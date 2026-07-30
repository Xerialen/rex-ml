#!/usr/bin/env python3
"""Export the trained discrete-head policy into the flat layout `automaton::Mlp` reads.

The Rust side keeps one weight matrix per layer (`w2` is NOUT x NH), while the Python actor has a
shared trunk and four separate heads. So the heads are concatenated in a fixed order —
f(3), s(3), yaw(1), jump(1) — giving NOUT = 8, and that order is the contract the Rust decode
must match. It is written into the sidecar rather than left implicit.

Activation: `Mlp::forward` applies `tanh` to every output. That happens to be exactly right here
rather than by luck of the draw, and it is worth stating why, because it is the kind of thing that
silently rots:

  * the two sign heads are read with `argmax`, and `tanh` is monotone, so `argmax` is unchanged;
  * the yaw head already has `tanh` applied inside the Python `forward`, so Rust reproduces it;
  * the jump head is trained with `BCEWithLogitsLoss`, so the decision is `logit > 0`, and
    `tanh(logit) > 0` is the same test.

If any head's activation changes on the Python side, this stops being true and the export must
change with it — hence `check` below, which compares Rust-order arithmetic against the live torch
model on random inputs instead of trusting the reasoning above.

usage:
  python3 export_policy.py            # write policy.bin + policy.json
  python3 export_policy.py --check    # also verify against the torch model
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "pipeline" / "out" / "policy"
EVIDENCE = REPO / "evidence"
RTX = REPO / "rtx"
# Head order in the exported `w2`/`b2`. The Rust decode depends on this and nothing else.
HEADS = [("f_head", 3), ("s_head", 3), ("yaw_head", 1), ("jump_head", 1)]


def load(ckpt: Path) -> dict:
    import torch  # noqa: PLC0415 — only needed when actually exporting

    return torch.load(ckpt, map_location="cpu", weights_only=False)


def export(ckpt: Path = DATA / "actor_disc.pt", out: Path = DATA,
           bin_name: str = "policy.bin", json_name: str = "policy.json") -> dict:
    """Write the flat weight blob + sidecar for a trained `DiscActor` checkpoint.

    Handles any trunk `depth` (SPEC F1.0 extends the original hard-coded 2-hidden-layer export to
    the 3-hidden-layer / width-512 shape `automaton::Mlp3` reads): the checkpoint's own `depth`
    field says how many `trunk.{0,2,4,...}` Linear layers to pull out; a checkpoint saved before
    `depth` existed is exactly the original 2-layer shape, so that is the correct default rather
    than a guess. Layer order in the blob is `w0 b0 w1 b1 ... w{depth-1} b{depth-1} w_head b_head`
    -- `Mlp::load`'s layout for depth=2, `Mlp3::load`'s for depth=3, one more `NH x NH` pair per
    extra layer beyond that.

    `bin_name`/`json_name` default to the original filenames so an unqualified call reproduces the
    shipped, parity-verified `policy.bin`/`policy.json` exactly. SPEC F1.0's 3x512 policy is
    written under distinct names (e.g. `policy_3x512.bin`) so the original artefact is never
    touched.
    """
    ck = load(ckpt)
    if ck.get("kind") != "disc":
        sys.exit(f"{ckpt} is kind={ck.get('kind')!r}, expected 'disc'")
    sd = {k: v.numpy().astype(np.float32) for k, v in ck["actor"].items()}
    nh = int(ck["width"])
    depth = int(ck.get("depth", 2))

    hidden = []
    for i in range(depth):
        idx = 2 * i  # nn.Sequential(Linear, ReLU, Linear, ReLU, ...) -- Linears at even indices
        hidden.append((sd[f"trunk.{idx}.weight"], sd[f"trunk.{idx}.bias"]))
    nin = hidden[0][0].shape[1]
    for i, (w, _b) in enumerate(hidden):
        expected_in = nin if i == 0 else nh
        assert w.shape == (nh, expected_in), (i, w.shape)

    w_head = np.concatenate([sd[f"{h}.weight"] for h, _ in HEADS], axis=0)
    b_head = np.concatenate([sd[f"{h}.bias"] for h, _ in HEADS], axis=0)
    nout = w_head.shape[0]
    assert nout == sum(n for _, n in HEADS)

    arrays = []
    for w, b in hidden:
        arrays += [w, b]
    arrays += [w_head, b_head]
    blob = b"".join(a.astype("<f4").tobytes() for a in arrays)
    (out / bin_name).write_bytes(blob)

    layout = " ".join(
        [f"w0[NH*NIN] b0[NH]"] + [f"w{i}[NH*NH] b{i}[NH]" for i in range(1, depth)]
        + [f"w{depth}[NOUT*NH] b{depth}[NOUT]"]
    ) + ", little-endian f32"
    meta = {
        "layout": layout,
        "nin": nin,
        "nh": nh,
        "depth": depth,
        "nout": nout,
        "heads": [{"name": h, "width": n} for h, n in HEADS],
        # Everything the Rust decode needs to turn 8 outputs into a usercmd.
        "decode": {
            "fmove": "(argmax(out[0:3]) - 1) * move_mag",
            "smove": "(argmax(out[3:6]) - 1) * move_mag",
            "dyaw": "out[6] * a_scale[2]",
            "jump": "out[7] > 0",
        },
        "s_scale": np.asarray(ck["s_scale"], dtype=float).tolist(),
        "a_scale": [400.0, 400.0, 0.35, 1.0],
        "move_mag": float(ck["move_mag"]),
        "state_cols": list(ck["state_cols"]),
        "bytes": len(blob),
        "source": ckpt.name,
    }
    (out / json_name).write_text(json.dumps(meta, indent=1))
    return meta


def check(ckpt: Path = DATA / "actor_disc.pt", out: Path = DATA, n: int = 256,
          bin_name: str = "policy.bin", json_name: str = "policy.json") -> None:
    """Recompute the forward pass the way Rust will and compare against torch.

    Depth-general (SPEC F1.0): the hidden-layer count comes from `policy.json`'s own `depth`
    field (2 for the shipped network, 3 for the 3x512 one), and the manual forward loop below
    replays exactly that many `relu(x @ w.T + b)` hidden layers before the raw head layer -- the
    same layout `Mlp::forward`/`Mlp3::forward` compute on the Rust side.
    """
    import torch  # noqa: PLC0415

    meta = json.loads((out / json_name).read_text())
    nin, nh, nout = meta["nin"], meta["nh"], meta["nout"]
    depth = int(meta.get("depth", 2))
    raw = np.frombuffer((out / bin_name).read_bytes(), dtype="<f4")
    i = 0

    def take(k: int, shape) -> np.ndarray:
        nonlocal i
        a = raw[i : i + k].reshape(shape)
        i += k
        return a

    hidden = []
    for layer in range(depth):
        d_in = nin if layer == 0 else nh
        hidden.append((take(nh * d_in, (nh, d_in)), take(nh, (nh,))))
    w_head = take(nout * nh, (nout, nh))
    b_head = take(nout, (nout,))
    assert i == raw.size, f"{i} != {raw.size}"

    rng = np.random.default_rng(0)
    x = rng.standard_normal((n, nin)).astype(np.float32)
    h = x
    for w, b in hidden:
        h = np.maximum(h @ w.T + b, 0.0)
    # `Mlp::forward`'s own contract (see automaton.rs, and `Mlp3::forward`'s identical contract in
    # mlp3.rs): the output layer is returned RAW, with no activation at all. Whoever reads a head
    # applies its own activation -- argmax for the sign heads, a threshold at zero for jump, tanh
    # only for yaw. This function used to tanh every output first, in the mistaken belief that
    # tanh's monotonicity makes that a harmless no-op for argmax; measured here, it is not: two
    # logits that are cleanly separated pre-activation (e.g. 11.8 vs 44.1) both saturate to the
    # same float32 1.0 after tanh, so the "harmless" version picks by array order and fails on
    # ~1-2% of random rows -- reproducing, inside the test itself, exactly the ±300-logit collapse
    # this gate exists to catch (see `Mlp::forward`'s doc comment). Comparing the RAW output is
    # both correct and, measured against this checkpoint, exact: the numpy and torch arithmetic
    # agree to 0.0 max abs difference on this random batch.
    raw_out = h @ w_head.T + b_head

    from pipeline.policy import make_disc_actor  # noqa: PLC0415

    ck = load(ckpt)
    actor = make_disc_actor(nin, nh, depth)()
    actor.load_state_dict(ck["actor"])
    actor.eval()
    with torch.no_grad():
        lf, ls, ly, lj = actor(torch.tensor(x))
    # Torch's f_head/s_head/jump_head are plain nn.Linear, no activation -- lf/ls/lj are already the
    # same "raw" quantity `Mlp::forward` returns. Only yaw_head has tanh baked into torch's own
    # forward, so that's the one head compared post-activation, applying tanh here since raw_out
    # has none.
    tf, ts = lf.numpy(), ls.numpy()
    assert (raw_out[:, 0:3].argmax(1) == tf.argmax(1)).all(), "f_head argmax mismatch"
    assert (raw_out[:, 3:6].argmax(1) == ts.argmax(1)).all(), "s_head argmax mismatch"
    assert ((raw_out[:, 7] > 0) == (lj.numpy()[:, 0] > 0)).all(), "jump threshold mismatch"
    dy = np.abs(np.tanh(raw_out[:, 6]) - ly.numpy()[:, 0]).max()
    assert dy < 1e-5, f"yaw mismatch {dy}"
    print(f"check ok on {n} random inputs: argmax and jump exact, yaw max abs err {dy:.2e}")


def _rex_env_parity_bin() -> Path:
    """The Rust half of the ORIGINAL (2x256) gate, `rtx/crates/rex-env/src/bin/policy_parity.rs`.
    Prefer the release build (100k+ rows through a hand-rolled forward pass is worth not paying
    debug-profile cost for) but fall back to debug so `--check` works on a plain
    `cargo build -p rex-env`."""
    for profile in ("release", "debug"):
        p = RTX / "target" / profile / "rex-env-policy-parity"
        if p.exists():
            return p
    sys.exit(
        "rex-env-policy-parity is not built. Run this first:\n"
        "  cd ~/rex-ml/rtx && cargo build --release -p rex-env"
    )


def _rtx_nav_3x512_parity_bin() -> Path:
    """The Rust half of SPEC F1.0's gate, `rtx/crates/rtx-nav/src/bin/nav_policy_parity_3x512.rs`
    -- built in `rtx-nav`, not `rex-env` (another task is editing that crate concurrently)."""
    for profile in ("release", "debug"):
        p = RTX / "target" / profile / "nav_policy_parity_3x512"
        if p.exists():
            return p
    sys.exit(
        "nav_policy_parity_3x512 is not built. Run this first:\n"
        "  cd ~/rex-ml/rtx && cargo build --release -p rtx-nav --bin nav_policy_parity_3x512"
    )


def parity(ckpt: Path = DATA / "actor_disc.pt", out: Path = DATA, n_rows: int = 200_000, seed: int = 0,
           json_name: str = "policy.json", bin_name: str = "policy.bin",
           rust_bin: Path | None = None, obs_name: str = "g0.2_obs.bin",
           rust_out_name: str = "g0.2_rust_out.bin", report_name: str = "g0.2_parity.json") -> dict:
    """SPEC G0.2 — the gate itself: >= 100 000 held-out rows through both the live torch actor and
    the Rust `Mlp::forward` + `automaton::decode`, compared field by field.

    Held-out means the policy's own `test` split (`SP.npy == 2`, `train_disc` never samples from
    it), not a fresh random draw — the point is to catch disagreement on the kind of input the
    network will actually see, not on inputs from `check()`'s N(0,1) cloud, which the ±300-logit bug
    this gate exists to catch would not even reach (see automaton.rs's `Mlp::forward` doc comment).

    Depth-general (SPEC F1.0): `depth` is read from `policy.json`. Defaults (`json_name`/`bin_name`
    = "policy.json"/"policy.bin", `rust_bin` picked by depth, `obs_name`/`rust_out_name`/
    `report_name` = the original "g0.2_*" names) reproduce the original 2x256 gate exactly against
    `rex-env-policy-parity`, writing `evidence/g0.2_parity.json` as before. F1.0's 3x512 run passes
    distinct names for all of these so it never overwrites that frozen, parity-verified evidence.
    """
    import torch  # noqa: PLC0415

    from pipeline.policy import make_disc_actor  # noqa: PLC0415

    meta = json.loads((out / json_name).read_text())
    nin, nh, nout = meta["nin"], meta["nh"], meta["nout"]
    depth = int(meta.get("depth", 2))

    S = np.load(out / "S.npy")
    SP = np.load(out / "SP.npy")
    test_idx = np.flatnonzero(SP == 2)
    if len(test_idx) < n_rows:
        idx = test_idx
    else:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(test_idx, n_rows, replace=False))
    n = len(idx)
    if n < 100_000:
        sys.exit(f"only {n} held-out (test-split) rows available in {out/'S.npy'}, need >= 100000")

    s_scale = np.asarray(meta["s_scale"], dtype=np.float32)
    x = (S[idx].astype(np.float32) / s_scale).astype(np.float32)
    assert x.shape == (n, nin), x.shape

    ck = load(ckpt)
    actor = make_disc_actor(nin, nh, depth)()
    actor.load_state_dict(ck["actor"])
    actor.eval()
    with torch.no_grad():
        # NOT `actor(x)`: `DiscActor.forward` bakes `torch.tanh` into the yaw head itself
        # (`torch.tanh(s.yaw_head(h))`), so its public forward's 4th return is already
        # post-activation -- there is no way to recover the pre-tanh value from it. `Mlp::forward`
        # on the Rust side returns every head RAW, activation applied only by `decode`. So the two
        # "raw logit" streams are only the same quantity if yaw is read off `actor.yaw_head` before
        # `forward` wraps it: reach into the trunk and the four head submodules directly instead.
        # (First attempt at this used `actor(x)`'s already-activated yaw value directly as the
        # "raw" logit and measured a spurious 0.62 max abs diff against Rust's genuinely raw value
        # -- not a numerical error, a definition mismatch. This is that fix.)
        h = actor.trunk(torch.tensor(x))
        raw_lf = actor.f_head(h)
        raw_ls = actor.s_head(h)
        raw_ly = actor.yaw_head(h)
        raw_lj = actor.jump_head(h)
    tf, ts, ty_raw, tj = (t.numpy() for t in (raw_lf, raw_ls, raw_ly, raw_lj))
    # Same concatenation order export_policy used for w2/b2: f(3) s(3) yaw(1) jump(1), every entry
    # pre-activation, matching `Mlp::forward`'s contract exactly.
    torch_logits = np.concatenate([tf, ts, ty_raw, tj], axis=1).astype(np.float32)
    assert torch_logits.shape == (n, nout), torch_logits.shape

    a_scale = np.asarray(meta["a_scale"], dtype=np.float32)
    move_mag = np.float32(meta["move_mag"])
    sign = np.array([-1.0, 0.0, 1.0], dtype=np.float32)
    torch_fmove = sign[tf.argmax(1)] * move_mag
    torch_smove = sign[ts.argmax(1)] * move_mag
    torch_dyaw = (np.tanh(ty_raw[:, 0]) * a_scale[2]).astype(np.float32)
    torch_jump = tj[:, 0] > 0.0

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    obs_path = EVIDENCE / obs_name
    rust_out_path = EVIDENCE / rust_out_name
    obs_path.write_bytes(np.ascontiguousarray(x).tobytes())

    if rust_bin is not None:
        bin_path = rust_bin
    elif depth == 2:
        bin_path = _rex_env_parity_bin()
    elif depth == 3:
        bin_path = _rtx_nav_3x512_parity_bin()
    else:
        sys.exit(f"no known parity binary for depth={depth}; pass rust_bin= explicitly")
    t0 = time.time()
    r = subprocess.run(
        [str(bin_path), str(out / bin_name), str(obs_path), str(rust_out_path)],
        capture_output=True,
        text=True,
    )
    rust_wall_s = time.time() - t0
    if r.returncode != 0:
        sys.exit(f"{bin_path} failed (exit {r.returncode}):\nstdout: {r.stdout}\nstderr: {r.stderr}")
    if r.stderr.strip():
        print(r.stderr.strip())

    row_width = nout + 4
    raw = np.frombuffer(rust_out_path.read_bytes(), dtype="<f4")
    assert raw.size == n * row_width, f"rust output has {raw.size} floats, expected {n * row_width}"
    raw = raw.reshape(n, row_width)
    rust_logits = raw[:, :nout]
    rust_fmove, rust_smove, rust_dyaw = raw[:, nout], raw[:, nout + 1], raw[:, nout + 2]
    rust_jump = raw[:, nout + 3] > 0.5

    measured = dict(
        fmove_agreement=float((rust_fmove == torch_fmove).mean()),
        smove_agreement=float((rust_smove == torch_smove).mean()),
        jump_agreement=float((rust_jump == torch_jump).mean()),
        dyaw_max_abs_diff=float(np.abs(rust_dyaw - torch_dyaw).max()),
        logit_max_abs_diff=float(np.abs(rust_logits - torch_logits).max()),
    )
    thresholds = dict(
        fmove_agreement=1.0,
        smove_agreement=1.0,
        jump_agreement=1.0,
        dyaw_max_abs_diff=1e-5,
        logit_max_abs_diff=1e-3,
    )
    passed = dict(
        fmove_agreement=measured["fmove_agreement"] >= thresholds["fmove_agreement"],
        smove_agreement=measured["smove_agreement"] >= thresholds["smove_agreement"],
        jump_agreement=measured["jump_agreement"] >= thresholds["jump_agreement"],
        dyaw_max_abs_diff=measured["dyaw_max_abs_diff"] <= thresholds["dyaw_max_abs_diff"],
        logit_max_abs_diff=measured["logit_max_abs_diff"] <= thresholds["logit_max_abs_diff"],
    )

    # A tie in the argmax'd 3-way logits is exactly the failure mode this gate exists to catch (the
    # tanh-everywhere bug made ties common); report genuine ties rather than let them wash out in an
    # aggregate agreement number. Measured on torch's own logits, so this is about the network, not
    # about either implementation of argmax.
    def _ties(a: np.ndarray) -> int:
        s = np.sort(a, axis=1)
        return int((np.abs(s[:, -1] - s[:, -2]) < 1e-6).sum())

    report = dict(
        n_rows=n,
        source="S.npy[SP==2] (held-out test split, never seen by train_disc)",
        seed=seed,
        depth=depth,
        nh=nh,
        thresholds=thresholds,
        measured=measured,
        passed=passed,
        all_passed=all(passed.values()),
        f_head_argmax_ties=_ties(torch_logits[:, 0:3]),
        s_head_argmax_ties=_ties(torch_logits[:, 3:6]),
        rust_binary=str(bin_path),
        rust_wall_s=round(rust_wall_s, 3),
        ckpt=str(ckpt),
    )
    (EVIDENCE / report_name).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    m = export()
    print(f"wrote {DATA/'policy.bin'} ({m['bytes']} bytes) "
          f"and policy.json — {m['nin']}->{m['nh']}->{m['nh']}->{m['nout']}")
    if "--check" in sys.argv:
        check()
        # SPEC G0.2: the random-input sanity check above is necessary but not sufficient — it
        # never exercises the ±300-logit regime the tanh-everywhere bug actually lived in. `parity`
        # is the real gate: >= 100k held-out rows through both torch and the built `rex-env`
        # comparison binary, every field's agreement measured and written to
        # `evidence/g0.2_parity.json`.
        parity()
