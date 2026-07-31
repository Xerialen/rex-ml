"""Sim-referensrulle för bryggdiagnos: samma checkpoint, samma start som
rex-policy-smoke på riktiga servern, per-tick-logg av ALLT som behövs för att
hitta första divergens-ticken mellan qwsim-rullen och server-rullen:

    per tick: pre-step-tillstånd (pos, vel, onground, jump_held),
              kinetik-obsen (obs[81:97]) policyn faktiskt såg,
              greedy-aktionen (box-means RÅA + argmax-huvudena).

    PYTHONPATH=. sim/.venv-sf/bin/python -m rl.ref_rollout_gate1 \
        pipeline/out/rl/train_dir/gate1_v1/harvest/eval_dir --out <ref.jsonl>
"""
from __future__ import annotations

import argparse
import json
import os
import types
from pathlib import Path

os.environ.setdefault("SF_STDDEV_MAX", "1.0")

import numpy as np
import torch

from rl.eval_gate1 import load_policy
from rl.sf_env import QWGate1Env


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("exp_dir", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--ticks", type=int, default=1200)
    args = ap.parse_args(argv)

    cfg, _, ac = load_policy(args.exp_dir, "cpu")
    env = QWGate1Env("qw_gate1", types.SimpleNamespace(qw_backend="qwsim"))
    from sample_factory.model.model_utils import get_rnn_size

    obs, _ = env.reset()
    rnn = torch.zeros([1, get_rnn_size(cfg)])
    c = env.core
    rows = []
    for t in range(args.ticks):
        pre = dict(pos=[round(float(v), 4) for v in c.pos],
                   vel=[round(float(v), 4) for v in c.vel],
                   onground=bool(c.onground), jump_held=bool(c.jump_held),
                   yaw=round(float(c.yaw), 4), pitch=round(float(c.pitch), 4))
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
        rows.append({"tick": t + 1, **pre,
                     "kin": [round(float(v), 5) for v in obs[81:]],
                     "box": [round(float(a[0]), 5), round(float(a[1]), 5)],
                     "fwd": int(a[2]), "side": int(a[3]), "jump": int(a[4]),
                     "speed": round(float(np.hypot(c.vel[0], c.vel[1])), 2)})
        obs, r, term, trunc, info = env.step(a)
        if term or trunc:
            break

    with open(args.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    sp = np.array([r["speed"] for r in rows])
    jumps = sum(r["jump"] for r in rows)
    held = sum(1 for r in rows if r["jump_held"])
    air = sum(1 for r in rows if not r["onground"])
    print(f"{len(rows)} ticks, peak {sp.max():.1f}, mean {sp.mean():.1f}, "
          f"jump_pressed {jumps}, jump_held {held}, air_frac {air/len(rows):.2f}")


if __name__ == "__main__":
    main()
