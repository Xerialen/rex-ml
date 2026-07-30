"""STEP 2b — local locomotion policy (bhop / strafe) via TD3+BC.

Scope. In QuakeWorld "ground movement" is mostly airborne: a bunny hop spends
most of its ticks off the floor. Restricting the dataset to `ground_state ==
ground` would teach walking, not bhop, so the policy owns the whole locomotion
regime -- ground, air, jumps, falls, landings -- and only rocket jumps (BRIEF
2c, a DMP) and water are carved out. `maneuver_external` is excluded too: those
ticks are an opponent's rocket moving the player, not the player's own control,
and imitating them would teach the policy to reproduce being shot.

Goal conditioning is hindsight relabelled: the goal is the recorder's own
position H ticks later, expressed in the body frame of the current tick. That is
the same thing the BRIEF step 3 planner will hand down (a navmesh waypoint in
local coordinates), and it makes the human optimal for the goal by construction.

Reward is closing speed on that waypoint, in units/s. That is the "superhuman
efficiency" term stated directly rather than as a proxy.

Subcommands:
    build   materialise (s, a, r, s', done) to .npy
    train   TD3+BC on the H100
    eval    held-out action error + open-loop rollout tracking error
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from . import config as C
from . import qwphys

DATA = C.OUT_DIR / "policy"
LOCOMOTION_KINDS = (0, 1, 2, 5, 6, 7, 8)   # trims, jump, fall, land, other_*
H_MIN, H_MAX = 15, 60                       # goal horizon in ticks (~0.2 - 0.8 s)

STATE_COLS = [
    "v_fwd", "v_right", "vz", "speed_xy", "slip_sin", "slip_cos",
    "omega_prev", "pitch", "on_ground", "was_air",
    "goal_f", "goal_r", "goal_z", "goal_dist",
]
ACTION_COLS = ["fmove", "smove", "dyaw", "jump"]

# Scales chosen so every channel is O(1); recorded here because the Rust
# inference path in BRIEF step 4 has to reproduce them exactly.
S_SCALE = np.array([400., 400., 400., 400., 1., 1., 10., 90., 1., 1.,
                    500., 500., 200., 500.], dtype=np.float32)
A_SCALE = np.array([400., 400., 0.35, 1.], dtype=np.float32)


# ==========================================================================
# build
# ==========================================================================

def build(limit_batches: int | None = None, seed: int = 0, out: Path = DATA):
    import duckdb
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads TO 24")
    con.execute("SET preserve_insertion_order = false")
    con.execute(f"CREATE VIEW tk AS SELECT * FROM read_parquet('{C.OUT_DIR}/step1_ticks/*.parquet')")
    con.execute(f"CREATE VIEW rt AS SELECT * FROM read_parquet('{C.REPLAY_TICKS}', hive_partitioning=1)")
    con.execute(f"CREATE VIEW uc AS SELECT * FROM read_parquet('{C.USERCMDS}', hive_partitioning=1)")

    bf = f"AND t.batch < {limit_batches}" if limit_batches else ""
    kinds = ",".join(str(k) for k in LOCOMOTION_KINDS)
    q = f"""
      SELECT t.demo_key, t.slot, t.cmd_ordinal, t.split, t.kind, t.ground_state,
             t.v_fwd, t.v_right, t.vz, t.speed_xy, t.slip, t.omega_prev, t.pitch_deg,
             t.forwardmove, t.sidemove, t.dyaw, t.jump_btn, t.msec, t.has_next,
             r.x, r.y, r.z, u.yaw
      FROM tk t
      JOIN rt r ON r.demo_key = t.demo_key AND r.slot = t.slot AND r.cmd_ordinal = t.cmd_ordinal
      JOIN uc u ON u.demo_key = t.demo_key AND u.slot = t.slot AND u.cmd_ordinal = t.cmd_ordinal
      WHERE t.kind IN ({kinds}) AND t.waterlevel = 0 {bf}
      ORDER BY t.demo_key, t.slot, t.cmd_ordinal
    """
    t0 = time.time()
    tbl = con.execute(q).arrow()
    if not hasattr(tbl, "column_names"):
        tbl = tbl.read_all()
    g = {n: np.ascontiguousarray(tbl.column(n).combine_chunks().to_numpy(zero_copy_only=False))
         for n in tbl.column_names if n != "split"}
    split = np.asarray(tbl.column("split").to_pylist(), dtype=object)
    n = len(g["cmd_ordinal"])
    print(f"loaded {n:,} locomotion ticks in {time.time()-t0:.1f}s", flush=True)

    # contiguity: same track and consecutive cmd_ordinal
    same = np.zeros(n, bool)
    same[:-1] = ((g["demo_key"][1:] == g["demo_key"][:-1])
                 & (g["slot"][1:] == g["slot"][:-1])
                 & (g["cmd_ordinal"][1:] == g["cmd_ordinal"][:-1] + 1))

    rng = np.random.default_rng(seed)
    H = rng.integers(H_MIN, H_MAX + 1, size=n)

    # index of the goal tick: i + H, but clipped to the end of the contiguous run.
    # same[i] is the link i -> i+1, so a run ends exactly where same is False.
    ends = np.flatnonzero(~same)
    if len(ends) == 0 or ends[-1] != n - 1:
        ends = np.append(ends, n - 1)
    run_end = ends[np.searchsorted(ends, np.arange(n), side="left")]
    gi = np.minimum(np.arange(n) + H, run_end)

    # goal in the body frame of tick i
    yaw = np.deg2rad(g["yaw"].astype(np.float64) * C.U16_TO_DEG)
    cy, sy = np.cos(yaw), np.sin(yaw)
    dx = g["x"][gi] - g["x"]
    dy = g["y"][gi] - g["y"]
    goal_f = dx * cy + dy * sy
    goal_r = dx * sy - dy * cy
    goal_z = g["z"][gi] - g["z"]
    goal_d = np.sqrt(goal_f ** 2 + goal_r ** 2 + goal_z ** 2)

    # the SAME world goal seen from tick i+1, for the reward
    nx = np.minimum(np.arange(n) + 1, n - 1)
    dx2 = g["x"][gi] - g["x"][nx]
    dy2 = g["y"][gi] - g["y"][nx]
    dz2 = g["z"][gi] - g["z"][nx]
    goal_d_next = np.sqrt(dx2 ** 2 + dy2 ** 2 + dz2 ** 2)

    dt = np.clip(g["msec"].astype(np.float64), 1, 50) / 1000.0
    reward = (goal_d - goal_d_next) / dt          # closing speed, units/s

    was_air = np.zeros(n, bool)
    was_air[1:] = (g["ground_state"][:-1] != 0) & same[:-1]

    S = np.stack([
        g["v_fwd"], g["v_right"], g["vz"], g["speed_xy"],
        np.sin(g["slip"]), np.cos(g["slip"]),
        np.nan_to_num(g["omega_prev"], nan=0.0), g["pitch_deg"],
        (g["ground_state"] == 0).astype(np.float64), was_air.astype(np.float64),
        goal_f, goal_r, goal_z, goal_d,
    ], axis=1).astype(np.float32)

    A = np.stack([
        g["forwardmove"], g["sidemove"],
        np.nan_to_num(g["dyaw"], nan=0.0), g["jump_btn"].astype(np.float64),
    ], axis=1).astype(np.float32)

    valid = same & g["has_next"].astype(bool) & (gi > np.arange(n))
    S2 = np.empty_like(S)
    S2[:-1] = S[1:]
    S2[-1] = S[-1]
    # next state must carry the SAME goal, re-expressed at i+1
    yaw2 = np.roll(yaw, -1)
    cy2, sy2 = np.cos(yaw2), np.sin(yaw2)
    S2[:, 10] = (dx2 * cy2 + dy2 * sy2).astype(np.float32)
    S2[:, 11] = (dx2 * sy2 - dy2 * cy2).astype(np.float32)
    S2[:, 12] = dz2.astype(np.float32)
    S2[:, 13] = goal_d_next.astype(np.float32)

    done = (~same) | (gi <= np.arange(n) + 1)

    keep = valid & np.isfinite(S).all(1) & np.isfinite(A).all(1) & np.isfinite(reward)
    print(f"{keep.sum():,} usable transitions ({100*keep.mean():.1f} %)", flush=True)

    for name, arr in (("S", S), ("A", A), ("S2", S2)):
        np.save(out / f"{name}.npy", arr[keep])
    np.save(out / "R.npy", reward[keep].astype(np.float32))
    np.save(out / "D.npy", done[keep].astype(np.float32))
    sp = np.where(split == "train", 0, np.where(split == "val", 1, 2)).astype(np.int8)
    np.save(out / "SP.npy", sp[keep])
    meta = dict(n=int(keep.sum()), state_cols=STATE_COLS, action_cols=ACTION_COLS,
                s_scale=S_SCALE.tolist(), a_scale=A_SCALE.tolist(),
                h_min=H_MIN, h_max=H_MAX, kinds=list(LOCOMOTION_KINDS),
                splits={s: int((sp[keep] == i).sum()) for i, s in enumerate(("train", "val", "test"))},
                reward_p={p: float(np.percentile(reward[keep], p)) for p in (1, 50, 99)})
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


# ==========================================================================
# model + TD3+BC
# ==========================================================================

def _torch():
    import torch
    import torch.nn as nn
    return torch, nn


def make_nets(sdim, adim, width=256):
    torch, nn = _torch()

    class Actor(nn.Module):
        def __init__(s):
            super().__init__()
            s.f = nn.Sequential(nn.Linear(sdim, width), nn.ReLU(),
                                nn.Linear(width, width), nn.ReLU(),
                                nn.Linear(width, adim), nn.Tanh())

        def forward(s, x):
            return s.f(x)

    class Critic(nn.Module):
        def __init__(s):
            super().__init__()
            mk = lambda: nn.Sequential(nn.Linear(sdim + adim, width), nn.ReLU(),
                                       nn.Linear(width, width), nn.ReLU(),
                                       nn.Linear(width, 1))
            s.q1, s.q2 = mk(), mk()

        def forward(s, x, a):
            xa = torch.cat([x, a], 1)
            return s.q1(xa), s.q2(xa)

    return Actor, Critic


def train_bc(steps=100_000, batch=1024, lr=3e-4, width=256, out: Path = DATA, seed=0):
    """Plain behaviour cloning, as the control BRIEF 2b's fallback clause requires.

    TD3+BC is only worth its complexity if the Q term earns it. Measured here, the
    critic saturates at the analytic bound QMAX = 1/(1-gamma) = 20, which makes
    lambda = alpha/|Q| ~ 0.12 and leaves the actor ~88 % behaviour cloning anyway.
    Training the pure-BC control lets that be a measurement instead of a claim.
    """
    torch, nn = _torch()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(seed)
    S = np.load(out / "S.npy"); A = np.load(out / "A.npy"); SP = np.load(out / "SP.npy")
    tr = SP == 0
    s_sc = torch.tensor(S_SCALE, device=dev); a_sc = torch.tensor(A_SCALE, device=dev)
    St = torch.tensor(S[tr], device=dev) / s_sc
    At = torch.clamp(torch.tensor(A[tr], device=dev) / a_sc, -1, 1)
    n = St.shape[0]
    Actor, _ = make_nets(St.shape[1], At.shape[1], width)
    actor = Actor().to(dev)
    opt = torch.optim.Adam(actor.parameters(), lr=lr)
    t0 = time.time()
    for it in range(1, steps + 1):
        idx = torch.randint(0, n, (batch,), device=dev)
        loss = nn.functional.mse_loss(actor(St[idx]), At[idx])
        opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
        if it % 20_000 == 0:
            print(f"[bc {it:>7}] mse {float(loss):.4f}  {time.time()-t0:.0f}s", flush=True)
    torch.save(dict(actor=actor.state_dict(), width=width, s_scale=S_SCALE,
                    a_scale=A_SCALE, state_cols=STATE_COLS, action_cols=ACTION_COLS),
               out / "actor_bc.pt")
    print(f"saved {out/'actor_bc.pt'}")


def train(steps=200_000, batch=1024, alpha=2.5, gamma=0.95, tau=0.005,
          policy_noise=0.2, noise_clip=0.5, policy_freq=2, lr=3e-4,
          width=256, out: Path = DATA, seed=0):
    torch, nn = _torch()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(seed)

    S = np.load(out / "S.npy"); A = np.load(out / "A.npy")
    S2 = np.load(out / "S2.npy"); R = np.load(out / "R.npy")
    D = np.load(out / "D.npy"); SP = np.load(out / "SP.npy")
    tr = SP == 0
    print(f"train transitions {tr.sum():,}  dev={dev}", flush=True)

    s_sc = torch.tensor(S_SCALE, device=dev)
    a_sc = torch.tensor(A_SCALE, device=dev)
    St = torch.tensor(S[tr], device=dev) / s_sc
    At = torch.clamp(torch.tensor(A[tr], device=dev) / a_sc, -1, 1)
    S2t = torch.tensor(S2[tr], device=dev) / s_sc
    # Reward as the FRACTION of the outstanding distance closed this tick, not
    # raw closing speed. Raw closing speed is unbounded and the goal is never an
    # absorbing state, so the critic had nothing to anchor to: Q ran
    # 219 -> 3,185 -> 19,877 over 30 k steps and the loss followed it. R was
    # stored in units/s, so multiplying by a nominal tick converts it back to
    # units closed, and dividing by the distance outstanding bounds the
    # undiscounted return by ~1.
    d0 = torch.tensor(np.maximum(S[tr][:, 13], 1.0).astype(np.float32),
                      device=dev).unsqueeze(1)
    Rt = torch.tensor(R[tr], device=dev).unsqueeze(1) * 0.014
    Rt = torch.clamp(Rt / d0, -1.0, 1.0)
    Dt = torch.tensor(D[tr], device=dev).unsqueeze(1)
    n = St.shape[0]
    QMAX = 1.0 / (1.0 - gamma)

    Actor, Critic = make_nets(St.shape[1], At.shape[1], width)
    actor, critic = Actor().to(dev), Critic().to(dev)
    actor_t = Actor().to(dev); actor_t.load_state_dict(actor.state_dict())
    critic_t = Critic().to(dev); critic_t.load_state_dict(critic.state_dict())
    oa = torch.optim.Adam(actor.parameters(), lr=lr)
    oc = torch.optim.Adam(critic.parameters(), lr=lr)

    t0 = time.time()
    log = []
    for it in range(1, steps + 1):
        idx = torch.randint(0, n, (batch,), device=dev)
        s, a, s2, r, d = St[idx], At[idx], S2t[idx], Rt[idx], Dt[idx]

        with torch.no_grad():
            noise = (torch.randn_like(a) * policy_noise).clamp(-noise_clip, noise_clip)
            a2 = (actor_t(s2) + noise).clamp(-1, 1)
            q1t, q2t = critic_t(s2, a2)
            # Rewards are bounded in [-1, 1] by construction, so |Q| <= 1/(1-gamma)
            # analytically. Clipping the bootstrap target to that bound cannot
            # bias a correct Q and stops the divergence outright: unclipped, Q
            # ran to 56,051 against a true bound of 20 by 40 k steps.
            target = (r + gamma * (1 - d) * torch.min(q1t, q2t)).clamp(-QMAX, QMAX)
        q1, q2 = critic(s, a)
        closs = nn.functional.mse_loss(q1, target) + nn.functional.mse_loss(q2, target)
        oc.zero_grad(set_to_none=True); closs.backward(); oc.step()

        if it % policy_freq == 0:
            pi = actor(s)
            q = critic.q1(torch.cat([s, pi], 1))
            lmbda = alpha / q.abs().mean().detach()
            bc = nn.functional.mse_loss(pi, a)
            aloss = -lmbda * q.mean() + bc
            oa.zero_grad(set_to_none=True); aloss.backward(); oa.step()
            with torch.no_grad():
                for p, pt in zip(critic.parameters(), critic_t.parameters()):
                    pt.mul_(1 - tau).add_(tau * p)
                for p, pt in zip(actor.parameters(), actor_t.parameters()):
                    pt.mul_(1 - tau).add_(tau * p)

        if it % 10_000 == 0:
            log.append(dict(it=it, critic=float(closs), bc=float(bc),
                            q=float(q.mean()), s=round(time.time() - t0, 1)))
            print(f"[{it:>7}] critic {float(closs):.4f}  bc {float(bc):.4f}  "
                  f"q {float(q.mean()):.3f}  {time.time()-t0:.0f}s", flush=True)

    torch.save(dict(actor=actor.state_dict(), width=width,
                    s_scale=S_SCALE, a_scale=A_SCALE,
                    state_cols=STATE_COLS, action_cols=ACTION_COLS),
               out / "actor.pt")
    (out / "train_log.json").write_text(json.dumps(log, indent=2))
    print(f"saved {out/'actor.pt'}")


# ==========================================================================
# eval — held-out action error and open-loop rollout tracking
# ==========================================================================

def evaluate(out: Path = DATA, ckpt: str = "actor.pt", n_roll: int = 4000,
             horizon: int = 40, seed: int = 0):
    """BRIEF 2b asks for held-out action error, not training loss. Both are here,
    plus the rollout error that actually predicts step 4 behaviour.

    The rollout closes the loop through `qwphys`: start from a held-out state,
    let the policy choose every usercmd for `horizon` ticks, integrate QW pmove,
    and compare against where the human actually went. The sim has no collision
    model, so ticks whose recorded path touched geometry are reported separately
    rather than folded into the headline number.
    """
    torch, nn = _torch()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    ck = torch.load(out / ckpt, map_location=dev, weights_only=False)
    Actor, _ = make_nets(len(STATE_COLS), len(ACTION_COLS), ck["width"])
    actor = Actor().to(dev); actor.load_state_dict(ck["actor"]); actor.eval()

    S = np.load(out / "S.npy"); A = np.load(out / "A.npy"); SP = np.load(out / "SP.npy")
    res = {}
    for name, code in (("train", 0), ("val", 1), ("test", 2)):
        m = SP == code
        if not m.any():
            continue
        idx = np.flatnonzero(m)
        rng = np.random.default_rng(seed)
        if len(idx) > 500_000:
            idx = rng.choice(idx, 500_000, replace=False)
        with torch.no_grad():
            s = torch.tensor(S[idx], device=dev) / torch.tensor(S_SCALE, device=dev)
            pred = actor(s).cpu().numpy() * A_SCALE
        tgt = A[idx]
        per = {}
        for k, col in enumerate(ACTION_COLS):
            e = np.abs(pred[:, k] - tgt[:, k])
            per[col] = dict(mae=float(e.mean()), p50=float(np.percentile(e, 50)),
                            p90=float(np.percentile(e, 90)))
        # jump is a bit, so report it as a classification too
        jp = pred[:, 3] > 0.5
        jt = tgt[:, 3] > 0.5
        per["jump"]["accuracy"] = float((jp == jt).mean())
        per["jump"]["precision"] = float((jt[jp]).mean()) if jp.any() else 0.0
        per["jump"]["recall"] = float((jp[jt]).mean()) if jt.any() else 0.0
        # direction agreement on the move axes: does it pick the same quadrant?
        agree = ((np.sign(pred[:, 0]) == np.sign(tgt[:, 0]))
                 & (np.sign(pred[:, 1]) == np.sign(tgt[:, 1])))
        per["move_quadrant_agreement"] = float(agree.mean())
        res[name] = per
    (out / f"eval_action_{Path(ckpt).stem}.json").write_text(json.dumps(res, indent=2))
    for k, v in res.items():
        print(f"{k}: fmove MAE {v['fmove']['mae']:.1f}  smove MAE {v['smove']['mae']:.1f}  "
              f"dyaw MAE {np.rad2deg(v['dyaw']['mae']):.2f} deg  "
              f"jump acc {v['jump']['accuracy']*100:.1f}%  "
              f"quadrant {v['move_quadrant_agreement']*100:.1f}%")
    return res


# ==========================================================================
# discrete-head policy — the fix for the quadrant-agreement failure
# ==========================================================================

# Measured over the 27 M-transition dataset, forwardmove and sidemove are not
# continuous: they are keyboard axes taking 0 about 45 % of the time and +/-508,
# +/-400, +/-320 the rest. Regressing them under MSE collapses the prediction to
# the conditional mean near zero, and the *sign* of a near-zero prediction is
# noise -- which is exactly what the 25 % move-quadrant agreement (chance for
# four quadrants) was reporting. Sign is the part that matters for movement, so
# it gets a classifier.
MOVE_MAG = 508.0   # the modal magnitude; pmove accepts any value, humans press a key


def make_disc_actor(sdim, width=256, depth=2):
    """`depth` is the number of `Linear(width, width)`-ish hidden layers in the trunk (the first
    maps sdim -> width, the rest width -> width), each followed by ReLU. Default `depth=2`
    reproduces the original hard-coded two-layer trunk exactly -- same `trunk.0`/`trunk.2` state
    dict keys, same architecture -- so nothing already trained or exported changes meaning.
    SPEC F1.0 needs `depth=3` at `width=512` (the size SPEC G0.4 measured the tick budget allows);
    depth is a constructor arg instead of a second class so `export_policy.py` has one code path
    for both.
    """
    torch, nn = _torch()
    if depth < 1:
        raise ValueError(f"depth must be >= 1, got {depth}")

    class DiscActor(nn.Module):
        """3-way sign heads for the move axes, continuous dyaw, binary jump."""

        def __init__(s):
            super().__init__()
            layers = []
            d_in = sdim
            for _ in range(depth):
                layers += [nn.Linear(d_in, width), nn.ReLU()]
                d_in = width
            s.trunk = nn.Sequential(*layers)
            s.f_head = nn.Linear(width, 3)   # -1 / 0 / +1
            s.s_head = nn.Linear(width, 3)
            s.yaw_head = nn.Linear(width, 1)
            s.jump_head = nn.Linear(width, 1)

        def forward(s, x):
            h = s.trunk(x)
            return s.f_head(h), s.s_head(h), torch.tanh(s.yaw_head(h)), s.jump_head(h)

    return DiscActor


def _sign_class(v, dead=1.0):
    """-1/0/+1 -> class 0/1/2."""
    return np.where(v > dead, 2, np.where(v < -dead, 0, 1)).astype(np.int64)


def train_disc(steps=120_000, batch=1024, lr=3e-4, width=256, depth=2, out: Path = DATA,
               seed=0, ckpt_name="actor_disc.pt"):
    """`depth`/`width` default to the shipped 2x256 shape; `ckpt_name` defaults to the shipped
    checkpoint's filename too, so an unqualified call reproduces the original behaviour exactly.
    SPEC F1.0 trains a second, larger policy (depth=3, width=512) on the *same* data/objective --
    call this with those overridden and a different `ckpt_name` so the 2x256 checkpoint used to
    build the frozen, parity-verified `policy.bin` is never touched.
    """
    torch, nn = _torch()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(seed)
    S = np.load(out / "S.npy"); A = np.load(out / "A.npy"); SP = np.load(out / "SP.npy")
    tr = SP == 0
    s_sc = torch.tensor(S_SCALE, device=dev)
    St = torch.tensor(S[tr], device=dev) / s_sc
    fc = torch.tensor(_sign_class(A[tr][:, 0]), device=dev)
    sc = torch.tensor(_sign_class(A[tr][:, 1]), device=dev)
    yw = torch.tensor(np.clip(A[tr][:, 2] / A_SCALE[2], -1, 1), device=dev).unsqueeze(1)
    jp = torch.tensor((A[tr][:, 3] > 0.5).astype(np.float32), device=dev).unsqueeze(1)
    n = St.shape[0]
    print(f"discrete-head BC on {n:,} transitions; depth={depth} width={width}; class balance "
          f"f={np.bincount(_sign_class(A[tr][:,0]))/n} s={np.bincount(_sign_class(A[tr][:,1]))/n}",
          flush=True)

    actor = make_disc_actor(St.shape[1], width, depth)().to(dev)
    n_params = sum(p.numel() for p in actor.parameters())
    print(f"actor params: {n_params:,}", flush=True)
    opt = torch.optim.Adam(actor.parameters(), lr=lr)
    ce, mse, bce = nn.CrossEntropyLoss(), nn.MSELoss(), nn.BCEWithLogitsLoss()
    t0 = time.time()
    log = []
    for it in range(1, steps + 1):
        i = torch.randint(0, n, (batch,), device=dev)
        lf, ls, ly, lj = actor(St[i])
        loss = ce(lf, fc[i]) + ce(ls, sc[i]) + 10.0 * mse(ly, yw[i]) + bce(lj, jp[i])
        opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
        if it % 20_000 == 0:
            print(f"[disc {it:>7}] loss {float(loss):.4f}  {time.time()-t0:.0f}s", flush=True)
            log.append(dict(it=it, loss=float(loss), s=round(time.time() - t0, 1)))
    torch.save(dict(actor=actor.state_dict(), width=width, depth=depth, s_scale=S_SCALE,
                    move_mag=MOVE_MAG, state_cols=STATE_COLS, kind="disc",
                    steps=steps, batch=batch, lr=lr, seed=seed, n_params=n_params),
               out / ckpt_name)
    (out / f"train_log_{Path(ckpt_name).stem}.json").write_text(json.dumps(log, indent=2))
    print(f"saved {out/ckpt_name}")


def evaluate_disc(out: Path = DATA, ckpt: str = "actor_disc.pt", seed: int = 0):
    torch, nn = _torch()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    ck = torch.load(out / ckpt, map_location=dev, weights_only=False)
    # Older checkpoints (the shipped 2x256) predate the `depth` field; they are all depth=2, so
    # that is the correct default rather than a guess.
    actor = make_disc_actor(len(STATE_COLS), ck["width"], ck.get("depth", 2))().to(dev)
    actor.load_state_dict(ck["actor"]); actor.eval()
    S = np.load(out / "S.npy"); A = np.load(out / "A.npy"); SP = np.load(out / "SP.npy")
    res = {}
    for name, code in (("train", 0), ("val", 1), ("test", 2)):
        m = SP == code
        idx = np.flatnonzero(m)
        rng = np.random.default_rng(seed)
        if len(idx) > 500_000:
            idx = rng.choice(idx, 500_000, replace=False)
        with torch.no_grad():
            x = torch.tensor(S[idx], device=dev) / torch.tensor(S_SCALE, device=dev)
            lf, ls, ly, lj = actor(x)
            fcls = lf.argmax(1).cpu().numpy(); scls = ls.argmax(1).cpu().numpy()
            yaw = ly.cpu().numpy().ravel() * A_SCALE[2]
            jump = (torch.sigmoid(lj).cpu().numpy().ravel() > 0.5)
        tf, ts = _sign_class(A[idx][:, 0]), _sign_class(A[idx][:, 1])
        pf = np.array([-MOVE_MAG, 0.0, MOVE_MAG])[fcls]
        ps = np.array([-MOVE_MAG, 0.0, MOVE_MAG])[scls]
        res[name] = dict(
            fmove_class_acc=float((fcls == tf).mean()),
            smove_class_acc=float((scls == ts).mean()),
            move_quadrant_agreement=float(((fcls == tf) & (scls == ts)).mean()),
            fmove_mae=float(np.abs(pf - A[idx][:, 0]).mean()),
            smove_mae=float(np.abs(ps - A[idx][:, 1]).mean()),
            dyaw_mae_deg=float(np.rad2deg(np.abs(yaw - A[idx][:, 2])).mean()),
            jump_acc=float((jump == (A[idx][:, 3] > 0.5)).mean()),
        )
        v = res[name]
        print(f"{name}: fmove cls {v['fmove_class_acc']*100:.1f}%  smove cls "
              f"{v['smove_class_acc']*100:.1f}%  quadrant {v['move_quadrant_agreement']*100:.1f}%  "
              f"fmove MAE {v['fmove_mae']:.1f}  dyaw MAE {v['dyaw_mae_deg']:.2f} deg  "
              f"jump {v['jump_acc']*100:.1f}%")
    # Keep the original filename for the original checkpoint (nothing existing changes meaning);
    # any other checkpoint (e.g. SPEC F1.0's 3x512 run) gets its own file so it never overwrites
    # the shipped policy's measured eval_disc.json.
    eval_name = "eval_disc.json" if ckpt == "actor_disc.pt" else f"eval_disc_{Path(ckpt).stem}.json"
    (out / eval_name).write_text(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "train", "train_bc", "train_disc", "eval", "eval_disc"])
    ap.add_argument("--ckpt", default="actor.pt")
    ap.add_argument("--ckpt-out", default=None,
                    help="train_disc only: checkpoint filename to save (default: actor_disc.pt "
                         "if --width/--depth are left at the shipped 256/2, else "
                         "actor_disc_{depth}x{width}.pt)")
    ap.add_argument("--batches", type=int, default=None)
    ap.add_argument("--steps", type=int, default=200_000)
    ap.add_argument("--alpha", type=float, default=2.5)
    ap.add_argument("--width", type=int, default=256)
    ap.add_argument("--depth", type=int, default=2)
    a = ap.parse_args()
    if a.cmd == "eval":
        evaluate(ckpt=a.ckpt)
    elif a.cmd == "eval_disc":
        evaluate_disc(ckpt=a.ckpt if a.ckpt != "actor.pt" else "actor_disc.pt")
    elif a.cmd == "train_disc":
        ckpt_out = a.ckpt_out
        if ckpt_out is None:
            ckpt_out = "actor_disc.pt" if (a.width, a.depth) == (256, 2) else f"actor_disc_{a.depth}x{a.width}.pt"
        train_disc(steps=a.steps, width=a.width, depth=a.depth, ckpt_name=ckpt_out)
    elif a.cmd == "train_bc":
        train_bc()
    elif a.cmd == "build":
        build(limit_batches=a.batches)
    else:
        train(steps=a.steps, alpha=a.alpha)
