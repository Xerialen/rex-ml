"""Do humans jump *at edges* — and can the policy even see one?

Measured 2026-07-29: the three routes into the SNG mega fail because the bot runs off the ledge at
x ~ -670 into the rocket pit and thrashes there for two thirds of the episode. The route needs three
gap jumps in a row (48 u across the rocket pit, 32 u across the shelf at x ~ -800, then ~140 u south
to the mega strip). The navmesh models them — its path nodes hang in mid-air over each gap — but the
14-dimensional observation carries only own velocity, ground contact and a body-frame offset to the
lookahead goal. **Nothing in it describes the ground ahead.** A policy that cannot see a hole can
only clear one by memorising where it is, and position is not in the observation either.

Before adding a feature on that reasoning alone, this asks the corpus the question directly: when a
human leaves the ground, how far ahead is the floor about to end? If takeoffs sit at edges while
ordinary running ticks do not, then "distance to the edge ahead" is the signal the policy is missing,
and it is the corpus that said so rather than me.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import race

MAP = race.MAP
# How far ahead to look, and at what resolution. 320 u is one second of running at sv_maxspeed.
PROBE_MAX_U = 320.0
PROBE_STEP_U = 8.0
# A drop this deep is an edge; anything shallower is a stair or a kerb and is run straight over.
EDGE_DROP_U = 48.0
DOWN_PROBE_U = 96.0
MOVING_UPS = 100.0


def _floor_below(pts: np.ndarray, depth: float = DOWN_PROBE_U, step: float = 8.0) -> np.ndarray:
    """Depth of the floor under each point, or ``depth`` where none is found within reach."""
    import rex_env

    zs = np.arange(0.0, -depth - step, -step, dtype=np.float32)
    grid = pts[:, None, :] + np.stack(
        [np.zeros_like(zs), np.zeros_like(zs), zs], 1)[None, :, :]
    flat = np.ascontiguousarray(grid.reshape(-1, 3), np.float32)
    open_ = rex_env.PyVecEnv.points_open(MAP, flat).reshape(len(pts), len(zs))
    # The floor is the first level at which the hull stops fitting, walking downwards.
    blocked = ~open_
    hit = blocked.any(1)
    d = np.where(hit, -zs[blocked.argmax(1)], depth)
    return d.astype(np.float32)


def edge_ahead(pos: np.ndarray, vel_xy: np.ndarray) -> np.ndarray:
    """Distance to the first drop of :data:`EDGE_DROP_U` along the direction of travel.

    Returns :data:`PROBE_MAX_U` where the ground stays solid for the whole probe.
    """
    n = np.linalg.norm(vel_xy, axis=1, keepdims=True)
    d = np.divide(vel_xy, n, out=np.zeros_like(vel_xy), where=n > 1e-3)
    steps = np.arange(PROBE_STEP_U, PROBE_MAX_U + PROBE_STEP_U, PROBE_STEP_U, dtype=np.float32)
    out = np.full(len(pos), PROBE_MAX_U, np.float32)

    here = _floor_below(pos.astype(np.float32))
    for s in steps:
        p = pos.copy()
        p[:, :2] += d * s
        drop = _floor_below(p.astype(np.float32))
        # Only the first edge counts, so points already resolved are frozen.
        fresh = (out >= PROBE_MAX_U) & (drop - here >= EDGE_DROP_U)
        out[fresh] = s
    return out


def takeoffs(states: np.ndarray) -> np.ndarray:
    """Indices where a human left the ground: a sample whose vertical speed turns sharply positive.

    Demo samples carry no ground flag, so the takeoff is read off the vertical velocity the same way
    `human_paths.restart_states` derives it — a rise of at least half a jump's initial speed between
    consecutive samples, with the previous sample not already climbing.
    """
    vz = states[:, 5]
    rise = (vz[1:] >= 0.5 * 270.0) & (vz[:-1] < 0.5 * 270.0)
    return np.flatnonzero(rise) + 1


def conditional(states: np.ndarray, lead_ticks: int = 6) -> tuple[int, int]:
    """Of the moving samples with an edge close ahead, how many are already committed to the air?

    The unconditional question — *do takeoffs happen at edges* — comes back diluted, because most
    takeoffs in QuakeWorld are bunny hops on flat ground: two a second, nothing to do with geometry.
    The question the policy actually has to answer is the converse. Standing at an edge, does the
    demonstrator leave the ground? Committed means airborne now or taking off within `lead_ticks`.
    """
    sp = np.linalg.norm(states[:, 3:5], axis=1)
    moving = np.flatnonzero(sp >= MOVING_UPS)
    if not moving.size:
        return 0, 0
    e = edge_ahead(states[moving, :3], states[moving, 3:5])
    at_edge = moving[e < 48.0]
    if not at_edge.size:
        return 0, 0
    vz = states[:, 5]
    ti = set(takeoffs(states).tolist())
    committed = 0
    for i in at_edge:
        if vz[i] > 30.0 or any((i + k) in ti for k in range(lead_ticks + 1)):
            committed += 1
    return committed, int(at_edge.size)


def main() -> None:
    rows = []
    print(f"{'rutt':22s} {'avstamp':>8} {'kant<48u':>9} {'övriga':>8} {'kant<48u':>9} {'kvot':>6}")
    all_t, all_o, cond = [], [], []
    for r in race.training_routes():
        t_d, o_d = [], []
        for rec in race.human_paths_for(r, 10_000):
            s = np.asarray(rec["restart_states"], np.float32)
            if len(s) < 6:
                continue
            sp = np.linalg.norm(s[:, 3:5], axis=1)
            ti = takeoffs(s)
            ti = ti[sp[ti] >= MOVING_UPS]
            others = np.setdiff1d(np.flatnonzero(sp >= MOVING_UPS), ti)
            if not ti.size:
                continue
            for idx, sink in ((ti, t_d), (others, o_d)):
                if idx.size:
                    sink.append(edge_ahead(s[idx, :3], s[idx, 3:5]))
        cm, ce = 0, 0
        for rec in race.human_paths_for(r, 10_000):
            s = np.asarray(rec["restart_states"], np.float32)
            if len(s) >= 6:
                a_, b_ = conditional(s)
                cm += a_
                ce += b_
        cond.append((r.name, cm, ce))
        if not t_d:
            continue
        t = np.concatenate(t_d)
        o = np.concatenate(o_d) if o_d else np.zeros(0, np.float32)
        pt = float((t < 48.0).mean())
        po = float((o < 48.0).mean()) if o.size else float("nan")
        rows.append({"route": r.name, "n_takeoffs": int(t.size), "n_other": int(o.size),
                     "takeoff_frac_edge_within_48u": round(pt, 4),
                     "other_frac_edge_within_48u": round(po, 4),
                     "takeoff_median_edge_u": round(float(np.median(t)), 1),
                     "other_median_edge_u": round(float(np.median(o)), 1) if o.size else None})
        all_t.append(t)
        all_o.append(o)
        print(f"{r.name:22s} {t.size:8d} {pt * 100:8.1f}% {o.size:8d} {po * 100:8.1f}% "
              f"{pt / po if po else float('inf'):6.2f}")

    T, O = np.concatenate(all_t), np.concatenate(all_o)
    pt, po = float((T < 48.0).mean()), float((O < 48.0).mean())
    print(f"\n{'ALLA':22s} {T.size:8d} {pt * 100:8.1f}% {O.size:8d} {po * 100:8.1f}% "
          f"{pt / po if po else float('inf'):6.2f}")
    print(f"median kant framför: avstamp {np.median(T):.0f} u, övriga {np.median(O):.0f} u")

    print(f"\n{'rutt':22s} {'vid kant':>9} {'i luften/hoppar':>16}")
    tm = te = 0
    for name, cm, ce in cond:
        tm += cm
        te += ce
        print(f"{name:22s} {ce:9d} {cm / ce * 100 if ce else 0:15.1f}%")
    print(f"{'ALLA':22s} {te:9d} {tm / te * 100 if te else 0:15.1f}%")

    out = Path("/home/benjamin-adm/rex-ml/evidence/edge_signal.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "question": "do human takeoffs sit at ground edges the observation cannot see?",
        "method": {"edge_drop_u": EDGE_DROP_U, "probe_max_u": PROBE_MAX_U,
                   "probe_step_u": PROBE_STEP_U, "moving_ups": MOVING_UPS},
        "overall": {"n_takeoffs": int(T.size), "n_other": int(O.size),
                    "takeoff_frac_edge_within_48u": round(pt, 4),
                    "other_frac_edge_within_48u": round(po, 4),
                    "takeoff_median_edge_u": round(float(np.median(T)), 1),
                    "other_median_edge_u": round(float(np.median(O)), 1)},
        "at_edge_conditional": {"note": "of moving samples with an edge within 48 u ahead, the "
                               "share already airborne or taking off within 6 samples",
                               "n": te, "committed_frac": round(tm / te, 4) if te else None,
                               "per_route": [{"route": n, "n_at_edge": e,
                                              "committed_frac": round(c / e, 4) if e else None}
                                             for n, c, e in cond]},
        "routes": rows}, indent=1))
    print(f"\nskrev {out}")


if __name__ == "__main__":
    main()
