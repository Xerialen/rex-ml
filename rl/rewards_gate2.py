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


class AirLandingBonus:
    """V1a (klätterbonus) + V2 (gap-crossing) — betalas vid LANDNING, aldrig per tick.

    Trösklar kalibrerade mot mänskliga korpusen (evidence/analyst_review_
    vertical_rewards.md, 2026-08-01): SNG→mega span p50 182/max 332 u och
    fönsterinflygning span p50 150-191 u gjorde ursprungsförslaget span>240
    värdelöst (4.5 % resp. 0/29 träffar). Mänsklig RA-klättring är trappserie
    med rise p50 32.8 u/hopp ⇒ klättertröskel 24 u.

    DJUPMÅTTET (skeptikerfix runda 2, 2026-08-03, ultra_fix_reverification §3):
    `effective_depth` är FOTRELATIVT — djupet av golvet under flygbanan
    RELATIVT landnings-/avstampsfotnivån, INTE absolut trace-längd från
    spelarorigo. Origo sitter ORIGIN_FLOOR_OFFSET = 24 u över golvytan
    (uppmätt, probe_origin.py), så den gamla origo-baserade tracen mätte
    67.8 u under ett HELT PLATT hopp (24 origo-offset + ~44 apex) — tröskeln
    56 uteslöt i verkligheten ingenting och varje platt hopp med span >= 150
    betalade gapbonus (261/261 icke-korsningar i skeptikerns fan-probe).
    Fotrelativt: platt hopp ⇒ effective_depth ≈ 0 ⇒ diskat; gropkorsningen
    (fot 32, gropgolv −224) ⇒ 256 ⇒ deep. Trösklarna 56/141 behålls enligt
    skeptikerns föreskrift — de biter nu på verkligt gapdjup.
    Bonusstorlekarna är startestimat (novelty betalar ~2.25/voxel i fartskala;
    ett fullt gap-hopp ska väga som en handfull nya voxlar) — justeras efter
    mätning, inte antagande."""

    CLIMB_MIN_RISE = 24.0
    CLIMB_RISE_CAP = 96.0
    GAP_MIN_SPAN = 150.0
    GAP_MIN_DEPTH = 56.0
    GAP_DEEP_DEPTH = 141.0
    GAP_SPAN_CAP = 2.5
    # uppmätt spelarorigo→golvyta-offset (stående: origo-z − golv-z = 24.0;
    # probe_origin.py mot riktiga qwsim/dm3) — dras av vid fotnivåberäkningen
    ORIGIN_FLOOR_OFFSET = 24.0
    # Skeptikerfix 2026-08-03 (gropdyk-jackpotten): en gap-KORSNING landar på
    # ledgenivå — landnings-z >= takeoff-z - 24 (rise >= -24). Gropdyk
    # (48 -> -224, rise -272) diskvalificeras automatiskt; mänsklig ring<->quad
    # är ~nivåneutral (plattformarna z=56 båda).
    GAP_MAX_DROP = 24.0

    # koefficienterna är instansparametrar (flaggexponerade 2026-08-01 för
    # billig justering utan kodändring; PBT-förberedelse — aktivering av PBT
    # kräver ägarbeslut). Trösklarna ovan är korpusmätta konstanter.
    def __init__(self, climb_coef: float = 0.08, gap_base: float = 3.0):
        self.climb_coef = climb_coef   # 0.08*rise: typiskt klätterhopp (32.8 u) ⇒ ~2.6
        self.gap_base = gap_base       # skalas med span; djup nivå ×2 ⇒ SNG→mega ~7.3

    def gap_qualifies(self, span: float, rise: float,
                      effective_depth: float) -> bool:
        """Gap-korsningens fulla kvalificering (skeptikerfixar 2026-08-03):
        span + FOTRELATIVT golvdjup (effective_depth — se klassdocstringen;
        platt hopp ⇒ ~0 ⇒ diskat), PLUS landningsnivåkravet rise >=
        -GAP_MAX_DROP — gropdyk (landning på gropgolvet, rise -272) och alla
        nedslag mer än 24 u under avstampet ger noll gapbonus, inget n_gap."""
        return (span >= self.GAP_MIN_SPAN
                and effective_depth > self.GAP_MIN_DEPTH
                and rise >= -self.GAP_MAX_DROP)

    def landing(self, span: float, rise: float, effective_depth: float,
                deep_anneal: float = 1.0) -> float:
        """effective_depth: fotrelativt gapdjup (env_gate2._air_segment:
        min(takeoff_z, landing_z) − ORIGIN_FLOOR_OFFSET − min golv-z under
        banan). deep_anneal ∈ [0,1]: skalning av djupnivåns EXTRA (×2 →
        ×1+anneal); 1.0 = full ×2 (bitkompatibel default), 0.0 = baspoäng.
        Sätts av TransitionRarity (env_gate2) — grunda gap och klätterbonusen
        berörs ej."""
        r = 0.0
        if rise >= self.CLIMB_MIN_RISE:
            r += self.climb_coef * min(rise, self.CLIMB_RISE_CAP)
        if self.gap_qualifies(span, rise, effective_depth):
            deep = 1.0 + deep_anneal if effective_depth > self.GAP_DEEP_DEPTH else 1.0
            r += self.gap_base * min(span / self.GAP_MIN_SPAN, self.GAP_SPAN_CAP) \
                 * deep
        return r


