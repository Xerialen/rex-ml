"""Where do the failing routes actually stop?

`race eval` says six of seven routes arrive 0 % of the time while sustaining 350+ u/s and clearing
the bunny-hop gate on 77-95 % of moving ticks. Fast and lost are very different failures from slow,
and the fix for one is not the fix for the other, so this measures which it is.

No new environment API is needed: `RewardParts::progress` is now arclength advanced along the
planned path per tick, so summing it over an episode gives the arclength the agent reached, and
dividing by `PyVecEnv.path_len` gives the fraction of the route it covered. It also records *when*
that maximum was reached, which separates "walked 40 % of the way and stopped dead" from "walked
40 % of the way and spent the rest of the budget oscillating".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from . import cohort_routes as C
from . import race
from .ppo import PPOActorCritic, actions_to_env, obs_to_state, _torch, S_SCALE

OUT = race.OUT


def probe(ac, route: C.CohortRoute, n: int, dev: str = "cuda") -> dict:
    import rex_env
    torch, _ = _torch()
    env = rex_env.PyVecEnv(race.MAP, route.start, route.target, n, C.ARRIVE_BOX, route.max_ticks)
    L = env.path_len
    obs = env.reset()

    arc = np.zeros(n)
    peak_arc = np.zeros(n)
    peak_tick = np.zeros(n, dtype=np.int64)
    done = np.zeros(n, dtype=bool)
    outcome = np.array(["running"] * n, dtype=object)
    end_tick = np.zeros(n, dtype=np.int64)
    # speed at the moment the run peaked, to tell a stall (speed ~0) from a loop (speed high)
    speed_at_peak = np.zeros(n)

    for t in range(route.max_ticks + 5):
        obs_t = obs_to_state(obs, torch, dev)
        with torch.no_grad():
            f_l, s_l, yaw, j_l = ac.actor(obs_t)
        acts = actions_to_env((f_l.argmax(-1), s_l.argmax(-1), yaw.squeeze(-1),
                               (j_l.squeeze(-1) > 0).float()))
        spd = obs[:, 3] * S_SCALE[3]
        obs, parts, dones = env.step(acts)
        parts = np.asarray(parts)
        live = ~done
        arc[live] += parts[live, 0]
        better = live & (arc > peak_arc)
        peak_arc[better] = arc[better]
        peak_tick[better] = t
        speed_at_peak[better] = spd[better]
        just = live & np.asarray(dones)
        for i in np.flatnonzero(just):
            done[i] = True
            end_tick[i] = t
            outcome[i] = "arrived" if parts[i, 4] > 0 else ("timeout" if parts[i, 3] < 0 else "void")
        if done.all():
            break
    end_tick[~done] = route.max_ticks

    frac = peak_arc / max(L, 1e-6)
    return {
        "name": route.name,
        "path_len_u": round(L, 1),
        "n": n,
        "outcomes": {k: int((outcome == k).sum()) for k in sorted(set(outcome.tolist()))},
        "frac_of_path_reached": {
            "median": round(float(np.median(frac)), 3),
            "p10": round(float(np.percentile(frac, 10)), 3),
            "p90": round(float(np.percentile(frac, 90)), 3),
        },
        "arc_reached_u_median": round(float(np.median(peak_arc)), 1),
        # If the peak is reached early and the episode runs to the deadline, the agent stopped
        # advancing long before it ran out of time — that is a stall or a loop, not slowness.
        "peak_reached_at_frac_of_episode": round(
            float(np.median(peak_tick / np.maximum(end_tick, 1))), 3),
        "speed_at_peak_ups_median": round(float(np.median(speed_at_peak)), 1),
    }


def main():
    ckpt = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT / "race_v1.pt"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 64
    ac = PPOActorCritic(dev="cuda")
    ac.load(ckpt)
    rows = [probe(ac, r, n) for r in race.training_routes()]
    for r in rows:
        print(f"{r['name']:22s} path {r['path_len_u']:7.0f}u  reached "
              f"{r['frac_of_path_reached']['median'] * 100:5.1f}% "
              f"(p10 {r['frac_of_path_reached']['p10'] * 100:4.0f}%, p90 "
              f"{r['frac_of_path_reached']['p90'] * 100:4.0f}%)  peak at "
              f"{r['peak_reached_at_frac_of_episode'] * 100:5.1f}% of episode  "
              f"speed@peak {r['speed_at_peak_ups_median']:5.0f}  {r['outcomes']}", flush=True)
    (OUT / "diag_stall.json").write_text(json.dumps({"ckpt": str(ckpt), "routes": rows}, indent=1))
    print(f"wrote {OUT / 'diag_stall.json'}")


if __name__ == "__main__":
    main()
