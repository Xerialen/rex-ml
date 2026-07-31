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

    # 0.05→0.15→0.6 (2026-07-31, mätgrundat i två steg): vid 695M frames trampar
    # policyn på stället i ~119 u/s VID ALLA SEX spawns (spann 40-160u) — en
    # riskjämvikt: färsk-strövande gav ~0,5/s nyhet mot 1,4/s ren fartinkomst,
    # så pacing förlorade bara 1/3 av inkomsten men slapp kollisions-/
    # termineringsrisken. 0,6/voxel gör strövande STRIKT dominant (~2,2/s).
    # 0.6→1.5 (2026-07-31 23:30, mätgrundat, gate2_v2): policyn ORBITERAR i hög
    # fart (open-mean 497-527, täckning platt 5-6 %/10 runs över 240M frames,
    # belöningsplatå ~1540). Jämvikten: exp-termen vid 527 ger 0,35/tick — att
    # korsa trång transitterräng mot ny mark kostar sekunder av den inkomsten,
    # och 0,6/voxel (~0,9 i fartskala) kompenserar inte. Med 1,5 (2,25 i fart-
    # skala) betalar nyupptäckt i fart ~36/s mot orbitens ~27/s ⇒ svepande
    # banor strikt dominanta. Fartkravet har marginal (527 > 500 @ 30 runs).
    def __init__(self, bonus_per_voxel: float = 1.5):
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
                 novelty: VoxelNovelty | None) -> float:
    """novelty=None ⇒ ticken är i exkluderad zon (vatten/hiss/tele): ingen
    nyhetsutbetalning, voxeln registreras inte heller som sedd."""
    r = kinetic_multiplier(s, ray_fracs, ray_dirs)
    # Fartgradient i TVÅ regimer (2026-07-31, båda mätgrundade):
    # (1) LINJÄR 0→320: första exp-varianten betalade först över 320 medan
    #     policyn rörde sig i 28-37 u/s — gradienten låg bortom beteende-
    #     horisonten (uppmätt: +32 % fart på 55M frames, långt under målet).
    #     Gate 1 hade korridorframdriften som brygga dit; dm3 behöver denna.
    # (2) EXP över 320 (Gate 1-receptet, bevisat mot taket).
    sp = _speed_h(s.vel)
    r += 0.02 * min(sp, 320.0) / 320.0
    if sp > 320.0:
        # koeff 0.01→0.05 (2026-07-31 06:55, mätgrundat): policyn KRYSSAR stabilt
        # på 364 (98,5 % OPEN-tid, 0,1 % kedjebrott — inte olycksbegränsad) för
        # vid 364 gav exp-termen 0,003/tick mot linjärens 0,02 ⇒ svagt drag mot
        # gatens 500. Med 0,05: 0,016 vid 364, 0,10 vid 500 (5× linjären) —
        # högfart blir entydigt optimal.
        # tau 160→100 (2026-07-31 09:15): platå vid ~400 (två fönster; kryss-
        # jämvikt, inga olyckor — övermänsklig regim: mänsklig OPEN-p95 är 496).
        # Brantare kurva i 400-500-bandet: 0,055/tick @400, 0,152 @500.
        r += float(np.expm1((sp - 320.0) / 100.0)) * 0.05
    loss = _collision_loss(s)
    if loss > 0.0:
        r -= loss / 150.0        # impulskollision: massivt negativt (BRIEF §3.4)
    if novelty is not None:
        r += novelty.step(s.pos, _speed_h(s.vel))
    return r
