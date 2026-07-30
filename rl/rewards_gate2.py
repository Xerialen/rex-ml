"""Gate 2-belöningar (BRIEF §3.4): fritt strövande dm3 utan navmesh.

Tre komponenter enligt manifestet:
  1. Kinetisk multiplikator — fart linjerad bort från närliggande hinder belönas;
     hastighetsvektor rakt in i vägg straffas.
  2. Kollisionsimpuls-straff — massivt negativt för ofrivilliga fartförluster.
  3. Global topologisk nyfikenhet — voxelraster (32u, samma upplösning som
     zonarbetet i pipeline/out/gate2/), DOLT för agentens observationer;
     engångsbonus per ny voxel, proportionell mot passagehastigheten.

Voxelnyfikenheten är per-episod (reset nollar besökssetet): det belönar att
episoden täcker ny terräng i fart, utan att policyn kan memorera ett globalt
besöksschema — geometrin, inte historiken, ska bära beteendet.
"""
from __future__ import annotations

import numpy as np

from .rewards_gate1 import StepState, _collision_loss, _speed_h
from .spec import SPEED_NORM

VOXEL_U = 32.0


class VoxelNovelty:
    """Endast i belöningskalkylatorn — aldrig i observationerna."""

    # 0.05→0.15 (2026-07-31, mätgrundat): lat-optimum uppmätt vid 462M frames —
    # samplat kryper i 28 u/s, 0,17 % täckning; nyheten måste väga tyngre.
    def __init__(self, bonus_per_voxel: float = 0.15):
        self.bonus = bonus_per_voxel
        self.seen: set[tuple[int, int, int]] = set()

    def reset(self):
        self.seen.clear()

    def step(self, pos: np.ndarray, speed_h: float) -> float:
        key = (int(pos[0] // VOXEL_U), int(pos[1] // VOXEL_U), int(pos[2] // VOXEL_U))
        if key in self.seen:
            return 0.0
        self.seen.add(key)
        # proportionell mot passagehastigheten (manifestet): långsam upptäckt
        # ger nästan inget — agenten ska SLUNGA sig in i okänd terräng
        return self.bonus * min(speed_h / SPEED_NORM, 1.5)


def kinetic_multiplier(s: StepState, ray_fracs: np.ndarray,
                       ray_dirs: np.ndarray) -> float:
    """Fart × linjering bort från hinder. ray_fracs/dirs är samma strålar som
    observationen använder (fraction 1.0 = fritt till max_dist).

    Projektionen av hastighetsriktningen på varje strålriktning viktas med hur
    NÄRA hindret på den strålen är: fart mot en nära vägg ger negativ term,
    fart längs öppna korridorer positiv.
    """
    sp = _speed_h(s.vel)
    if sp < 1.0:
        return 0.0
    vdir = s.vel / (np.linalg.norm(s.vel) + 1e-9)
    align = ray_dirs @ vdir                      # (n_rays,), cos-vinkel
    closeness = 1.0 - np.clip(ray_fracs, 0.0, 1.0)   # 0 = fritt, 1 = vägg intill
    # straffa endast rörelse MOT nära hinder (align>0, closeness hög);
    # öppenhet i färdriktningen belönas svagt
    into_wall = float(np.max(align * closeness * (align > 0)))
    openness = float(np.mean(np.clip(ray_fracs[align > 0.5], 0, 1))) if np.any(align > 0.5) else 0.5
    return (sp / SPEED_NORM) * (0.01 * openness - 0.02 * into_wall)


def reward_gate2(s: StepState, ray_fracs: np.ndarray, ray_dirs: np.ndarray,
                 novelty: VoxelNovelty) -> float:
    r = kinetic_multiplier(s, ray_fracs, ray_dirs)
    # Gate 1-receptet (bevisat fartdrivande): exponentiell utdelning ÖVER motor-
    # gränsen 320. Tillagt 2026-07-31 mot uppmätt lat-optimum (smyga undan
    # fastnad-straffet i 28 u/s). Utan denna term saknar farten egen gradient.
    sp = _speed_h(s.vel)
    if sp > 320.0:
        r += float(np.expm1((sp - 320.0) / 160.0)) * 0.01
    loss = _collision_loss(s)
    if loss > 0.0:
        r -= loss / 150.0        # impulskollision: massivt negativt (BRIEF §3.4)
    r += novelty.step(s.pos, _speed_h(s.vel))
    return r
