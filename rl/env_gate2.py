"""Gate 2-miljökärnan: fritt strövande dm3 (BRIEF §2, curriculum §4 A–D).

Skiljer sig från Gate 1-kärnan i tre avseenden:
  * starter: slumpade (spawnpunkter i steg A–C-områden resp. hela kartan i D),
  * belöning: reward_gate2 (kinetik + kollisionsimpuls + voxelnyfikenhet),
  * terminering: tidsgräns (60 s) eller FASTNAD (>2 s under 50 UPS utanför
    exkluderad zon) — fastnad ger stort slutstraff; Gate-kravet är noll fastnade.

Zonmasken (pipeline/out/gate2/, agent A) pluggas in som en callable
`is_excluded(pos) -> bool`; tills rastret är levererat används None = inget
undantag (fastnad räknas överallt), vilket är KONSERVATIVT (aldrig generösare).
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np

from . import spec as S
from .env import Backend
from .rewards_gate1 import StepState, _collision_loss, _speed_h
from .rewards_gate2 import VoxelNovelty, reward_gate2

DM3_SPAWNS = Path(__file__).parent / "data" / "dm3_spawns.json"

STUCK_SPEED = 50.0
STUCK_TICKS = int(2.0 / S.TICK_DT)      # 2 s
STUCK_PENALTY = -5.0


def load_spawns(path: Path = DM3_SPAWNS) -> list[tuple[np.ndarray, float]]:
    d = json.load(open(path))
    return [(np.array(s["pos"], dtype=float), float(s["yaw"])) for s in d["spawns"]]


@dataclasses.dataclass
class Gate2Config:
    max_ticks: int = 77 * 60            # 60 s, gatens mätfönster
    spawn_region: tuple | None = None   # (min_xyz, max_xyz) för steg A–C; None = alla
    # "random_open" = manifestets steg D ordagrant ("helt slumpmässiga koordinater"):
    # spawn i slumpad OPEN-voxel ur zonrastret. Infört 2026-07-31 efter uppmätt
    # hemlåde-jämvikt (6 fasta spawns ⇒ policyn lärde sig pacea sin startkammare
    # vid ALLA sex; slumpstart över kartan gör mönstret olärbart).
    spawn_mode: str = "random_open"


class QWGate2Core:
    def __init__(self, backend: Backend, obs_spec: S.ObsSpec | None = None,
                 cfg: Gate2Config | None = None, rng: np.random.Generator | None = None,
                 is_excluded=None):
        self.b = backend
        self.obs_spec = obs_spec or S.ObsSpec()
        self.cfg = cfg or Gate2Config()
        self.rng = rng or np.random.default_rng()
        self.is_excluded = is_excluded
        self.spawns = load_spawns()
        self._open_centers = None
        if self.cfg.spawn_mode == "random_open":
            try:
                from .zones import RASTER, CLS_OPEN
                d = np.load(RASTER)
                m = d["cls"] == CLS_OPEN
                self._open_centers = np.stack(
                    [d["ix"][m] * 32.0 + 16, d["iy"][m] * 32.0 + 16,
                     d["iz"][m] * 32.0 + 16], axis=1).astype(float)
            except FileNotFoundError:
                pass                     # faller tillbaka på fasta spawns
        self.novelty = VoxelNovelty()
        self._reset_state(self.spawns[0])

    def _pick_spawn(self):
        if self._open_centers is not None and self.cfg.spawn_region is None \
                and self.cfg.spawn_mode == "random_open":
            i = int(self.rng.integers(len(self._open_centers)))
            pos = self._open_centers[i].copy()
            pos[2] += 8.0                # strax över voxelcentrum; settling tar golvet
            return pos, float(self.rng.uniform(0.0, 360.0))
        cands = self.spawns
        if self.cfg.spawn_region is not None:
            lo, hi = (np.array(x, dtype=float) for x in self.cfg.spawn_region)
            inside = [s for s in cands if np.all(s[0] >= lo) and np.all(s[0] <= hi)]
            cands = inside or cands
        i = int(self.rng.integers(len(cands)))
        pos, yaw = cands[i]
        return pos.copy(), yaw + float(self.rng.uniform(-180.0, 180.0))

    def _reset_state(self, spawn):
        pos, yaw = spawn
        self.pos = pos
        self.yaw = yaw % 360.0
        self.pitch = 0.0
        self.vel = np.zeros(3)
        self.tick = 0
        self.onground = True
        self.waterlevel = 0
        self.jump_held = False
        self.last_action = np.zeros(6, dtype=np.float32)
        self.slow_ticks = 0
        self.stuck = False
        self.speed_sum = 0.0
        self.speed_n = 0
        self._last_ray_fracs = None
        self._last_ray_dirs = None

    def reset(self) -> np.ndarray:
        # random_open-voxlar kan sakna golv rakt under (luftvoxlar) — pröva om
        for _attempt in range(6):
            self._reset_state(self._pick_spawn())
            self.novelty.reset()
            self.b.reset(self.pos, self.vel, self.yaw)
            for _ in range(90):
                self.pos, self.vel, self.onground, self.waterlevel, self.jump_held = \
                    self.b.step(self.yaw, self.pitch, 0.0, 0.0, False)
                if self.onground:
                    break
            if self.onground:
                break
        return self._obs()

    def _obs(self) -> np.ndarray:
        rs = self.obs_spec.rays
        dirs = rs.directions(self.yaw)
        fracs = self.b.trace_rays(rs.origins(self.pos.astype(np.float32), self.yaw),
                                  dirs, rs.max_dist)
        self._last_ray_fracs = np.asarray(fracs, dtype=np.float32)
        self._last_ray_dirs = dirs
        kin = self.obs_spec.kinetic(self.vel, self.yaw, self.pitch, self.onground,
                                    self.waterlevel, self.jump_held, self.last_action)
        return np.concatenate([self._last_ray_fracs, kin])

    def step(self, box: np.ndarray, fwd: int, side: int, jump: int):
        self.yaw, self.pitch, fm, sm, jb = S.action_to_usercmd(
            box, fwd, side, jump, self.yaw, self.pitch)
        prev_vel = self.vel.copy()
        prev_og = self.onground
        self.pos, self.vel, self.onground, self.waterlevel, self.jump_held = \
            self.b.step(self.yaw, self.pitch, fm, sm, jb)
        self.tick += 1
        st = StepState(pos=self.pos, vel=self.vel, prev_vel=prev_vel,
                       onground=self.onground, prev_onground=prev_og,
                       jumped_this_tick=(prev_og and not self.onground))
        r = reward_gate2(st, self._last_ray_fracs, self._last_ray_dirs, self.novelty)

        sp = _speed_h(self.vel)
        counted = not (self.is_excluded and self.is_excluded(self.pos))
        if counted:
            self.speed_sum += sp
            self.speed_n += 1
            self.slow_ticks = self.slow_ticks + 1 if sp < STUCK_SPEED else 0
        else:
            self.slow_ticks = 0
        if self.slow_ticks >= STUCK_TICKS:
            self.stuck = True
            r += STUCK_PENALTY

        self.last_action = S.flat_action(
            float(box[0]) * S.MAX_DYAW_DEG, float(box[1]) * S.MAX_DPITCH_DEG,
            fwd, side, jump)
        done = self.stuck or self.tick >= self.cfg.max_ticks
        mean_speed = self.speed_sum / max(self.speed_n, 1)
        return self._obs(), float(r), done, {
            "stuck": self.stuck, "mean_speed_counted": mean_speed,
            "novel_voxels": len(self.novelty.seen),
        }
