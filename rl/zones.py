"""Zonrastret (pipeline/out/gate2/voxel_classes.npz) som uppslag för miljö,
belöningskalkylator och gate-utvärdering.

Klasskoder (voxel_classes_meta.json): 1=WATER 2=LIFT 3=TELE 4=OPEN
5=CONSTRAINED 6=LOWDATA. Voxlar utanför rastret (aldrig trafikerade av
människor) behandlas som LOWDATA: agenten får utforska dem, men ingen
fartutsaga går att försvara där, så de räknas inte i gaten.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

VOXEL_U = 32.0
RASTER = Path(__file__).resolve().parent.parent / "pipeline" / "out" / "gate2" / "voxel_classes.npz"

CLS_WATER, CLS_LIFT, CLS_TELE, CLS_OPEN, CLS_CONSTRAINED, CLS_LOWDATA = 1, 2, 3, 4, 5, 6
EXCLUDED = {CLS_WATER, CLS_LIFT, CLS_TELE}
OPEN_TARGET = 500.0
CONSTRAINED_FACTOR = 0.8


class ZoneRaster:
    def __init__(self, path: Path = RASTER):
        d = np.load(path)
        key = (d["ix"].astype(np.int64) << 32) ^ \
              ((d["iy"].astype(np.int64) & 0xFFFF) << 16) ^ \
              (d["iz"].astype(np.int64) & 0xFFFF)
        cls = d["cls"].astype(np.int8)
        target = np.where(cls == CLS_OPEN, OPEN_TARGET,
                          np.where(cls == CLS_CONSTRAINED,
                                   CONSTRAINED_FACTOR * d["p999"], 0.0)).astype(np.float32)
        self._map: dict[int, tuple[int, float]] = {
            int(k): (int(c), float(t)) for k, c, t in zip(key, cls, target)
        }
        self.n_open = int(np.sum(cls == CLS_OPEN))

    @staticmethod
    def _key(pos) -> int:
        ix = int(np.floor(pos[0] / VOXEL_U))
        iy = int(np.floor(pos[1] / VOXEL_U))
        iz = int(np.floor(pos[2] / VOXEL_U))
        return (ix << 32) ^ ((iy & 0xFFFF) << 16) ^ (iz & 0xFFFF)

    def lookup(self, pos) -> tuple[int, float]:
        """-> (klass, T(v) i u/s; 0 där ticken inte räknas)."""
        return self._map.get(self._key(pos), (CLS_LOWDATA, 0.0))

    def is_excluded(self, pos) -> bool:
        """För fastnad-detekteringen: vatten/hiss/tele räknas inte som fastnad."""
        return self.lookup(pos)[0] in EXCLUDED


class GateScore:
    """Ackumulerar gate-formelns tre termer under en körning (eller flera)."""

    def __init__(self, raster: ZoneRaster):
        self.r = raster
        self.ratio_sum = 0.0
        self.ratio_n = 0
        self.open_speed_sum = 0.0
        self.open_n = 0
        self.open_visited: set[int] = set()

    def tick(self, pos, speed_h: float):
        cls, target = self.r.lookup(pos)
        if target > 0.0:
            self.ratio_sum += speed_h / target
            self.ratio_n += 1
        if cls == CLS_OPEN:
            self.open_speed_sum += speed_h
            self.open_n += 1
            self.open_visited.add(self.r._key(pos))

    def summary(self) -> dict:
        return {
            "score": self.ratio_sum / max(self.ratio_n, 1),
            "open_mean_speed": self.open_speed_sum / max(self.open_n, 1),
            "open_coverage": len(self.open_visited) / max(self.r.n_open, 1),
        }

    def passed(self) -> bool:
        s = self.summary()
        return (s["score"] >= 1.0 and s["open_mean_speed"] > OPEN_TARGET
                and s["open_coverage"] >= 0.70)
