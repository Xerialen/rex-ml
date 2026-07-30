"""Backend mot libqwsim (bit-exakta pmove.c ur mvdsv, sim/qwsim*.so).

Verkligt API (verifierat mot modulen 2026-07-30): modulnivåfunktioner med global
slotpool — alloc_slots(n) sätter TOTALA antalet, load_bsp är global per process.
En env-instans = en slot; poolen allokeras en gång per process (SF:s workers är
separata processer, envs inom samma worker delar pool).

    step_batch(slot_ids, angles[N,3] (pitch,yaw,roll), forwardmove i16,
               sidemove i16, upmove i16, buttons u8 (bit1 = hopp), msec u8)
      -> (pos, vel, onground, waterlevel, jump_held, blocked)
    trace_rays(origins, dirs, max_dist) -> (fractions, normals, startsolid)

Movevars-defaults i modulen är valideringslåsta mot servern (gravity 800,
maxspeed 320, friction 4, airaccelerate 10, ktjump 1).
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import numpy as np

from .env import Backend

SIM_DIR = str(Path(__file__).resolve().parent.parent / "sim")

MAPS = {
    "100m": "/home/benjamin-adm/mlx/qwserver/serverdir/id1/maps/100m.bsp",
    "dm3": "/home/benjamin-adm/mlx/qwserver/serverdir/id1/maps/dm3.bsp",
}

BUTTON_JUMP = 1 << 1
MSEC_PER_TICK = 13          # 77 Hz-klienters wire-msec; validerat mot korpusen

_lock = threading.Lock()
_pool_size = 0
_next_slot = 0
_loaded_map: str | None = None


def _qwsim():
    if SIM_DIR not in sys.path:
        sys.path.insert(0, SIM_DIR)
    import qwsim
    return qwsim


def _acquire_slot(qwsim) -> int:
    """Processglobal slotutdelning. alloc_slots(n) sätter totalantal och nollar
    inget vid växning enligt modulens semantik — vi växer poolen i block."""
    global _pool_size, _next_slot
    with _lock:
        if _next_slot >= _pool_size:
            _pool_size = max(64, _pool_size * 2)
            qwsim.alloc_slots(_pool_size)
        slot = _next_slot
        _next_slot += 1
        return slot


class QwsimBackend(Backend):
    def __init__(self, cfg=None, map_name: str | None = None):
        global _loaded_map
        self.q = _qwsim()
        name = map_name or (getattr(cfg, "qw_map", "100m") if cfg is not None else "100m")
        with _lock:
            if _loaded_map != name:
                if _loaded_map is not None and _loaded_map != name:
                    raise RuntimeError(
                        f"en process kan bara ha en karta laddad ({_loaded_map} != {name})")
                self.q.load_bsp(MAPS[name])
                _loaded_map = name
        self.slot = _acquire_slot(self.q)
        self._sid = np.array([self.slot], dtype=np.int32)

    def reset(self, pos, vel, yaw_deg):
        self.q.reset(self._sid,
                     np.asarray([pos], np.float32),
                     np.asarray([vel], np.float32),
                     np.array([[0.0, yaw_deg, 0.0]], np.float32))

    def step(self, yaw_deg, pitch_deg, forwardmove, sidemove, jump):
        pos, vel, og, wl, jh, blocked = self.q.step_batch(
            self._sid,
            np.array([[pitch_deg, yaw_deg, 0.0]], np.float32),
            np.array([forwardmove], np.int16),
            np.array([sidemove], np.int16),
            np.zeros(1, np.int16),
            np.array([BUTTON_JUMP if jump else 0], np.uint8),
            np.array([MSEC_PER_TICK], np.uint8),
        )
        return (pos[0].astype(float), vel[0].astype(float),
                bool(og[0]), int(wl[0]), bool(jh[0]))

    def trace_rays(self, origins, dirs, max_dist):
        fractions, _normals, _startsolid = self.q.trace_rays(
            np.asarray(origins, np.float32), np.asarray(dirs, np.float32),
            float(max_dist))
        return fractions
