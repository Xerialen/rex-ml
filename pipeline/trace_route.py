"""Dump one greedy episode per route: where the agent goes, where it stops, and what the path
wanted it to do there.

`diag_stall.py` established *that* the policy reaches 73-84 % of every route's remaining-distance
and then times out. That is not actionable. This prints the world-space positions, so a stall reads
as a place on the map rather than as a percentage.

The last-25-ticks summary is the part that matters: a stall at 0 u/s against a wall, a stall
circling at 350 u/s, and a stall oscillating on a ledge edge are three different bugs with three
different fixes, and the speed and position spread over the final ticks separates them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from . import cohort_routes as C
from . import race
from .ppo import PPOActorCritic, actions_to_env, obs_to_state, _torch


def trace(ac, route: C.CohortRoute, human_path: dict | None, dev: str = "cuda") -> dict:
    import rex_env
    torch, _ = _torch()
    if human_path is not None:
        env = rex_env.PyVecEnv.from_path(race.MAP, [tuple(p) for p in human_path["path"]], 1,
                                         C.ARRIVE_BOX, route.max_ticks)
        geometry = f"human:{human_path['demo_key']}@{human_path['duration_s']}"
    else:
        env = rex_env.PyVecEnv(race.MAP, route.start, route.target, 1, C.ARRIVE_BOX, route.max_ticks)
        geometry = "navmesh"
    path = env.path
    obs = env.reset()

    pos, vel, acts = [], [], []
    outcome = "unfinished"
    for t in range(route.max_ticks + 2):
        pos.append(env.origins[0].tolist())
        vel.append(env.velocities[0].tolist())
        obs_t = obs_to_state(obs, torch, dev)
        with torch.no_grad():
            f_l, s_l, yaw, j_l = ac.actor(obs_t)
        a = actions_to_env((f_l.argmax(-1), s_l.argmax(-1), yaw.squeeze(-1),
                            (j_l.squeeze(-1) > 0).float()))
        acts.append([float(x) for x in a[0]])
        obs, parts, dones = env.step(a)
        if dones[0]:
            outcome = "arrived" if parts[0][4] > 0 else ("timeout" if parts[0][3] < 0 else "void")
            break

    pos = np.array(pos)
    vel = np.array(vel)
    goal = np.array(path[-1])
    d_goal = np.linalg.norm(pos - goal, axis=1)
    stuck_from = int(np.argmin(d_goal))
    tail = pos[-25:]
    tail_v = np.linalg.norm(vel[-25:, :2], axis=1)
    tail_a = np.array(acts[-25:])

    return {
        "route": route.name,
        "geometry": geometry,
        "outcome": outcome,
        "ticks": len(pos),
        "seconds": round(len(pos) * C.TICK_DT, 2),
        "goal": [round(float(v), 1) for v in goal],
        "closest_approach_u": round(float(d_goal.min()), 1),
        "closest_at_tick": stuck_from,
        "closest_at_s": round(stuck_from * C.TICK_DT, 2),
        "final_pos": [round(float(v), 1) for v in pos[-1]],
        "final_dist_to_goal_u": round(float(d_goal[-1]), 1),
        # Spread of the last 25 positions: near zero means genuinely stuck in place; hundreds of
        # units means running a loop.
        "tail_pos_spread_u": [round(float(v), 1) for v in (tail.max(axis=0) - tail.min(axis=0))],
        "tail_speed_xy_mean": round(float(tail_v.mean()), 1),
        "tail_jump_fraction": round(float((tail_a[:, 3] > 0.5).mean()), 2),
        "tail_fwd_mean": round(float(tail_a[:, 0].mean()), 2),
        "positions_every_10_ticks": [[round(float(v), 0) for v in p] for p in pos[::10]],
    }


def main():
    ckpt = Path(sys.argv[1])
    human_k = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    ac = PPOActorCritic(dev="cuda")
    ac.load(ckpt)
    rows = []
    for r in race.training_routes(human_k=human_k):
        hp = (race.human_paths_for(r, 1) or [None])[0] if human_k else None
        t = trace(ac, r, hp)
        rows.append(t)
        print(f"{t['route']:22s} {t['outcome']:9s} {t['seconds']:6.2f}s  "
              f"closest {t['closest_approach_u']:7.1f}u at {t['closest_at_s']:5.2f}s  "
              f"final {str(t['final_pos']):26s} d={t['final_dist_to_goal_u']:7.1f}u  "
              f"tail spread {str(t['tail_pos_spread_u']):22s} v={t['tail_speed_xy_mean']:6.1f} "
              f"jump={t['tail_jump_fraction']:.2f}", flush=True)
    out = race.OUT / f"trace_{ckpt.stem}.json"
    out.write_text(json.dumps(rows, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
