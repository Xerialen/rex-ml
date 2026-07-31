"""Beteendediagnostik för Gate 2 (dm3 fritt strövande): teknik mot mänsklig profil.

    PYTHONPATH=. sim/.venv-sf/bin/python -m rl.diag_gate2 \
        pipeline/out/rl/train_dir/<experiment> [--n 10] [--out evidence/...json]

Mäter samma storheter som analystens mänskliga högfartsprofil
(evidence/human_sustained_speed_dm3.md, runs ≥450: luftandel p50 0,93,
hoppkadens ~1,0/s, landningsförlust median −13,5 u/s, "över ~450 finns bara
luftvägen"). Diagnosen svarar på: kryssar policyn på marken (teknikbrist) eller
bunnyhoppar den redan (då är platån navigations-/geometribunden)?
"""
from __future__ import annotations

import argparse
import json
import os
import types
from pathlib import Path

os.environ.setdefault("SF_STDDEV_MAX", "1.0")   # träningsparitet, se eval_gate1

import numpy as np
import torch

from rl.eval_gate1 import load_policy
from rl.sf_env import QWGate2Env


def run_episode(env, ac, cfg):
    from sample_factory.model.model_utils import get_rnn_size
    obs, _ = env.reset()
    rnn = torch.zeros([1, get_rnn_size(cfg)])
    rows = []
    done = False
    while not done:
        with torch.no_grad():
            out = ac(ac.normalize_obs({"obs": torch.tensor(obs[None])}), rnn)
            rnn = out["new_rnn_states"]
            dist = ac.action_distribution()
            parts = []
            for d in dist.distributions:
                if hasattr(d, "means"):
                    parts.append(d.means.ravel())
                else:
                    parts.append(torch.argmax(d.log_probs, dim=-1).float().ravel())
            a = torch.cat(parts).numpy()
        obs, r, term, trunc, info = env.step(a)
        c = env.core
        rows.append((float(np.hypot(c.vel[0], c.vel[1])), bool(c.onground),
                     int(a[4]) if len(a) > 4 else 0))
        done = term or trunc
    return rows, info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("exp_dir", type=Path)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    cfg, _, ac = load_policy(args.exp_dir, "cpu")
    env = QWGate2Env("qw_gate2", types.SimpleNamespace(qw_backend="qwsim"))

    sp_all, ong_all, jump_all, land_all = [], [], [], []
    ep_stats = []
    for ep in range(args.n):
        rows, info = run_episode(env, ac, cfg)
        sp = np.array([r[0] for r in rows])
        ong = np.array([r[1] for r in rows])
        jmp = np.array([r[2] for r in rows])
        ground_starts = np.flatnonzero(ong & ~np.roll(ong, 1))
        land = [float(sp[g] - sp[g - 1]) for g in ground_starts if g > 0]
        sp_all.append(sp); ong_all.append(ong); jump_all.append(jmp); land_all += land
        # teknik i högfartsregimen: tickar där policyn redan är över 400
        hi = sp > 400.0
        ep_stats.append({
            "mean_speed": float(sp.mean()), "peak": float(sp.max()),
            "frac_airborne": float((~ong).mean()),
            "frac_airborne_over400": float((~ong)[hi].mean()) if hi.any() else None,
            "frac_ticks_over450": float((sp > 450.0).mean()),
            "stuck": bool(info.get("stuck", False)),
        })

    sp = np.concatenate(sp_all); ong = np.concatenate(ong_all)
    jmp = np.concatenate(jump_all)
    hi = sp > 400.0
    jumps_per_s = float(np.sum(np.diff(jmp) > 0)) / (len(jmp) * 0.013)
    diag = {
        "experiment": str(args.exp_dir), "episodes": args.n, "ticks": int(len(sp)),
        "speed_mean": float(sp.mean()), "speed_p50": float(np.median(sp)),
        "speed_p99": float(np.percentile(sp, 99)), "peak": float(sp.max()),
        "frac_ticks_over450": float((sp > 450.0).mean()),
        "frac_ticks_over500": float((sp > 500.0).mean()),
        "frac_airborne": float((~ong).mean()),
        "frac_airborne_over400": float((~ong)[hi].mean()) if hi.any() else None,
        "jumps_per_s": jumps_per_s,
        "landing_dv_median_u": float(np.median(land_all)) if land_all else None,
        "landing_dv_p10_u": float(np.percentile(land_all, 10)) if land_all else None,
        "human_ref_over450": {"frac_airborne": 0.93, "jumps_per_s": 1.0,
                              "landing_dv_median_u": -13.5},
        "episodes_detail": ep_stats,
    }
    print(json.dumps(diag, indent=1))
    if args.out:
        json.dump(diag, open(args.out, "w"), indent=1)


if __name__ == "__main__":
    main()