class TransitionRarity:
    """Graft ur Transitions-ICM (2026-08-03): √(ref/(n+1))-annealing, capad
    vid 1.0, av gap-djupmultiplikatorns EXTRA (×2→×1) per transitioncell
    (takeoffcell→landningscell, 256u — samma cellstorlek som CellRarity).
    Motiv: V2-djupbonusen (gap_base×spancap×2) är en jackpot; utan avklingning
    blir den nästa farm-jämvikt (samma felmod som orbiten vid 27-36/s).
    Med ref=1.0 är extran full vid första lyckandet och ~×1.2 efter ~25
    lyckade i samma cellpar. Per env-instans, lever ÖVER episoder (samma
    prejudikat som CellRarity). Endast i belöningskalkylatorn, aldrig i
    observationerna."""

    CELL_U = 256.0

    def __init__(self, ref: float = 1.0):
        # NaN-vakt (skeptikerfix 2026-08-03): negativt ref hade gett
        # np.sqrt(negativt) = NaN som tyst propagerar in i PPO-belöningen
        self.ref = max(0.0, float(ref))
        self.n: dict[tuple, int] = {}

    @staticmethod
    def _key(takeoff: np.ndarray, landing: np.ndarray) -> tuple:
        c = TransitionRarity.CELL_U
        return (int(takeoff[0] // c), int(takeoff[1] // c), int(takeoff[2] // c),
                int(landing[0] // c), int(landing[1] // c), int(landing[2] // c))

    def anneal(self, takeoff: np.ndarray, landing: np.ndarray) -> float:
        n = self.n.get(self._key(takeoff, landing), 0)
        return float(min(1.0, np.sqrt(self.ref / (n + 1))))

    def note(self, takeoff: np.ndarray, landing: np.ndarray):
        k = self._key(takeoff, landing)
        self.n[k] = self.n.get(k, 0) + 1


class CellRarity:
    """V1b: zonsällsynthetsviktning av voxelnyheten — självrefererande
    (bottens EGEN besökshistorik per 256u-cell, EMA över episoder i denna
    env-instans), INTE mänskliga zonandelar: korpusdata i rewarden vore
    rutt-prior i förklädnad. Motiv (analyst-review 2026-08-01): bottens
    täckningsunderskott är horisontellt — window översitts 9.4× (25.1 % av
    tiden mot människors 2.7 %) medan YA-gården/mega-gården/quad-övre/ringen
    undersitts 0.16-0.53×. Multiplikatorn gör nyhet i sällan besökta celler
    upp till 4× värd och i översittna celler 0.5×. Endast i belönings-
    kalkylatorn, aldrig i observationerna (samma regel som noveltyn)."""

    CELL_U = 256.0
    REF_SHARE = 0.02           # ~uniform andel över de ~50 celler en bana rör

    def __init__(self, alpha: float = 0.03, lo: float = 0.5, hi: float = 4.0):
        self.alpha, self.lo, self.hi = alpha, lo, hi
        self.ema: dict[tuple[int, int, int], float] = {}
        self._ep: dict[tuple[int, int, int], int] = {}
        self._ep_ticks = 0

    @staticmethod
    def _key(pos: np.ndarray) -> tuple[int, int, int]:
        c = CellRarity.CELL_U
        return (int(pos[0] // c), int(pos[1] // c), int(pos[2] // c))

    def note(self, pos: np.ndarray):
        k = self._key(pos)
        self._ep[k] = self._ep.get(k, 0) + 1
        self._ep_ticks += 1

    def end_episode(self):
        if self._ep_ticks == 0:
            return
        shares = {k: n / self._ep_ticks for k, n in self._ep.items()}
        for k in set(self.ema) | set(shares):
            self.ema[k] = (1 - self.alpha) * self.ema.get(k, 0.0) \
                          + self.alpha * shares.get(k, 0.0)
        self._ep.clear()
        self._ep_ticks = 0

    def mult(self, pos: np.ndarray) -> float:
        share = self.ema.get(self._key(pos), 0.0)
        return float(np.clip(self.REF_SHARE / (share + 0.005), self.lo, self.hi))


# Höjdviktad fartinkomst (ägardesign 2026-08-01 ~21:50: "ALLTID är highground
# viktigast" — YA-trappan, high bridge, window/lifts, RA-toppen, mega-ansatsen,
# quad/ring). Generisk översättning: absolut z normerad mot NÅBARA voxlarnas
# spann (uppmätt ur zonrastret: -304..368; RA-topp 0.90, window 0.70, mega-
# hylla 0.69, quad/ring 0.54, gårdgolv 0.06). FARTSKALAD (stillastående på
# höjd = 0 ⇒ ingen camping) och tänkt att multipliceras med CellRarity-multen
# (översitten höjd halveras, orörd fyrdubblas ⇒ cirkulation mellan höjderna;
# snabbaste vägen dit är trickhoppen som V1a/V2 betalar).
# Koef ~2.0 (kalkyl): RA/window-linje @550 ≈ 2.9/tick slår gropvarv @700 ≈ 2.3.
HEIGHT_Z_MIN = -304.0
HEIGHT_Z_MAX = 368.0


def height_reward(z: float, speed_h: float, coef: float, mult: float = 1.0) -> float:
    if coef <= 0.0:
        return 0.0
    zn = (z - HEIGHT_Z_MIN) / (HEIGHT_Z_MAX - HEIGHT_Z_MIN)
    zn = min(max(zn, 0.0), 1.0)
    return coef * zn * min(speed_h / SPEED_NORM, 1.5) * mult


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
                 novelty: VoxelNovelty | None, novelty_mult: float = 1.0) -> float:
    """novelty=None ⇒ ticken är i exkluderad zon (vatten/hiss/tele): ingen
    nyhetsutbetalning, voxeln registreras inte heller som sedd.
    novelty_mult: CellRarity-viktning (V1b); 1.0 = avstängd."""
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
        r += novelty_mult * novelty.step(s.pos, _speed_h(s.vel))
    return r
