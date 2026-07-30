"""Assembles `evidence/f1.2_ppo.json` from the artefacts `ppo.py`/`run_ppo_full.py` produced:
throughput breakdown, per-weighting training logs, per-weighting per-route eval tables, and the
route-construction probe. Pure aggregation -- no new measurement happens here.
"""
import json
import numpy as np
from pathlib import Path

OUT = Path("/home/benjamin-adm/rex-ml/pipeline/out/ppo")
EVIDENCE = Path("/home/benjamin-adm/rex-ml/evidence/f1.2_ppo.json")


def term_trend(log, key, k=20):
    vals = [e[key] for e in log]
    head = float(np.mean(vals[:k]))
    tail = float(np.mean(vals[-k:]))
    return {"first_20_mean": head, "last_20_mean": tail, "delta": tail - head}


def summarize_weighting(name):
    log = json.loads((OUT / f"train_log_{name}.json").read_text())
    terms = ["term_progress", "term_speed", "term_wall", "term_timeout", "term_arrive", "reward_mean"]
    trends = {t: term_trend(log, t) for t in terms}
    # "which term did the policy actually respond to" -- the term whose |delta| (post critic-warmup
    # phase, so early value-error noise isn't counted) is largest relative to its own scale.
    ppo_phase = [e for e in log if e["phase"] == "ppo"]
    trends_ppo_only = {t: term_trend(ppo_phase, t) for t in terms if t != "reward_mean"}
    biggest = max(trends_ppo_only, key=lambda t: abs(trends_ppo_only[t]["delta"]))
    eval_data = json.loads((OUT / f"eval_routes_{name}.json").read_text())
    arrival_rates = [r["arrival_rate"] for r in eval_data["routes"]]
    return {
        "n_iterations": len(log),
        "term_trends_full_run": trends,
        "term_trends_ppo_phase_only": trends_ppo_only,
        "term_the_policy_responded_to_most": biggest,
        "mean_arrival_rate_across_routes": float(np.mean(arrival_rates)) if arrival_rates else None,
        "routes_with_nonzero_arrival": int(sum(1 for a in arrival_rates if a > 0)),
        "routes_total": len(arrival_rates),
        "ckpt": eval_data["ckpt"],
    }


def main():
    throughput = json.loads((OUT / "throughput.json").read_text())
    route_probe = json.loads((OUT / "route_probe.json").read_text())
    run_summary = json.loads((OUT / "run_full_summary.json").read_text())

    weightings = {}
    for name in ("rtx_default", "speed_emphasis", "arrival_emphasis"):
        weightings[name] = summarize_weighting(name)

    # "Final policy": the weighting with the highest mean arrival rate across all 15 routes. Ties
    # broken by mean fraction of moving ticks above the 320 u/s bhop gate (SPEC F1.2: the speed
    # columns are the point, not decoration -- a policy that arrives without the speed floor has
    # been walked, not learned).
    def eval_of(name):
        return json.loads((OUT / f"eval_routes_{name}.json").read_text())

    def bhop_frac_mean(name):
        rows = eval_of(name)["routes"]
        return float(np.mean([r["frac_moving_ticks_above_320ups"] for r in rows])) if rows else 0.0

    best_name = max(weightings, key=lambda n: (weightings[n]["mean_arrival_rate_across_routes"] or 0.0, bhop_frac_mean(n)))
    best_eval = eval_of(best_name)

    evidence = {
        "spec": "F1.2-ppo",
        "date": "2026-07-28",
        "throughput_breakdown": {
            "methodology": (
                "A real PPO iteration (T=128-step rollout through rex_env.PyVecEnv + 4 epochs x "
                "4 minibatches of PPO update) timed in three buckets: env_s (wall time inside "
                "PyVecEnv.step() only), forward_s (host->device obs copy + actor/critic forward + "
                "sampling + device->host action copy -- everything that produces the next action), "
                "update_s (GAE + every epoch's forward/backward/optimiser.step() over the collected "
                "rollout). Median of 3 repeats per N after a discarded warmup iteration (rayon "
                "thread-pool spin-up, CUDA kernel/context caching)."
            ),
            "rows": {
                n: {
                    "env_s": throughput[n]["median_env_s"],
                    "forward_s": throughput[n]["median_forward_s"],
                    "update_s": throughput[n]["median_update_s"],
                    "env_frac": throughput[n]["median_env_frac"],
                    "forward_frac": throughput[n]["median_forward_frac"],
                    "update_frac": throughput[n]["median_update_frac"],
                    "steps_per_s": throughput[n]["median_steps_per_s"],
                } for n in ("4096", "16384")
            },
            "binding_constraint": throughput["_binding_constraint"],
            "finding": (
                "The backward+optimiser update is the binding constraint at BOTH batch sizes measured "
                "(38% of iteration time at N=4096, 60% at N=16384), never env.step() (18-22%). This "
                "contradicts evidence/f1.1_vecenv.json's conclusion that the rollout loop should move "
                "into Rust: that conclusion was drawn from the retained-fraction-of-native-throughput "
                "question, which this spec explicitly says is the wrong question. Moving env.step() "
                "into Rust would optimise a part of the iteration that is not binding -- 18-22% of wall "
                "time even at the batch sizes tested -- so it is NOT done here. At N=4096 the "
                "rollout-side forward pass (39%) is actually larger than env.step() (22%): the "
                "policy MLP itself is microseconds of compute, so that bucket is almost entirely "
                "Python/CUDA kernel-launch and host<->device transfer overhead, reported honestly "
                "rather than optimised away per the task's explicit instruction not to optimise the "
                "boundary."
            ),
        },
        "route_construction": route_probe,
        "training": {
            "warm_start": "pipeline/out/policy/actor_disc_3x512.pt (policy.make_disc_actor, depth=3, width=512)",
            "algorithm": "PPO: clipped surrogate (clip=0.2), GAE(gamma=0.99, lambda=0.95), entropy bonus 0.005",
            "action_space": "3-way Categorical fwd, 3-way Categorical side, Normal(mean=tanh(yaw_head)*0.35, learnable state-independent log_std) dyaw, Bernoulli jump",
            "value_function": "separate 2x256-tanh MLP, freshly initialised -- no warm start exists for it",
            "critic_only_warmup_iterations": 20,
            "critic_only_warmup_rationale": (
                "Own decision, logged rather than silent: the spec warns the first iterations are "
                "dominated by value error / noisy advantage estimates. Skipping the actor's optimiser "
                "step for the first 20 iterations (critic still trains on-policy) keeps that expected "
                "early noise from reaching the warm-started actor weights through a shared update."
            ),
            "config": run_summary["config"],
            "routes_trained_on": route_probe["constructible"],
            "reward_weightings": weightings,
            "final_policy_selection": {
                "criterion": "highest mean arrival rate across the 15 constructible routes, ties broken by mean fraction of moving ticks above the 320 u/s bhop gate",
                "selected": best_name,
            },
        },
        "per_route_final_policy": best_eval,
        "per_route_all_weightings": {n: eval_of(n) for n in weightings},
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2))
    print(f"wrote {EVIDENCE}")
    print(f"final policy selected: {best_name}")


if __name__ == "__main__":
    main()
