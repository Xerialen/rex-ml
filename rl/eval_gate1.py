"""Utvärdera en Gate 1-checkpoint: N episoder, peak-fördelning, JSON-rapport.

    PYTHONPATH=. sim/.venv-sf/bin/python -m rl.eval_gate1 \
        pipeline/out/rl/train_dir/<experiment> [--n 30] [--sample] \
        [--backend qwsim|stub] [--out evidence/...json]

Detta är TRÄNINGSSIMMENS utvärdering — den styr utvecklingen men bevisar aldrig
gaten. Gate 1-beviset körs på riktiga mvdsv-servern (RUNBOOK, bevisregeln).
"""
from __future__ import annotations

import argparse
import json
import os
import types
from pathlib import Path

# TRÄNINGSPARITET: träningen kör med SF_STDDEV_MAX=1.0 (stänger pitch-entropi-
# farmningen). Utan samma klämma här samplar evalen med vild pitch och
# UNDERSKATTAR policyn (uppmätt 2026-07-30: 676 vs 748 median). Måste sättas
# FÖRE sample_factory-importerna (klassattribut läses vid import).
os.environ.setdefault("SF_STDDEV_MAX", "1.0")

import numpy as np
import torch

from sample_factory.algo.learning.learner import Learner
from sample_factory.algo.utils.make_env import BatchedVecEnv  # noqa: F401 (SF-import kedjar moduler)
from sample_factory.cfg.arguments import load_from_checkpoint
from sample_factory.model.actor_critic import create_actor_critic
from sample_factory.utils.attr_dict import AttrDict

from rl.sf_env import QWGate1Env


def load_policy(exp_dir: Path, device: str):
    import gymnasium as gym
    # torch>=2.6 weights_only-default stoppar numpy-skalärer i SF-checkpoints;
    # filerna är våra egna (train_dir) — allowlista typen
    import numpy.core.multiarray
    torch.serialization.add_safe_globals([numpy.core.multiarray.scalar,
                                          np.dtype, np.dtypes.Float64DType])
    raw = json.load(open(exp_dir / "config.json"))
    cfg = AttrDict(raw.get("cfg", raw))
    # STUB här: envn behövs bara för obs/action-RUMMEN (backend-oberoende), och
    # qwsim tillåter en karta per process — en 100m-laddning här hade blockerat
    # gate2-evalens dm3. Anroparen bygger sin egen riktiga miljö.
    env = QWGate1Env("qw_gate1", types.SimpleNamespace(qw_backend="stub"))
    # SF wrappar platta Box-observationer i Dict({"obs": ...}) internt
    obs_space = gym.spaces.Dict({"obs": env.observation_space})
    actor_critic = create_actor_critic(cfg, obs_space, env.action_space)
    actor_critic.eval()
    actor_critic.model_to_device(device)
    ckpts = Learner.get_checkpoints(exp_dir / "checkpoint_p0", "checkpoint_*")
    ckpt = Learner.load_checkpoint(ckpts, device)
    actor_critic.load_state_dict(ckpt["model"])
    return cfg, env, actor_critic


def run_episodes(env: QWGate1Env, actor_critic, cfg, n: int, device: str,
                 sample: bool) -> list[dict]:
    from sample_factory.model.model_utils import get_rnn_size
    results = []
    for ep in range(n):
        obs, _ = env.reset()
        rnn_states = torch.zeros([1, get_rnn_size(cfg)], dtype=torch.float32,
                                 device=device)
        done = False
        info = {}
        while not done:
            with torch.no_grad():
                obs_t = {"obs": torch.tensor(obs[None], device=device)}
                normalized = actor_critic.normalize_obs(obs_t)
                policy_out = actor_critic(normalized, rnn_states)
                rnn_states = policy_out["new_rnn_states"]
                if sample:
                    action = policy_out["actions"]
                else:
                    # SF:s TupleActionDistribution.argmax kraschar på blandade
                    # kontinuerliga+diskreta huvuden (2D-means vs 1D-argmax) —
                    # ta greedy-handlingen manuellt per delfördelning.
                    dist = actor_critic.action_distribution()
                    parts = []
                    for d in dist.distributions:
                        if hasattr(d, "means"):
                            parts.append(d.means.ravel())
                        else:
                            parts.append(torch.argmax(d.log_probs, dim=-1).float().ravel())
                    action = torch.cat(parts)
            a = action.cpu().numpy().ravel()
            obs, r, term, trunc, info = env.step(a)
            done = term or trunc
        results.append({"peak_speed": round(info["peak_speed"], 1),
                        "stage": info["stage"]})
    return results


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("exp_dir", type=Path)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--sample", action="store_true", help="sampla i stället för argmax")
    ap.add_argument("--backend", default=None, choices=[None, "qwsim", "stub"])
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    cfg, _spaces_env, actor_critic = load_policy(args.exp_dir, args.device)
    # load_policy ger en STUB-env (bara rummen) — bygg alltid riktiga miljön här
    backend = args.backend or cfg.get("qw_backend", "qwsim")
    env = QWGate1Env("qw_gate1", types.SimpleNamespace(qw_backend=backend))
    res = run_episodes(env, actor_critic, cfg, args.n, args.device, args.sample)
    peaks = np.array([r["peak_speed"] for r in res])
    summary = {
        "experiment": str(args.exp_dir), "n": args.n,
        "mode": "sample" if args.sample else "greedy",
        "peak_median": float(np.median(peaks)), "peak_max": float(peaks.max()),
        "peak_p10": float(np.percentile(peaks, 10)),
        "episodes": res,
    }
    print(json.dumps({k: v for k, v in summary.items() if k != "episodes"}, indent=1))
    if args.out:
        json.dump(summary, open(args.out, "w"), indent=1)
        print("skrev", args.out)


if __name__ == "__main__":
    main()
