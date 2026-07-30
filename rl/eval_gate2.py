"""Utvärdera en checkpoint mot Gate 2-formeln: N fri-strövningskörningar på dm3,
GateScore-ackumulering (T(v), OPEN-medel, täckning) + fastnad-räkning.

    PYTHONPATH=. sim/.venv-sf/bin/python -m rl.eval_gate2 \
        pipeline/out/rl/train_dir/<experiment> [--n 30] [--sample] \
        [--backend qwsim|stub] [--out evidence/...json]

Träningssimmens mätning — gateBEVISET körs på riktiga mvdsv (bevisregeln).
Obs/action-rummen är identiska med Gate 1, så laddningen delas (rl/eval_gate1).
"""
from __future__ import annotations

import argparse
import json
import types
from pathlib import Path

import numpy as np
import torch

from rl.eval_gate1 import load_policy
from rl.sf_env import QWGate2Env
from rl.zones import GateScore, RASTER, ZoneRaster


def run_freeroam(env: QWGate2Env, actor_critic, cfg, n: int, device: str,
                 sample: bool, gs: GateScore | None) -> list[dict]:
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
                normalized = actor_critic.normalize_obs(
                    {"obs": torch.tensor(obs[None], device=device)})
                policy_out = actor_critic(normalized, rnn_states)
                rnn_states = policy_out["new_rnn_states"]
                if sample:
                    action = policy_out["actions"]
                else:
                    dist = actor_critic.action_distribution()
                    parts = []
                    for d in dist.distributions:
                        if hasattr(d, "means"):
                            parts.append(d.means.ravel())
                        else:
                            parts.append(torch.argmax(d.log_probs, dim=-1).float().ravel())
                    action = torch.cat(parts)
            obs, r, term, trunc, info = env.step(action.cpu().numpy().ravel())
            if gs is not None:
                gs.tick(env.core.pos, float(np.hypot(env.core.vel[0], env.core.vel[1])))
            done = term or trunc
        results.append({"stuck": bool(info["stuck"]),
                        "mean_speed_counted": round(info["mean_speed_counted"], 1),
                        "novel_voxels": info["novel_voxels"]})
    return results


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("exp_dir", type=Path)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--backend", default=None, choices=[None, "qwsim", "stub"])
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    cfg, _, actor_critic = load_policy(args.exp_dir, args.device)
    backend = args.backend or cfg.get("qw_backend", "qwsim")
    env = QWGate2Env("qw_gate2", types.SimpleNamespace(qw_backend=backend))
    gs = GateScore(ZoneRaster()) if RASTER.exists() else None

    res = run_freeroam(env, actor_critic, cfg, args.n, args.device, args.sample, gs)
    summary = {
        "experiment": str(args.exp_dir), "n": args.n, "backend": backend,
        "mode": "sample" if args.sample else "greedy",
        "stuck_episodes": int(sum(r["stuck"] for r in res)),
        "gate": gs.summary() if gs else None,
        "gate_passed_sim": bool(gs.passed()) if gs else None,
        "episodes": res,
    }
    print(json.dumps({k: v for k, v in summary.items() if k != "episodes"}, indent=1))
    if args.out:
        json.dump(summary, open(args.out, "w"), indent=1)
        print("skrev", args.out)


if __name__ == "__main__":
    main()
