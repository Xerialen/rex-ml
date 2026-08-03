"""Närmanalys: per försök, max projektion mot målet (phi) — känsligare än binärt."""
import json, sys, types
import numpy as np
import torch
torch.set_num_threads(2)
from pathlib import Path
from rl.sf_env import QWGate2Env
from rl.dump_trajectories import load_policy

STATES = json.load(open(sys.argv[1]))["states"]
N = int(sys.argv[2]); SEED0 = int(sys.argv[3])
cfg, _, ac = load_policy(Path("pipeline/out/rl/train_dir/gate2_v2"), "cpu")
env = QWGate2Env("qw_gate2", types.SimpleNamespace(qw_backend="qwsim"))
from sample_factory.model.model_utils import get_rnn_size
phis = []
tr = 0
for st in STATES:
    pos0 = np.array(st["pos"], float); yaw = float(st["yaw"])
    land = np.array(st["landing_2d"], float)
    fwd = np.array([np.cos(np.radians(yaw)), np.sin(np.radians(yaw))])
    tv = land - pos0[:2]; d = float(np.hypot(*tv)); u = tv / d
    for k in range(N):
        tr += 1
        torch.manual_seed(SEED0 + tr)
        env.reset(); c = env.core
        c.pos = pos0.copy(); v = np.zeros(3); v[:2] = fwd * 400.0
        c.vel = v; c.yaw = yaw; c.pitch = 0.0
        c.b.reset(c.pos, c.vel, c.yaw)
        obs = c._obs()
        rnn = torch.zeros([1, get_rnn_size(cfg)])
        best = 0.0
        for t in range(140):
            with torch.no_grad():
                o = ac(ac.normalize_obs({"obs": torch.tensor(obs[None], dtype=torch.float32)}), rnn)
                rnn = o["new_rnn_states"]
                dist = ac.action_distribution()
                a = torch.cat([dd.sample().float().ravel() for dd in dist.distributions]).numpy()
            obs, r, term, trunc, info = env.step(a)
            best = max(best, float((c.pos[:2] - pos0[:2]) @ u) / d)
            if c.pos[2] < -50.0 or (c.onground and float(np.hypot(*(c.pos[:2]-land))) < 130 and c.pos[2] >= 40):
                break
        phis.append(round(best, 3))
p = np.array(phis)
print(f"n={len(p)} phi_max: p50 {np.percentile(p,50):.3f} p90 {np.percentile(p,90):.3f} max {p.max():.3f} | >=0.8: {(p>=0.8).sum()} | >=1.0: {(p>=1.0).sum()}")
