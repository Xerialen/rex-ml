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
# Täckningens universum = NÅBARA OPEN-voxlar: ≤ REACHABLE_LEVELS voxlar över
# närmaste solida golv (2026-08-01, mätgrundat): OPEN-rastret är 3D och 62 %
# av voxlarna ligger >96 u upp i rummens luftvolymer — onåbara för en löpande/
# hoppande spelare (hopp-apex ~45 u). 70 %-unionen mot ALLA OPEN var därmed
# fysiskt omöjlig; mot nåbara (12 012 voxlar) är den nåbar och bär samma
# intention (besök hela kartan). Fördelning: nivå 0-2 = 37,6 % av OPEN.
REACHABLE_LEVELS = 3


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
        # nåbara OPEN-voxlar (se REACHABLE_LEVELS ovan)
        occ = set(zip(d["ix"].tolist(), d["iy"].tolist(), d["iz"].tolist()))
        m = cls == CLS_OPEN
        self.reachable_open: set[int] = set()
        for x, y, z in zip(d["ix"][m].tolist(), d["iy"][m].tolist(), d["iz"][m].tolist()):
            k = 0
            while (x, y, z - 1 - k) in occ and k < REACHABLE_LEVELS:
                k += 1
            if k < REACHABLE_LEVELS:
                self.reachable_open.add(
                    (x << 32) ^ ((y & 0xFFFF) << 16) ^ (z & 0xFFFF))
        self.n_open_reachable = len(self.reachable_open)

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
            k = self.r._key(pos)
            if k in self.r.reachable_open:
                self.open_visited.add(k)

    def summary(self) -> dict:
        return {
            "score": self.ratio_sum / max(self.ratio_n, 1),
            "open_mean_speed": self.open_speed_sum / max(self.open_n, 1),
            "open_coverage": len(self.open_visited) / max(self.r.n_open_reachable, 1),
        }

    def passed(self) -> bool:
        s = self.summary()
        return (s["score"] >= 1.0 and s["open_mean_speed"] > OPEN_TARGET
                and s["open_coverage"] >= 0.70)
