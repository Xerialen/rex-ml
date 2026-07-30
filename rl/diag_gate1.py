"""Beteendediagnostik för en Gate 1-checkpoint: VAR vinns/förloras farten?

    PYTHONPATH=. sim/.venv-sf/bin/python -m rl.diag_gate1 \
        pipeline/out/rl/train_dir/<experiment> [--out evidence/...json]

Kör en greedy-episod på qwsim och mäter strafe-mekanikens beståndsdelar,
jämförbara mot det analytiska takets körning (evidence/strafe_ceiling_100m.json:
peak 821.4, frac_airborne 0.80, median_time 7.94 s):
  - luftandel, hoppkadens (ticks mellan hopp), marktid per kontakt
  - |dyaw| i luften (medel/max) och teckenbyten (half-beat-frekvens)
  - fartvinst per lufttid-segment (u/s per hopp-cykel) och förluster vid landning
"""
from __future__ import annotations

import argparse
import json
import types
from pathlib import Path

import numpy as np
import torch

from rl.eval_gate1 import load_policy
from rl.sf_env import QWGate1Env


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("exp_dir", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    cfg, _, ac = load_policy(args.exp_dir, "cpu")
    env = QWGate1Env("qw_gate1", types.SimpleNamespace(qw_backend="qwsim"))
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
        rows.append((float(np.hypot(c.vel[0], c.vel[1])), float(a[0]), bool(c.onground),
                     int(a[4]) if len(a) > 4 else 0))
        done = term or trunc

    sp = np.array([r[0] for r in rows])
    dyaw = np.array([r[1] for r in rows])
    ong = np.array([r[2] for r in rows])
    air = ~ong
    # hoppcykler: markkontaktsegment
    ground_starts = np.flatnonzero(ong & ~np.roll(ong, 1))
    ground_lens = []
    for gs in ground_starts:
        n = 0
        while gs + n < len(ong) and ong[gs + n]:
            n += 1
        ground_lens.append(n)
    sign_flips = int(np.sum(np.abs(np.diff(np.sign(dyaw[air]))) > 0)) if air.sum() > 2 else 0
    # fartdelta vid landning (tick före markkontakt -> första markticken)
    land_losses = [float(sp[g - 1] - sp[g]) for g in ground_starts if g > 0]

    diag = {
        "experiment": str(args.exp_dir),
        "ticks": len(rows), "peak": float(sp.max()), "final": float(sp[-1]),
        "frac_airborne": float(air.mean()),
        "ref_analytic": {"peak": 821.4, "frac_airborne": 0.80},
        "ground_contacts": len(ground_lens),
        "ground_ticks_median": float(np.median(ground_lens)) if ground_lens else None,
        "abs_dyaw_air_mean": float(np.abs(dyaw[air]).mean()) if air.any() else None,
        "abs_dyaw_air_max": float(np.abs(dyaw[air]).max()) if air.any() else None,
        "halfbeat_sign_flips_per_s": sign_flips / (len(rows) * 0.013),
        "landing_loss_median_u": float(np.median(land_losses)) if land_losses else None,
        "landing_loss_max_u": float(np.max(land_losses)) if land_losses else None,
        "speed_p50_last_2s": float(np.median(sp[-154:])),
    }
    print(json.dumps(diag, indent=1))
    if args.out:
        json.dump(diag, open(args.out, "w"), indent=1)


if __name__ == "__main__":
    main()
