"""Backend mot libqwsim (bit-exakta pmove.c, sim/). En slot per env-instans —
SF:s rollout-workers ger processparallellism; qwsim:s egen batch/trådpool
utnyttjas fullt först om vi senare kör flera slots per env (batched sampling).

OBS: skrivet mot API:t som specificerades i libqwsim-uppdraget:
    qwsim.load_bsp(path) / Sim(n_slots) med reset(slot, pos, vel, angles),
    step_batch(...), get_state(slots), trace_rays(origins, dirs, max_dist).
Justeras mot den faktiska pybind-signaturen när agent B:s leverans landar
(bit-exakthetsvalideringen är godkännandekravet, se BRIEF §3.1).
"""
from __future__ import annotations

import numpy as np

from .env import Backend
from .spec import TICK_DT

MAPS = {
    "100m": "/home/benjamin-adm/mlx/qwserver/serverdir/id1/maps/100m.bsp",
    "dm3": "/home/benjamin-adm/mlx/qwserver/serverdir/id1/maps/dm3.bsp",
}


class QwsimBackend(Backend):
    def __init__(self, cfg=None):
        import qwsim  # byggd i sim/ (se sim/STACK.md för venv)
        self._mod = qwsim
        map_name = getattr(cfg, "qw_map", "100m") if cfg is not None else "100m"
        self.sim = qwsim.Sim(1)                      # en slot per env-instans
        self.sim.load_bsp(MAPS[map_name])

    def reset(self, pos, vel, yaw_deg):
        self.sim.reset(0, np.asarray(pos, np.float32), np.asarray(vel, np.float32),
                       np.array([0.0, yaw_deg, 0.0], np.float32))

    def step(self, yaw_deg, pitch_deg, forwardmove, sidemove, jump):
        self.sim.step_batch(
            angles=np.array([[pitch_deg, yaw_deg, 0.0]], np.float32),
            forwardmove=np.array([forwardmove], np.float32),
            sidemove=np.array([sidemove], np.float32),
            upmove=np.zeros(1, np.float32),
            jump=np.array([jump], bool),
            dt=TICK_DT,
        )
        st = self.sim.get_state([0])
        return (np.asarray(st["pos"][0], float), np.asarray(st["vel"][0], float),
                bool(st["onground"][0]), int(st["waterlevel"][0]),
                bool(st["jump_held"][0]))

    def trace_rays(self, origins, dirs, max_dist):
        return self.sim.trace_rays(np.asarray(origins, np.float32),
                                   np.asarray(dirs, np.float32), float(max_dist))
