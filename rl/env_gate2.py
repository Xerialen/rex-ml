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
from .rewards_gate2 import (AirLandingBonus, CellRarity, TransitionRarity,
                            VoxelNovelty, height_reward, reward_gate2)

DM3_SPAWNS = Path(__file__).parent / "data" / "dm3_spawns.json"

STUCK_SPEED = 50.0
STUCK_TICKS = int(2.0 / S.TICK_DT)      # 2 s
STUCK_PENALTY = -5.0
# Sidovillkorets tröskel (skeptikerrunda 2b, mätkalibrerad på riktiga qwsim):
# målprogression prog = ((landning − takeoff)·u)/d² där u = takeoff→landing_2d,
# d = |u|. Uppmätt separation: hörnklipp 0,054-0,444, äkta korsning 0,805-0,902
# ⇒ 0,6 har >= 0,16 marginal åt båda håll. Under tröskeln: effective_depth = 0.
TAKEOFF_PROG_MIN = 0.6


def load_spawns(path: Path = DM3_SPAWNS) -> list[tuple[np.ndarray, float]]:
    d = json.load(open(path))
    return [(np.array(s["pos"], dtype=float), float(s["yaw"])) for s in d["spawns"]]


@dataclasses.dataclass
class Gate2Config:
    max_ticks: int = 77 * 60            # 60 s, gatens mätfönster
    spawn_region: tuple | None = None   # (min_xyz, max_xyz) för steg A–C; None = alla
    # riskregimen 2026-08-02 (ägarens genombrottsmandat): exakta spawn-punkter
    # (N,3)-array — boxar är för grova för smala ledger. Har företräde före region.
    spawn_centers: object = None
    # "random_open" = manifestets steg D ordagrant ("helt slumpmässiga koordinater"):
    # spawn i slumpad OPEN-voxel ur zonrastret. Infört 2026-07-31 efter uppmätt
    # hemlåde-jämvikt (6 fasta spawns ⇒ policyn lärde sig pacea sin startkammare
    # vid ALLA sex; slumpstart över kartan gör mönstret olärbart).
    spawn_mode: str = "random_open"
    # V1/V2 (rewardtrappan, PROGRESS 2026-08-01 03:19): AVSTÄNGDA tills
    # täckningstriggern slår — aktiveras via train_gate2-flaggorna.
    vertical_rewards: bool = False   # V1a klätterbonus + V2 gap-crossing
    cell_rarity: bool = False        # V1b sällsynthetsviktad novelty
    # viktflaggor (2026-08-01): omstartsbillig justering + PBT-förberedelse
    novelty_bonus: float = 1.5
    rarity_lo: float = 0.5
    rarity_hi: float = 4.0
    climb_coef: float = 0.08
    gap_base: float = 3.0
    height_coef: float = 0.0         # höjdviktad fartinkomst (0 = av)
    # KANTAVSTAMPS-SPAWNER (reverse curriculum steg 0, 2026-08-03): riktade
    # takeoff-states — grundad kantstart 7-15 u från kanten (human-p50), yaw
    # mot målplattformens uppmätta landningscentroid, initialfart i human-
    # lyckat-bandet. Har företräde före ALLA andra spawn-grenar.
    # FIX D (2026-08-03, analyst_fas1_validation.md): workflowens gamla
    # humanfartsiffror (p50 271.6/p90 388.8) var dt-artefakter (fast dt=0.051
    # på en 13-51 ms-blandad kohort); kanoniskt human-lyckat är p50 372.8 /
    # p90 418.6 / max 451.4 ⇒ default-bandet 250-390 → 350-450.
    spawn_takeoff_states: object = None      # lista av {pos:[x,y,z], yaw:deg}
    takeoff_speed_range: tuple = (350.0, 450.0)  # kanoniskt human-lyckat ~p50..~max
    takeoff_yaw_jitter: float = 6.0
    takeoff_pos_jitter: float = 12.0
    # Graft ur Transitions-ICM (2026-08-03): √(ref/(n+1))-annealing (capad) av
    # gap-djupmultiplikatorns extra (×2→×1) per transitioncell — förhindrar att
    # gropjackpotten blir nästa farm-jämvikt (orbitens felmod vid 27-36/s).
    gap_anneal: bool = False
    gap_anneal_ref: float = 1.0


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
        # Skeptikerfix 2026-08-03 (novelty-förnybarheten): takeoff-workers
        # resettas ~5x oftare (924 vs 4620 ticks) vid SAMMA 8 fasta states —
        # per-episod-noveltyn hade gjort samma voxlar till en förnybar inkomst
        # var 12:e s (strövande/gropvarvning hade utkonkurrerat själva hoppet).
        # Enklaste åtgärden (vald, dokumenterad): bonus 0.0 för takeoff-envs —
        # de tränar UTESLUTANDE på gapbonusens signal; seen-setet och
        # novel_voxels-mätaren lever kvar för diagnostik.
        nov_bonus = 0.0 if self.cfg.spawn_takeoff_states is not None \
            else self.cfg.novelty_bonus
        self.novelty = VoxelNovelty(nov_bonus)
        self.air_bonus = AirLandingBonus(self.cfg.climb_coef, self.cfg.gap_base) \
            if self.cfg.vertical_rewards else None
        # CellRarity lever ÖVER episoder (EMA) — skapas en gång per env-instans
        self.rarity = CellRarity(lo=self.cfg.rarity_lo, hi=self.cfg.rarity_hi) \
            if self.cfg.cell_rarity else None
        # TransitionRarity lever ÖVER episoder (samma prejudikat som CellRarity)
        self.gap_rarity = TransitionRarity(self.cfg.gap_anneal_ref) \
            if (self.cfg.gap_anneal and self.cfg.vertical_rewards) else None
        self._reset_state(self.spawns[0])

    def _pick_spawn(self):
        if self.cfg.spawn_takeoff_states is not None:
            # kantavstamp: riktad state + tangentiell jitter (längs kanten,
            # vinkelrätt mot avstampsriktningen — trycker aldrig ut i gapet)
            states = self.cfg.spawn_takeoff_states
            s = states[int(self.rng.integers(len(states)))]
            yaw = float(s["yaw"]) + float(self.rng.uniform(
                -self.cfg.takeoff_yaw_jitter, self.cfg.takeoff_yaw_jitter))
            pos = np.asarray(s["pos"], dtype=float).copy()
            yr = np.radians(yaw)
            perp = np.array([-np.sin(yr), np.cos(yr)])
            pos[:2] += perp * float(self.rng.uniform(
                -self.cfg.takeoff_pos_jitter, self.cfg.takeoff_pos_jitter))
            pos[2] += 8.0                # strax över; settling tar golvet
            speed = float(self.rng.uniform(*self.cfg.takeoff_speed_range))
            # Sidovillkoret (skeptikerrunda 2b, ultra_fix_reverification2 §4):
            # spara valt states MÅL — landningscentroiden — så att gap-
            # kvalificeringen kan kräva målprogression vid landningen.
            # Fjärde tupelelementet ⇒ _reset_state sätter det atomiskt med
            # spawnen (övriga grenar = 3-/2-tupler ⇒ target None där).
            target = s.get("landing_2d")
            if target is not None:
                target = np.asarray(target, dtype=float)
            return pos, yaw, speed, target
        if self.cfg.spawn_centers is not None:
            cs = np.asarray(self.cfg.spawn_centers, dtype=float)
            i = int(self.rng.integers(len(cs)))
            pos = cs[i].copy()
            pos[2] += 8.0
            return pos, float(self.rng.uniform(0.0, 360.0)), None
        if self._open_centers is not None and self.cfg.spawn_mode == "random_open":
            cs = self._open_centers
            if self.cfg.spawn_region is not None:
                # curriculum-spawn (BRIEF §4 A-C-verktyget): slumpad OPEN-voxel
                # INOM regionen (2026-08-01: hexagonplatåerna — botten hade 0
                # samples på ringnivån av 30 min; episoder som börjar uppe ger
                # höjd/novelty från tick 0 och ledge-hoppen inom räckhåll)
                lo, hi = (np.array(x, dtype=float) for x in self.cfg.spawn_region)
                m = np.all((cs >= lo) & (cs <= hi), axis=1)
                if m.any():
                    cs = cs[m]
            i = int(self.rng.integers(len(cs)))
            pos = cs[i].copy()
            pos[2] += 8.0                # strax över voxelcentrum; settling tar golvet
            return pos, float(self.rng.uniform(0.0, 360.0)), None
        cands = self.spawns
        if self.cfg.spawn_region is not None:
            lo, hi = (np.array(x, dtype=float) for x in self.cfg.spawn_region)
            inside = [s for s in cands if np.all(s[0] >= lo) and np.all(s[0] <= hi)]
            cands = inside or cands
        i = int(self.rng.integers(len(cands)))
        pos, yaw = cands[i]
        return pos.copy(), yaw + float(self.rng.uniform(-180.0, 180.0)), None

    def _reset_state(self, spawn):
        pos, yaw = spawn[0], spawn[1]
        # tredje element = önskad initialfart (kantavstamps-spawnern); tvåtupler
        # (fasta spawns) förblir giltiga anrop
        self._spawn_speed = float(spawn[2]) if len(spawn) > 2 and spawn[2] else None
        # fjärde element = takeoff-statens landningsmål (landing_2d) för
        # sidovillkoret; None i alla övriga spawn-grenar (skeptikerrunda 2b)
        self._takeoff_target = spawn[3] if len(spawn) > 3 else None
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
        # luftsegment (V1a/V2): takeoff-pos + samplade luftpositioner;
        # None = inget aktivt segment (avbryts av vatten/exkluderad takeoff)
        self._air_takeoff = None
        self._air_buf: list[np.ndarray] = []
        self.n_climb = 0
        self.n_gap = 0
        # FIX C (skeptikerförslag runda 2): takeoff-episoder termineras vid
        # FÖRSTA landningen (lyckad eller ej) — hindrar kedjefarmning inom
        # episoden och eliminerar post-försöks-strövandet (~80 % av 12s-taket)
        self._landed_done = False

    def reset(self) -> np.ndarray:
        if self.rarity is not None:
            self.rarity.end_episode()
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
                # curriculum-spawn: settling som föll UR regionen (t.ex. ned i
                # gropen från en kantvoxel) räknas som misslyckat försök
                if self.cfg.spawn_takeoff_states is not None:
                    zmin = min(float(s["pos"][2])
                               for s in self.cfg.spawn_takeoff_states)
                    if self.pos[2] < zmin - 24.0:
                        continue        # settlade ner i gropen — kassera
                elif self.cfg.spawn_centers is not None:
                    zmin = float(np.asarray(self.cfg.spawn_centers)[:, 2].min())
                    if self.pos[2] < zmin - 24.0:
                        continue        # settlade ur ledgenivån (t.ex. ner i gropen)
                elif self.cfg.spawn_region is not None and \
                        self.pos[2] < float(self.cfg.spawn_region[0][2]) - 24.0:
                    continue
                break
        else:
            # Skeptikerfix 2026-08-03 (spawn_speed-i-grop-läckan): alla 6
            # settlingförsök kasserade ⇒ boten står kvar i SISTA försökets
            # tillstånd (t.ex. nere i gropen) — injicera ALDRIG fart där.
            self._spawn_speed = None
        if self.onground and self._spawn_speed:
            # kantavstamp: injicera initialfarten EFTER settlingen (ordningen
            # avgörande — friktionen under settlingens upp till 90 tick hade
            # annars ätit farten). Backenden stödjer vel i reset (env.py:19);
            # 1 synk-tick hämtar hem det nya tillståndet.
            # Friktionskompensation (skeptikerfix 2026-08-03): synk-ticken tar
            # QW-markfriktion ×(1 − friction 4 × TICK_DT) = ×0.948 — uppmätt
            # levererat band var 237-370 i stället för konfigurerade 250-390.
            # ÷0.948 vid injektionen ⇒ levererat band = konfigurerat.
            yr = np.radians(self.yaw)
            v = (self._spawn_speed / (1.0 - 4.0 * S.TICK_DT)) \
                * np.array([np.cos(yr), np.sin(yr), 0.0])
            self.b.reset(self.pos, v, self.yaw)
            self.pos, self.vel, self.onground, self.waterlevel, self.jump_held = \
                self.b.step(self.yaw, self.pitch, 0.0, 0.0, False)
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

    def _air_segment(self, prev_og: bool, counted: bool,
                     jumped: bool = False) -> float:
        """V1a/V2: spåra luftsegment, betala klätter-/gapbonus vid landning.
        Vatten avbryter (simning är inte hopp); segment kräver räknad takeoff
        OCH räknad landning så att hiss-/tele-utfall aldrig betalas.
        Skeptikerfix 2026-08-03 (gropdyk-jackpotten): segment startas ENDAST
        vid äkta hoppavstamp (jumped = hoppknapp + positiv vz vid grundad
        avgång) — ren kantavgång (prev_og→luft utan hopp) öppnar inget segment
        och kan aldrig utlösa gap-/klätterbonus eller räknas i n_gap."""
        if self.waterlevel > 0:
            self._air_takeoff = None
            self._air_buf.clear()
            return 0.0
        if prev_og and not self.onground:                 # takeoff
            self._air_takeoff = self.pos.copy() if (counted and jumped) else None
            self._air_buf.clear()
            return 0.0
        if not self.onground:                             # i luften
            if self._air_takeoff is not None and self.tick % 3 == 0:
                self._air_buf.append(self.pos.copy())
            return 0.0
        if prev_og or self._air_takeoff is None:          # på marken/inget segment
            return 0.0
        takeoff, self._air_takeoff = self._air_takeoff, None   # landning
        if not counted:
            self._air_buf.clear()
            return 0.0
        span = float(np.linalg.norm((self.pos - takeoff)[:2]))
        rise = float(self.pos[2] - takeoff[2])
        eff_depth = 0.0
        if span >= self.air_bonus.GAP_MIN_SPAN and len(self._air_buf) >= 3:
            # 3-punkts golvprofil under banan (25/50/75 %), samma provpunkter
            # som analyze_gapjumps fast online; 512 u räcker för dm3:s schakt.
            # Skeptikerfix runda 2 (2026-08-03, origo-offset-hålet): djupet är
            # FOTRELATIVT, inte trace-längd från origo. Trace-längd mätte
            # origo-höjd + apex (67.8 u under ett HELT PLATT hopp > tröskeln
            # 56 ⇒ gapbonus för varje platt hopp med span >= 150, uppmätt
            # 261/261 icke-korsningar). Nu: golv-z per prov = prov-z − trace,
            # fotnivå = min(avstamps-z, landnings-z) − 24 (origo→golvyta,
            # uppmätt), effective_depth = fotnivå − min(golv-z). Platt hopp:
            # golvet ÄR fotnivån ⇒ ~0 ⇒ diskat. Gropkorsning: fot 32 −
            # gropgolv −224 ⇒ 256 ⇒ deep. (frac 1.0 = inget golv inom 512 u
            # ⇒ golv-z minst 512 under provet — djupt, korrekt kvalificerat.)
            idx = [len(self._air_buf) // 4, len(self._air_buf) // 2,
                   (3 * len(self._air_buf)) // 4]
            origins = np.stack([self._air_buf[i] for i in idx]).astype(np.float32)
            down = np.tile(np.array([0.0, 0.0, -1.0], dtype=np.float32), (3, 1))
            fracs = np.asarray(self.b.trace_rays(origins, down, 512.0))
            floor_z = origins[:, 2].astype(float) - fracs * 512.0
            foot_z = min(float(takeoff[2]), float(self.pos[2])) \
                - self.air_bonus.ORIGIN_FLOOR_OFFSET
            eff_depth = float(foot_z - np.min(floor_z))
        # Sidovillkoret (skeptikerrunda 2b, ultra_fix_reverification2 §4):
        # gapbonus i takeoff-envs kräver MÅLPROGRESSION — hörnklippet (hopp
        # över gropens hörn, landning på samma sidas rim, d_tgt ~570) var
        # uppmätt dominant jämvikt (18,85/episod på 0,66 s = 3,7× gropfallets
        # frame-rate) och policy-nåbart med en konstant 0,15-luftstrafe från
        # kanonisk spawn. prog = projektionen av faktiska hoppvektorn på
        # målvektorn, normerad mot målavståndet. Kalibrering (riktiga qwsim):
        # klipp 0,054-0,444, äkta korsning 0,805-0,902 ⇒ tröskeln 0,6 har
        # >= 0,16 marginal åt båda håll. Kartfri separation (void-andel under
        # banan) är uppmätt OMÖJLIG — klippet är en äkta void-bana (0,88-1,00
        # mot korsningens 0,81-1,00). Gäller ENDAST takeoff-spawnade envs
        # (strövande envs har inget landing_2d — oförändrad semantik där).
        # Nollar också klippets n_gap-förgiftning (gap_qualifies ser samma 0).
        if self.cfg.spawn_takeoff_states is not None \
                and self._takeoff_target is not None:
            u = self._takeoff_target - takeoff[:2]
            d = float(np.linalg.norm(u))
            prog = float((self.pos[:2] - takeoff[:2]) @ u) / (d * d) \
                if d > 1e-6 else 0.0
            if prog < TAKEOFF_PROG_MIN:
                eff_depth = 0.0    # ⇒ gap_qualifies False ⇒ bonus 0, n_gap orört
        self._air_buf.clear()
        # gap-anneal (Transitions-ICM-graften): djupextran ×2→×1 avklingar med
        # √(ref/(n+1)) per transitioncell så jackpotten inte blir farm-jämvikt
        anneal = self.gap_rarity.anneal(takeoff, self.pos) \
            if self.gap_rarity is not None else 1.0
        bonus = self.air_bonus.landing(span, rise, eff_depth, deep_anneal=anneal)
        if rise >= self.air_bonus.CLIMB_MIN_RISE:
            self.n_climb += 1
        # n_gap räknar ENDAST fullt kvalificerade gap-korsningar (skeptikerfix
        # 2026-08-03: mätförgiftningen — gropdyk/nivåtappande nedslag räknas
        # inte; gap_qualifies inkluderar landningsnivåkravet rise >= -24)
        if bonus > 0.0 and self.air_bonus.gap_qualifies(span, rise, eff_depth):
            self.n_gap += 1
            # rarity-asymmetrin (skeptikerfix): note() endast för DJUPA gap —
            # grunda gap i samma cellpar ska inte avklinga djupextran
            if self.gap_rarity is not None \
                    and eff_depth > self.air_bonus.GAP_DEEP_DEPTH:
                self.gap_rarity.note(takeoff, self.pos)
        return bonus

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
        # Nyhet betalas ENDAST i räknade (icke-exkluderade) voxlar (2026-08-01,
        # mätgrundat): med bonus 1,5 blev vattenvolymen policyns nyhetsgruva —
        # 32,8 % av tiden i VATTNET i fart 71 (spatial_report). Vatten/hiss/tele
        # är exkluderade ur gate-mätningen; kuriositeten ska rikta sig mot
        # terräng som räknas.
        sp = _speed_h(self.vel)
        counted = not (self.is_excluded and self.is_excluded(self.pos))
        nov_mult = 1.0
        if self.rarity is not None:
            self.rarity.note(self.pos)
            nov_mult = self.rarity.mult(self.pos)
        r = reward_gate2(st, self._last_ray_fracs, self._last_ray_dirs,
                         self.novelty if counted else None, nov_mult)
        if counted and self.cfg.height_coef > 0.0:
            r += height_reward(float(self.pos[2]), sp, self.cfg.height_coef, nov_mult)
        if self.air_bonus is not None:
            # äkta hopp = hoppknapp nedtryckt PÅ avstampsticken + positiv vz
            # (skiljer hopp — vz ~260 efter gravitationen — från kantavgång,
            # vz <= 0; hoppknapp hållen utan verkställt hopp ger också vz <= 0)
            jumped = bool(jb) and float(self.vel[2]) > 0.0
            r += self._air_segment(prev_og, counted, jumped=jumped)
        # FIX C (skeptikerförslag runda 2, 2026-08-03): takeoff-spawnade
        # episoder termineras vid FÖRSTA luft→mark-övergången (hopp ELLER
        # walkoff, lyckad eller ej) — landningsbonusen för just den ticken är
        # redan utbetald ovan; ingen kedjefarmning inom episoden är möjlig.
        if self.cfg.spawn_takeoff_states is not None \
                and not prev_og and self.onground:
            self._landed_done = True
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
        done = self.stuck or self._landed_done or self.tick >= self.cfg.max_ticks
        mean_speed = self.speed_sum / max(self.speed_n, 1)
        return self._obs(), float(r), done, {
            "stuck": self.stuck, "mean_speed_counted": mean_speed,
            "novel_voxels": len(self.novelty.seen),
            "n_climb": self.n_climb, "n_gap": self.n_gap,
            "landed": self._landed_done,
        }
