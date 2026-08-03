"""Fartbandsdiagnostik (ultracode-kritikerns steg 1, ägargodkänd workflow):
mät NUVARANDE policy från kantavstamps-states UTAN träning — lyckandegrad per
initialfart 250-500. Separerar 'fel initialtillstånd' från 'oförmögen luftstyrning'.
Rör inget i rl/ — ren mätning."""
import json
import sys
import types

import numpy as np
import torch
torch.set_num_threads(2)

from rl.sf_env import QWGate2Env
from rl.dump_trajectories import load_policy

STATES = json.load(open(sys.argv[1]))["states"]
EXP = sys.argv[2]
OUT = sys.argv[3]

BANDS = [250, 300, 350, 400, 450, 500]
JITTER = [(0.0, 0), (-8.0, -10), (8.0, 10)]  # (pos-u längs yaw-normal, fart-delta)
MAX_STEPS = 160          # ~4.2 s
LAND_R = 130.0
PIT_Z = -50.0

from pathlib import Path
cfg, _, ac = load_policy(Path(EXP), "cpu")
env = QWGate2Env("qw_gate2", types.SimpleNamespace(qw_backend="qwsim"))
from sample_factory.model.model_utils import get_rnn_size

results = []
for st in STATES:
    pos0 = np.array(st["pos"], dtype=float)
    yaw = float(st["yaw"])
    land = np.array(st["landing_2d"], dtype=float)
    fwd = np.array([np.cos(np.radians(yaw)), np.sin(np.radians(yaw))])
    nrm = np.array([-fwd[1], fwd[0]])
    for band in BANDS:
        for joff, jspd in JITTER:
            env.reset()
            c = env.core
            p = pos0.copy()
            p[:2] += nrm * joff
            v = np.zeros(3)
            sp = band + jspd
            v[:2] = fwd * sp
            c.pos = p.copy()
            c.vel = v.copy()
            c.yaw = yaw
            c.pitch = 0.0
            c.b.reset(c.pos, c.vel, c.yaw)
            obs = c._obs()
            rnn = torch.zeros([1, get_rnn_size(cfg)])
            outc = "timeout"
            path = []
            for t in range(MAX_STEPS):
                with torch.no_grad():
                    o = ac(ac.normalize_obs({"obs": torch.tensor(obs[None], dtype=torch.float32)}), rnn)
                    rnn = o["new_rnn_states"]
                    dist = ac.action_distribution()
                    parts = []
                    for d in dist.distributions:
                        parts.append(d.means.ravel() if hasattr(d, "means")
                                     else torch.argmax(d.log_probs, dim=-1).float().ravel())
                    a = torch.cat(parts).numpy()
                obs, r, term, trunc, info = env.step(a)
                if t % 2 == 0:
                    path.append([round(float(c.pos[0]), 1), round(float(c.pos[1]), 1),
                                 round(float(c.pos[2]), 1)])
                if c.pos[2] < PIT_Z:
                    outc = "grop"
                    break
                d2 = float(np.hypot(c.pos[0] - land[0], c.pos[1] - land[1]))
                if c.onground and d2 < LAND_R and 40.0 <= c.pos[2] <= 130.0:
                    outc = "landat"
                    break
            results.append({"state": st["namn"], "band": band, "joff": joff,
                            "jspd": jspd, "utfall": outc, "t_s": round(t * 0.026, 2),
                            "slut": [round(float(x), 1) for x in c.pos],
                            "path": path if outc == "landat" else path[-8:]})

agg = {}
for r in results:
    k = (r["state"], r["band"])
    a = agg.setdefault(k, {"landat": 0, "grop": 0, "timeout": 0})
    a[r["utfall"]] += 1
tab = [{"state": s, "band": b, **v} for (s, b), v in sorted(agg.items())]
json.dump({"trials": results, "agg": tab}, open(OUT, "w"), ensure_ascii=False)
for row in tab:
    print(f'{row["state"]:10s} {row["band"]:4d}: landat {row["landat"]}/3  grop {row["grop"]}  timeout {row["timeout"]}')
