"""Short diagnostic run: does the collapse-to-standing-still go away?

The first full run failed in a way worth naming precisely. Every one of the three
weightings kept `wall = 1.0`, so a single contact tick cost as much as fifty ticks
of maximum speed, while arrival was unreachable without first surviving the
exploration that earns contacts. The optimum was therefore to stop moving, and the
policy found it: the speed term fell from 0.39 with the frozen BC actor to 0.10
within twenty PPO iterations, arrivals stayed at 0.0000, and entropy went from
+0.09 to -1.3 and never recovered.

Two causes, two changes, and this run tests both at once because they are not
separable — a policy that has already gone deterministic cannot exploit a better
reward, and a policy with a pathological reward will go deterministic no matter how
much entropy is encouraged:

  * `explore` weights the wall penalty at 0.02 instead of 1.0. Zero wall contact is
    an acceptance criterion in the owner's protocol, verified over 20 consecutive
    runs at evaluation. It is not a per-tick training signal, and using it as one
    teaches the policy never to try.
  * the entropy coefficient goes from 0.005 to 0.02. Across four action heads,
    0.005 was not enough to keep the policy stochastic for even twenty iterations.

Short on purpose: 150 iterations answers whether the collapse is gone. It does not
answer whether the routes get solved, and this run is not evidence about that.
"""

import json
import time
from pathlib import Path

from pipeline import ppo

OUT = Path(__file__).resolve().parent / "out" / "ppo"
ITERATIONS = 150
N_PER_ROUTE = 256
T = 128


def main():
    specs = ppo.load_goto_scenarios()
    ok_specs, _ = ppo.probe_constructible(specs)
    # A handful of routes, not all fifteen: this is a diagnostic, and a narrow route
    # set makes the collapse (or its absence) visible without waiting on the tail.
    keep = {"ra_climb", "ring_to_ratop", "ralow_to_ratop", "window_to_rl"}
    specs = [s for s in ok_specs if s.name in keep] or ok_specs[:4]
    print(f"diagnostic on {[s.name for s in specs]}", flush=True)

    t0 = time.time()
    res = ppo.train_one_weighting(
        "sprint", ppo.REWARD_WEIGHTINGS["sprint"], specs,
        iterations=ITERATIONS, n_per_route=N_PER_ROUTE, T=T,
        ent_coef=0.02, living_cost=ppo.LIVING_COST["sprint"],
        ckpt_name="ppo_actor_diag_sprint.pt",
    )
    log = res["log"] if isinstance(res, dict) and "log" in res else res
    (OUT / "diag_sprint.json").write_text(json.dumps(
        {"iterations": ITERATIONS, "ent_coef": 0.02, "living_cost": ppo.LIVING_COST["sprint"],
         "weights": ppo.REWARD_WEIGHTINGS["sprint"].vec().tolist(),
         "routes": [s.name for s in specs], "wall_s": round(time.time() - t0, 1),
         "log": log}, indent=1, default=float))
    print("wrote out/ppo/diag_sprint.json", flush=True)


if __name__ == "__main__":
    main()
