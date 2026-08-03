"""Empirisk validering av flerhoppsregimen + rutt-spawn mot RIKTIGA qwsim/dm3
(skeptikerfynd 6-läxan: stubbtester bevisar fel sak — mät på riktiga geometrin).

    PYTHONPATH=. sim/.venv-sf/bin/python evidence/repro/validate_multihop_route.py

Mäter (nollpolicy — inga aktioner):
A) RUTT-SPAWN per tredjedel av banan (tidig/mitt/sen): fullbordan/grop/camp/
   timeout + att stegreward är EXAKT 0 utan shaping (fynd 2-fixen).
B) KANTSPAWN under multihop: episodlängd (campen ska ge snabb omsättning),
   ingen krasch, terminal-flaggan satt.
Facit som eftersöks: sen tredjedel auto-fullbordar ofta (lätt ände), tidig
gör det INTE (curriculum-gradient finns — fynd 1-fixen), grop terminerar.
"""
import json
import types
from collections import Counter

import numpy as np

from rl.sf_env import QWGate2Env, _takeoff_states, _route_states

RS = _route_states()
N_PER = 4


def make(**kw):
    cfg = types.SimpleNamespace(qw_backend="qwsim", qw_vertical_rewards=True,
                                qw_takeoff_multihop=True, qw_climb_coef=0.5,
                                qw_gap_base=3.0, qw_height_coef=1.5,
                                qw_prog_shaping=0.0, **kw)
    return QWGate2Env("qw_gate2", cfg, spawn_takeoff_states=_takeoff_states(),
                      max_ticks=77 * 12)


def run_zero_episode(env):
    env.core.reset()
    a = (np.zeros(2, dtype=np.float32), 0, 0, 0)
    tot, nonzero_steps = 0.0, 0
    for t in range(env.core.cfg.max_ticks + 2):
        _, r, done, info = env.core.step(np.zeros(2, dtype=np.float32), 0, 0, 0)
        tot += r
        if r != 0.0:
            nonzero_steps += 1
        if done:
            return info, t + 1, tot, nonzero_steps
    return info, env.core.cfg.max_ticks, tot, nonzero_steps


# A) rutt-spawn: styr valet av state via rng-patch — mät per tredjedel
env = make(qw_takeoff_air_frac=1.0)
env.core.cfg.route_states = RS
n = len(RS)
tred = {"tidig": range(0, n // 3), "mitt": range(n // 3, 2 * n // 3),
        "sen": range(2 * n // 3, n)}
res = {}
for namn, idxr in tred.items():
    utfall = Counter(); tot_nonzero = 0
    for i in idxr:
        for k in range(N_PER):
            class FixedRng:
                def __init__(self, i):
                    self.i = i
                    self._r = np.random.default_rng(1000 + i * 7 + k)
                def integers(self, m):
                    return self.i
                def random(self):
                    return 0.0            # < air_frac ⇒ alltid rutt-spawn
                def uniform(self, *a, **kw):
                    return self._r.uniform(*a, **kw)
            env.core.rng = FixedRng(i)
            info, ticks, tot, nz = run_zero_episode(env)
            tot_nonzero += nz
            if info.get("completed"):
                utfall["fullbordan"] += 1
            elif info.get("landed"):
                utfall["grop"] += 1
            elif info.get("terminal"):
                utfall["camp"] += 1
            else:
                utfall["timeout"] += 1
    res[namn] = dict(utfall)
    res[namn]["nonzero_stegreward_exkl_terminal"] = tot_nonzero
print("A) RUTT-SPAWN (nollpolicy, N=%d per state):" % N_PER)
print(json.dumps(res, ensure_ascii=False, indent=1))

# B) kantspawn under multihop: episodlängder + terminalflaggor
env2 = make()
langder, term = [], Counter()
for k in range(24):
    env2.core.rng = np.random.default_rng(2000 + k)
    info, ticks, tot, nz = run_zero_episode(env2)
    langder.append(ticks)
    term["terminal" if info.get("terminal") else "timeout"] += 1
    if info.get("completed"):
        term["fullbordan"] += 1
print("B) KANTSPAWN multihop: episodlängd p50 %.0f max %d ticks; %s"
      % (np.percentile(langder, 50), max(langder), dict(term)))
