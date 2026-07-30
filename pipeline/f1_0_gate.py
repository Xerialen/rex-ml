#!/usr/bin/env python3
"""SPEC F1.0 part 3 — the gate.

Exports the trained 3-hidden-layer/512-wide discrete actor beside the shipped 2x256 one (never
overwriting `policy.bin`/`policy.json`), re-runs the G0.2 parity check against the new network and
the new `rtx-nav` binary on >= 100,000 held-out rows, evaluates both policies' held-out imitation
agreement with the human demonstrations, and writes the whole thing -- training config, parameter
counts, full parity table, side-by-side agreement -- to `evidence/f1.0_bc_3x512.json`.

usage: python3 -m pipeline.f1_0_gate
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "pipeline" / "out" / "policy"
EVIDENCE = REPO / "evidence"

sys.path.insert(0, str(REPO))

from pipeline import export_policy as ep  # noqa: E402
from pipeline import policy as pl  # noqa: E402


def main() -> None:
    ckpt_old = DATA / "actor_disc.pt"
    ckpt_new = DATA / "actor_disc_3x512.pt"
    if not ckpt_new.exists():
        sys.exit(f"{ckpt_new} does not exist -- run train_disc --width 512 --depth 3 first")

    import torch  # noqa: PLC0415

    ck = torch.load(ckpt_new, map_location="cpu", weights_only=False)
    train_config = dict(
        depth=int(ck.get("depth", 3)),
        width=int(ck["width"]),
        steps=int(ck.get("steps", -1)),
        batch=int(ck.get("batch", -1)),
        lr=float(ck.get("lr", -1)),
        seed=int(ck.get("seed", -1)),
        n_params=int(ck.get("n_params", -1)),
        objective="same as shipped actor_disc.pt: CE(fmove sign class) + CE(smove sign class) "
                  "+ 10*MSE(tanh(yaw)) + BCEWithLogits(jump), Adam",
        data="pipeline/out/policy/{S,A,SP}.npy, train split only (SP==0), same build() as the "
             "shipped policy",
        source_ckpt=str(ckpt_new),
    )
    print("train config:", json.dumps(train_config, indent=2))

    # ---- export (never touches policy.bin / policy.json) ----
    meta_new = ep.export(ckpt=ckpt_new, out=DATA, bin_name="policy_3x512.bin", json_name="policy_3x512.json")
    print(f"exported {DATA/'policy_3x512.bin'} ({meta_new['bytes']} bytes), "
          f"{meta_new['nin']}->{meta_new['nh']}x{meta_new['depth']}->{meta_new['nout']}")
    meta_old = json.loads((DATA / "policy.json").read_text())

    param_counts = dict(
        old_2x256=dict(
            nin=meta_old["nin"], nh=meta_old["nh"], depth=meta_old.get("depth", 2), nout=meta_old["nout"],
            bytes=meta_old["bytes"], params=meta_old["bytes"] // 4,
        ),
        new_3x512=dict(
            nin=meta_new["nin"], nh=meta_new["nh"], depth=meta_new["depth"], nout=meta_new["nout"],
            bytes=meta_new["bytes"], params=meta_new["bytes"] // 4,
        ),
    )
    print("param counts:", json.dumps(param_counts, indent=2))

    # ---- sanity check against torch on a random batch ----
    ep.check(ckpt=ckpt_new, out=DATA, bin_name="policy_3x512.bin", json_name="policy_3x512.json")

    # ---- SPEC G0.2-style parity gate, new network + new rtx-nav binary, own evidence files ----
    parity_report = ep.parity(
        ckpt=ckpt_new, out=DATA, n_rows=200_000,
        json_name="policy_3x512.json", bin_name="policy_3x512.bin",
        obs_name="f1.0_obs.bin", rust_out_name="f1.0_rust_out.bin",
        report_name="f1.0_3x512_parity.json",
    )

    # ---- held-out imitation agreement, both policies, same held-out data ----
    print("\n--- evaluating held-out agreement: old 2x256 ---")
    eval_old = pl.evaluate_disc(out=DATA, ckpt="actor_disc.pt")
    print("\n--- evaluating held-out agreement: new 3x512 ---")
    eval_new = pl.evaluate_disc(out=DATA, ckpt="actor_disc_3x512.pt")

    comparison = {}
    for split in ("val", "test"):
        o, n = eval_old[split], eval_new[split]
        comparison[split] = dict(
            old_2x256=o,
            new_3x512=n,
            new_minus_old=dict(
                fmove_class_acc=n["fmove_class_acc"] - o["fmove_class_acc"],
                smove_class_acc=n["smove_class_acc"] - o["smove_class_acc"],
                move_quadrant_agreement=n["move_quadrant_agreement"] - o["move_quadrant_agreement"],
                fmove_mae=n["fmove_mae"] - o["fmove_mae"],
                smove_mae=n["smove_mae"] - o["smove_mae"],
                dyaw_mae_deg=n["dyaw_mae_deg"] - o["dyaw_mae_deg"],
                jump_acc=n["jump_acc"] - o["jump_acc"],
            ),
        )
    print("\ncomparison (new - old, positive = new policy better on that metric except *_mae "
          "where negative = better):")
    print(json.dumps(comparison, indent=2))

    report = dict(
        spec="F1.0",
        train_config=train_config,
        param_counts=param_counts,
        parity=parity_report,
        held_out_agreement=comparison,
        larger_policy_imitates_better=all(
            comparison[s]["new_minus_old"]["move_quadrant_agreement"] > 0 for s in ("val", "test")
        ),
    )
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "f1.0_bc_3x512.json").write_text(json.dumps(report, indent=2))
    print(f"\nwrote {EVIDENCE/'f1.0_bc_3x512.json'}")
    print(f"parity all_passed = {parity_report['all_passed']}")
    print(f"larger_policy_imitates_better = {report['larger_policy_imitates_better']}")


if __name__ == "__main__":
    main()
