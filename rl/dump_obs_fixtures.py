"""Dumpa (tillstånd → observationsvektor)-fixturer ur qwsim-miljön.

Rust-sidans obs-byggare (bevisbryggan i rtx-boten) MÅSTE reproducera exakt
samma 97-vektor ur samma spelartillstånd — annars är policyn blind på riktiga
servern (sim2real-obs-gap). Fixturerna är facit:

    .venv/bin/python -m rl.dump_obs_fixtures --out pipeline/out/rl/obs_fixtures_100m.npz

Innehåll per tick: pos, vel, yaw, pitch, onground, waterlevel, jump_held,
last_action(6) samt obs(97). Körningen är en skriptad grov bunny på 100m så
fixturerna täcker mark, luft, hopp och fart över 320.
"""
from __future__ import annotations

import argparse

import numpy as np

from rl import spec as S
from rl.env import EpisodeConfig, QWEnvCore
from rl.qwsim_backend import QwsimBackend
from rl.rewards_gate1 import Curriculum


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--ticks", type=int, default=400)
    args = ap.parse_args(argv)

    env = QWEnvCore(QwsimBackend(map_name="100m"), Curriculum(),
                    cfg=EpisodeConfig(max_ticks=args.ticks + 10))
    obs = env.reset()
    rows = {k: [] for k in ("pos", "vel", "yaw", "pitch", "onground",
                            "waterlevel", "jump_held", "last_action", "obs")}
    side, sgn = 2, +1
    for t in range(args.ticks):
        rows["pos"].append(env.pos.copy())
        rows["vel"].append(env.vel.copy())
        rows["yaw"].append(env.yaw)
        rows["pitch"].append(env.pitch)
        rows["onground"].append(env.onground)
        rows["waterlevel"].append(env.waterlevel)
        rows["jump_held"].append(env.jump_held)
        rows["last_action"].append(env.last_action.copy())
        rows["obs"].append(obs.copy())
        if t % 38 == 0 and t > 0:
            side, sgn = (1, -1) if side == 2 else (2, +1)
        obs, _, done, _ = env.step(
            np.array([sgn * 6.0 / S.MAX_DYAW_DEG, 0.0]),
            fwd=1 if t < 20 else 0, side=side, jump=1 if env.onground else 0)
        if done:
            break
    np.savez_compressed(args.out, **{k: np.asarray(v) for k, v in rows.items()})
    peaks = np.hypot(np.asarray(rows["vel"])[:, 0], np.asarray(rows["vel"])[:, 1])
    print(f"skrev {args.out}: {len(rows['obs'])} ticks, peakfart {peaks.max():.1f}, "
          f"luftandel {1 - np.mean(rows['onground']):.2f}")


if __name__ == "__main__":
    main()
