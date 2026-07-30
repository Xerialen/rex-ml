"""Driver for the full SPEC F1.2 training + eval sweep. Run in the background; not itself part of
the spec's deliverables (those are `ppo.py`'s bench/train/eval and `evidence/f1.2_ppo.json`).
"""
import json
import time
from pathlib import Path

from pipeline import ppo

OUT = ppo.OUT
LOG = OUT / "run_full.log"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    LOG.write_text("")
    specs = ppo.load_goto_scenarios()
    ok_specs, failed = ppo.probe_constructible(specs)
    log(f"routes: {len(ok_specs)} constructible, {len(failed)} failed to construct")
    for fd in failed:
        log(f"  CONSTRUCTION FAILURE {fd['name']}: {fd['error']}")
    (OUT / "route_probe.json").write_text(json.dumps(
        {"constructible": [s.name for s in ok_specs], "failed": failed}, indent=2))

    ITERATIONS = 800
    N_PER_ROUTE = 256
    T = 128
    EPOCHS = 4
    MINIBATCHES = 8
    CRITIC_WARMUP = 20

    train_results = {}
    for name, weights in ppo.REWARD_WEIGHTINGS.items():
        log(f"=== training {name}: {weights} ===")
        t0 = time.time()
        res = ppo.train_one_weighting(
            name, weights, ok_specs, iterations=ITERATIONS, n_per_route=N_PER_ROUTE,
            T=T, epochs=EPOCHS, minibatches=MINIBATCHES, critic_warmup_iters=CRITIC_WARMUP,
        )
        dt = time.time() - t0
        log(f"=== {name} done in {dt:.0f}s -> {res['ckpt']} ===")
        train_results[name] = {"ckpt": res["ckpt"], "seconds": dt}

    eval_results = {}
    for name in ppo.REWARD_WEIGHTINGS:
        log(f"=== evaluating {name} ===")
        ckpt = OUT / f"ppo_actor_{name}.pt"
        res = ppo.evaluate_all(ckpt, n_episodes=30, out_name=f"eval_routes_{name}.json")
        eval_results[name] = res
        log(f"=== eval {name} done ===")

    (OUT / "run_full_summary.json").write_text(json.dumps(
        {"train": train_results, "config": dict(
            iterations=ITERATIONS, n_per_route=N_PER_ROUTE, T=T, epochs=EPOCHS,
            minibatches=MINIBATCHES, critic_warmup_iters=CRITIC_WARMUP)}, indent=2))
    log("ALL DONE")


if __name__ == "__main__":
    main()
