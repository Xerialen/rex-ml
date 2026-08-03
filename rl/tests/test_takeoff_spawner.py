"""Kantavstamps-spawnern (reverse curriculum steg 0) + Transitions-ICM-graften.

Testar: (1) _pick_spawn-trippeln (pos/yaw/fart i bandet, tangentiell jitter),
(2) fartinjektionen efter settling inkl. friktionskompensationen,
(3) TransitionRarity-annealingen av gapdjupsextran, (4) AirLandingBonus.
deep_anneal-bitkompatibilitet, (5) sf_env-workergrenen + den genererade
datafilen mot v7.3-ledgemasken, samt skeptikerfixarna 2026-08-03:
äkta-hopp-kravet (kantavgång ⇒ ingen gapbonus), landningsnivåkravet
(gropdyk ⇒ ingen bonus, inget n_gap), novelty-nollningen för takeoff-envs,
NaN-vakten, spawn_speed-i-grop-läckan och rarity-asymmetrin.

Runda 2 (ultra_fix_reverification, 2026-08-03): FIX A — fotrelativt
effective_depth (origo-offset-hålet: platt hopp mätte trace-djup 67.8 > 56
och betalade gapbonus; nu ~0 ⇒ diskat) med omkalibrerad stub som kan
representera BÅDE platt golv och gropgeometri + explicit platthoppsfall;
FIX C — takeoff-episoder termineras vid första landningen (anti-kedjefarm);
FIX D — kanoniskt fartband 350-450 (analyst_fas1_validation.md).
"""
import numpy as np

from rl import spec as S
from rl.env import StubBackend
from rl.env_gate2 import Gate2Config, QWGate2Core

# teststates på stubbens golvnivå (golv z=32; z=40 ⇒ zmin-vakten 16 < 32 passerar)
STATES = [
    {"namn": "t0", "pos": [100.0, 200.0, 40.0], "yaw": 20.0},
    {"namn": "t1", "pos": [-300.0, 50.0, 40.0], "yaw": 199.0},
]


class GroundKeepBackend(StubBackend):
    """Stub med QW-lik markfriktion på noll-input-ticken: vel ×(1 − 4·dt)
    = ×0.948, sedan pos += vel·dt (samma ordning som pmove: friktion före
    förflyttning). Tidigare version behöll farten oförändrad och MASKERADE
    friktionsbettet (skeptikerfynd) — nu testas ÷0.948-kompensationen i
    reset() på riktigt: levererat band ska bli exakt det konfigurerade.

    GOLVGEOMETRI (skeptikerfix runda 2, origo-offset-hålet): tidigare stub-
    kalibrering lade golvet 200 u under luftbufferten och MASKERADE att ett
    platt hopp mätte trace-djup 67.8 (origo-offset 24 + apex) > tröskeln 56.
    Nu kan stubben representera BÅDE platt golv (trace från origo ≈ 24 +
    fothöjd, dvs golvytan z=32 rakt under) OCH gropgeometri: set_pit((lo,hi),
    golv_z) sänker golvet till golv_z för nedåttracar vars origo-x ligger i
    [lo,hi] — flygbanans mittparti kan alltså exponera ett äkta gap medan
    avstamp/landning står på golvytan."""

    def __init__(self):
        super().__init__()
        self._pit = None                 # ((x_lo, x_hi), golv_z) | None

    def set_pit(self, x_range, floor_z):
        self._pit = None if floor_z is None else (tuple(x_range), float(floor_z))

    def step(self, yaw_deg, pitch_deg, forwardmove, sidemove, jump):
        if self.onground and not jump and abs(forwardmove) < 1e-9 \
                and abs(sidemove) < 1e-9:
            self.vel[:2] *= (1.0 - 4.0 * S.TICK_DT)
            self.pos += self.vel * S.TICK_DT
            return self.pos.copy(), self.vel.copy(), True, 0, False
        return super().step(yaw_deg, pitch_deg, forwardmove, sidemove, jump)

    def trace_rays(self, origins, dirs, max_dist):
        frac = np.asarray(super().trace_rays(origins, dirs, max_dist),
                          dtype=np.float32).copy()
        if self._pit is not None:
            (lo, hi), pit_z = self._pit
            for i in range(len(dirs)):
                if dirs[i][2] < -1e-6 and lo <= origins[i][0] <= hi:
                    t = (origins[i][2] - pit_z) / -dirs[i][2]
                    frac[i] = min(max(t, 0.0), max_dist) / max_dist
        return frac


def make_takeoff_env(backend=None, states=STATES, seed=7, **kw):
    b = backend or GroundKeepBackend()
    b.X_WALL = 1e6
    return QWGate2Core(b, cfg=Gate2Config(spawn_takeoff_states=states, **kw),
                       rng=np.random.default_rng(seed))


def test_pick_spawn_returns_triple_in_band():
    env = make_takeoff_env()
    for _ in range(20):
        pos, yaw, speed, tgt = env._pick_spawn()
        # FIX D: kanoniskt fartband 350-450 (analyst_fas1_validation.md)
        assert 350.0 <= speed <= 450.0
        assert tgt is None                # STATES saknar landing_2d ⇒ inget mål
        src = min(STATES, key=lambda s: np.hypot(pos[0] - s["pos"][0],
                                                 pos[1] - s["pos"][1]))
        assert abs(yaw - src["yaw"]) <= 6.0 + 1e-9        # yaw-jitter ±6
        assert pos[2] == src["pos"][2] + 8.0              # +8 z som idag


def test_pick_spawn_jitter_is_tangential():
    # pos-jitter ska ligga LÄNGS kanten (vinkelrätt mot avstampsriktningen) —
    # aldrig trycka spawnen ut i gapet eller bakåt
    env = make_takeoff_env(states=[STATES[0]], takeoff_yaw_jitter=0.0,
                           takeoff_pos_jitter=12.0)
    fwd = np.array([np.cos(np.radians(20.0)), np.sin(np.radians(20.0))])
    seen_off_axis = False
    for _ in range(20):
        pos, yaw, _, _tgt = env._pick_spawn()
        assert yaw == 20.0
        delta = pos[:2] - np.array(STATES[0]["pos"][:2])
        assert abs(float(delta @ fwd)) < 1e-9             # noll längs yaw
        assert np.linalg.norm(delta) <= 12.0 + 1e-9
        seen_off_axis = seen_off_axis or np.linalg.norm(delta) > 1.0
    assert seen_off_axis                                  # jittern är aktiv


def test_takeoff_speed_range_configurable():
    env = make_takeoff_env(takeoff_speed_range=(200.0, 330.0))
    speeds = [env._pick_spawn()[2] for _ in range(30)]
    assert all(200.0 <= s <= 330.0 for s in speeds)
    assert max(speeds) - min(speeds) > 20.0               # faktiskt slumpad


def test_reset_injects_speed_after_settling():
    env = make_takeoff_env(states=[STATES[0]], takeoff_yaw_jitter=0.0,
                           takeoff_pos_jitter=0.0)
    for _ in range(5):
        env.reset()
        assert env.onground                               # grundad kantstart
        sp = float(np.hypot(env.vel[0], env.vel[1]))
        # friktionskompensationen ÷0.948 ⇒ LEVERERAT band efter synk-ticken
        # (som tar ×0.948) är exakt det konfigurerade (FIX D: 350-450)
        assert 350.0 - 1e-6 <= sp <= 450.0 + 1e-6
        vdir = env.vel[:2] / sp
        fwd = np.array([np.cos(np.radians(env.yaw)), np.sin(np.radians(env.yaw))])
        assert float(vdir @ fwd) > 0.999                  # riktad längs yaw
        assert env.vel[2] == 0.0                          # horisontell injektion


def test_spawn_speed_cleared_when_all_settling_attempts_fail():
    # Skeptikerfix (spawn_speed-i-grop-läckan): state 200 u över stubbgolvet ⇒
    # settlingen landar på z=32 < zmin-24 och kasseras alla 6 gånger — då ska
    # ingen fart injiceras där boten faktiskt hamnade (t.ex. nere i gropen)
    states = [{"namn": "hög", "pos": [100.0, 200.0, 200.0], "yaw": 20.0}]
    env = make_takeoff_env(states=states)
    env.reset()
    assert env._spawn_speed is None
    assert float(np.hypot(env.vel[0], env.vel[1])) == 0.0


def test_takeoff_envs_pay_no_novelty():
    # Skeptikerfix (novelty-förnybarheten): takeoff-envs resettas ~5x oftare
    # på samma 8 states — voxelnyheten där vore en förnybar farm. Vald åtgärd
    # (den enklare): bonus 0.0; seen-setet lever kvar för novel_voxels-mätaren.
    env = make_takeoff_env()
    assert env.novelty.bonus == 0.0
    assert env.novelty.step(np.array([5000.0, 5000.0, 32.0]), 300.0) == 0.0
    assert len(env.novelty.seen) == 1                     # mätaren registrerar ändå
    # icke-takeoff-envs behåller konfigurerad bonus
    b = StubBackend()
    b.X_WALL = 1e6
    env2 = QWGate2Core(b, cfg=Gate2Config(spawn_mode="fixed"),
                       rng=np.random.default_rng(3))
    assert env2.novelty.bonus == 1.5


def test_reset_without_takeoff_states_keeps_zero_speed():
    # bitkompatibilitet: övriga spawn-grenar returnerar speed=None ⇒ ingen injektion
    b = StubBackend()
    b.X_WALL = 1e6
    env = QWGate2Core(b, cfg=Gate2Config(spawn_mode="fixed"),
                      rng=np.random.default_rng(3))
    env.reset()
    assert env._spawn_speed is None
    assert float(np.hypot(env.vel[0], env.vel[1])) == 0.0


def test_transition_rarity_anneal_decays_per_cell():
    from rl.rewards_gate2 import TransitionRarity
    tr = TransitionRarity(ref=1.0)
    a = np.array([100.0, 0.0, 232.0])
    b = np.array([400.0, 0.0, 232.0])
    assert tr.anneal(a, b) == 1.0                         # orörd cell: full extra
    tr.note(a, b)
    assert abs(tr.anneal(a, b) - np.sqrt(1 / 2)) < 1e-12  # √(ref/(n+1))
    for _ in range(24):
        tr.note(a, b)
    assert tr.anneal(a, b) < 0.2 + 1e-9                   # ~baspoäng efter ~25
    # annan transitioncell opåverkad
    far = np.array([-2000.0, -2000.0, 32.0])
    assert tr.anneal(far, b) == 1.0
    # cap: ref>1 klipps vid 1.0 (extra överstiger aldrig ×2)
    tr9 = TransitionRarity(ref=9.0)
    assert tr9.anneal(a, b) == 1.0
    tr9.note(a, b)
    assert tr9.anneal(a, b) == 1.0                        # √(9/2)>1 ⇒ capad


def test_air_landing_bonus_deep_anneal():
    from rl.rewards_gate2 import AirLandingBonus
    ab = AirLandingBonus()
    base = ab.gap_base * min(200.0 / ab.GAP_MIN_SPAN, ab.GAP_SPAN_CAP)
    # default 1.0 = gamla ×2-semantiken (bitkompatibel)
    assert ab.landing(200.0, 0.0, 244.0) == ab.landing(200.0, 0.0, 244.0, 1.0)
    assert abs(ab.landing(200.0, 0.0, 244.0) - 2.0 * base) < 1e-12
    # anneal 0 ⇒ baspoäng
    assert abs(ab.landing(200.0, 0.0, 244.0, deep_anneal=0.0) - base) < 1e-12
    # grunda gap (djup < 141) berörs inte av annealingen
    shallow = ab.landing(200.0, 0.0, 100.0)
    assert ab.landing(200.0, 0.0, 100.0, deep_anneal=0.0) == shallow
    # klätterbonusen berörs inte
    climb = ab.landing(60.0, 32.8, 0.0)
    assert ab.landing(60.0, 32.8, 0.0, deep_anneal=0.0) == climb


def _land_gap(env, takeoff_x=100.0, land_z=56.0, jumped=True, pit_floor=-224.0):
    """Simulerad gap-landning genom takeoff- och landningsgrenarna i
    _air_segment — FOTRELATIVT omkalibrerad (skeptikerfix runda 2): avstamp
    och landning på ledge-ORIGONIVÅ z=56 (fotnivå 32 = stubbens golvyta),
    luftbuffert på origoapex ~101; gropen läggs i banans mittparti via
    stubbens set_pit. effective_depth = (56−24) − pit_floor:
      −224 ⇒ 256 (deep, dm3-gropens verkliga siffra)
      −68  ⇒ 100 (grunt gap, 56 < 100 < 141)
      None ⇒ platt golv 32 ⇒ 0 (diskat — origo-offset-hålets regressionsfall).
    jumped=False modellerar ren kantavgång (prev_og→luft utan hoppknapp)."""
    env.waterlevel = 0
    env.pos = np.array([takeoff_x, 0.0, 56.0])
    env.onground = False
    env._air_segment(prev_og=True, counted=True, jumped=jumped)   # avstampstick
    env.b.set_pit((takeoff_x + 25.0, takeoff_x + 175.0), pit_floor)
    env._air_buf = [np.array([takeoff_x + d, 0.0, 101.0]) for d in (50.0, 100.0, 150.0)]
    env.pos = np.array([takeoff_x + 200.0, 0.0, land_z])
    env.onground = True
    return env._air_segment(prev_og=False, counted=True)


def _land_deep_gap(env, takeoff_x=100.0):
    return _land_gap(env, takeoff_x=takeoff_x)


def test_gap_bonus_requires_landing_level():
    # Skeptikerfix (gropdyk-jackpotten, del b): gap-termen kräver landning på
    # ledgenivå — rise >= -GAP_MAX_DROP (-24). Gropdyk 48→-224 (rise -272)
    # ger noll trots span/djup.
    from rl.rewards_gate2 import AirLandingBonus
    ab = AirLandingBonus()
    assert ab.landing(200.0, -24.0, 244.0) > 0.0          # gränsen: -24 ok
    assert ab.landing(200.0, -25.0, 244.0) == 0.0         # strax under: diskad
    assert ab.landing(200.0, -272.0, 300.0) == 0.0        # gropdyket
    assert not ab.gap_qualifies(200.0, -272.0, 300.0)
    assert ab.gap_qualifies(200.0, 0.0, 244.0)


def test_edge_walkoff_pays_no_gap_bonus():
    # Skeptikerfix (gropdyk-jackpotten, del a): ren kantavgång (prev_og→luft
    # UTAN hoppknapp) öppnar inget luftsegment ⇒ ingen gapbonus, inget n_gap —
    # oavsett hur djupt golvet under banan är
    env = make_takeoff_env(vertical_rewards=True)
    assert _land_gap(env, jumped=False) == 0.0
    assert env.n_gap == 0
    assert env._air_takeoff is None
    # samma flygbana MED hopp betalar (regression: äkta hopp fortsatt belönade)
    assert _land_gap(env, jumped=True) > 0.0
    assert env.n_gap == 1


def test_pit_dive_landing_pays_nothing_and_is_not_counted():
    # Skeptikerfix (gropdyk-jackpotten + mätförgiftningen): hopp som landar på
    # gropgolvet (rise -256; fotrelativt djup dessutom ~0 — man landar PÅ
    # golvet under banan) ger noll bonus, räknas inte i n_gap och noterar
    # inte transitioncellen i rarityn
    env = make_takeoff_env(vertical_rewards=True, gap_anneal=True,
                           gap_anneal_ref=1.0)
    assert _land_gap(env, land_z=-200.0) == 0.0           # origo på gropgolvet
    assert env.n_gap == 0
    assert env.gap_rarity.n == {}                         # ingen anneal-nedräkning
    # och den äkta korsningen efteråt får fortfarande full jackpot
    base = env.air_bonus.gap_base * min(200.0 / env.air_bonus.GAP_MIN_SPAN,
                                        env.air_bonus.GAP_SPAN_CAP)
    assert abs(_land_deep_gap(env) - 2.0 * base) < 1e-9


def test_rarity_note_only_for_deep_gaps():
    # Skeptikerfix (rarity-asymmetrin): grunda gap (djup 56-141) i samma
    # cellpar ska INTE avklinga djupextran
    env = make_takeoff_env(vertical_rewards=True, gap_anneal=True,
                           gap_anneal_ref=1.0)
    base = env.air_bonus.gap_base * min(200.0 / env.air_bonus.GAP_MIN_SPAN,
                                        env.air_bonus.GAP_SPAN_CAP)
    shallow = _land_gap(env, pit_floor=-68.0)             # eff-djup 100: grunt
    assert abs(shallow - base) < 1e-9                     # betalas, utan djupextra
    assert env.n_gap == 1                                 # grunt gap räknas i n_gap
    assert env.gap_rarity.n == {}                         # men noteras INTE
    assert abs(_land_deep_gap(env) - 2.0 * base) < 1e-9   # djupextran orörd
    assert len(env.gap_rarity.n) == 1                     # djupt gap noteras


def _land_gap_at(env, land_xy, target, takeoff=(100.0, 0.0, 56.0),
                 pit_floor=-224.0):
    """Som _land_gap men med fri landningspunkt i planet + explicit
    takeoff-mål (sidovillkoret, skeptikerrunda 2b). Gropen läggs under
    banans mittparti (25/50/75 %-punkterna) oavsett riktning — geometrin är
    alltså en ÄKTA void-bana i alla fall; det enda som skiljer klipp från
    korsning är VART den landar (skeptikerns §3: kartfri separation omöjlig)."""
    env.waterlevel = 0
    t = np.array(takeoff)
    env.pos = t.copy()
    env.onground = False
    env._takeoff_target = None if target is None \
        else np.asarray(target, dtype=float)
    env._air_segment(prev_og=True, counted=True, jumped=True)   # avstampstick
    land = np.array([land_xy[0], land_xy[1], takeoff[2]])
    pts = [t + f * (land - t) for f in (0.25, 0.5, 0.75)]
    xs = [float(p[0]) for p in pts]
    env.b.set_pit((min(xs) - 5.0, max(xs) + 5.0), pit_floor)
    env._air_buf = [np.array([p[0], p[1], 101.0]) for p in pts]
    env.pos = land
    env.onground = True
    return env._air_segment(prev_og=False, counted=True)


def test_takeoff_target_saved_on_reset_and_none_elsewhere():
    # Sidovillkoret (skeptikerrunda 2b): _pick_spawn sparar valt states
    # landing_2d; övriga grenar (och states utan landing_2d) ger None
    states = [{"namn": "t0", "pos": [100.0, 200.0, 40.0], "yaw": 20.0,
               "landing_2d": [600.0, 200.0]}]
    env = make_takeoff_env(states=states)
    env.reset()
    assert env._takeoff_target is not None
    assert np.allclose(env._takeoff_target, [600.0, 200.0])
    env2 = make_takeoff_env()                      # STATES saknar landing_2d
    env2.reset()
    assert env2._takeoff_target is None
    b = StubBackend()
    b.X_WALL = 1e6
    env3 = QWGate2Core(b, cfg=Gate2Config(spawn_mode="fixed"),
                       rng=np.random.default_rng(3))
    env3.reset()
    assert env3._takeoff_target is None


def test_takeoff_progression_condition_blocks_corner_clip_pays_crossing():
    # Sidovillkoret (skeptikerrunda 2b, ultra_fix_reverification2 §4):
    # gapbonus i takeoff-envs kräver prog = ((landning−takeoff)·u)/d² >= 0.6
    # (u = takeoff→landing_2d). Verkliga separationstal (riktiga qwsim):
    # hörnklipp 0,054-0,444 ⇒ 0; äkta korsning 0,805-0,902 ⇒ full bonus.
    from rl.env_gate2 import TAKEOFF_PROG_MIN
    assert TAKEOFF_PROG_MIN == 0.6
    env = make_takeoff_env(vertical_rewards=True)
    tgt = [600.0, 0.0]                             # d = 500 från takeoff (100,0)
    full = env.air_bonus.gap_base * env.air_bonus.GAP_SPAN_CAP * 2.0   # 15.0
    # hörnklipp, strafe-klippets uppmätta prog 0,079: nästan vinkelrät
    # landning på samma sidas rim — span 203,9 >= 150, äkta void under banan
    assert _land_gap_at(env, (139.5, 200.0), tgt) == 0.0
    assert env.n_gap == 0                          # n_gap-förgiftningen nollad
    # värsta uppmätta klippet (fan −35°): prog 0,444 — fortfarande diskat
    assert _land_gap_at(env, (322.0, 200.0), tgt) == 0.0
    assert env.n_gap == 0
    # äkta korsning, uppmätt prog-band 0,805-0,902: prog 0,85 ⇒ full jackpot
    b = _land_gap_at(env, (525.0, 20.0), tgt)
    assert abs(b - full) < 1e-9
    assert env.n_gap == 1
    # samma klippgeometri UTAN mål (strövande semantik / states utan
    # landing_2d) betalar som förut — villkoret gäller ENDAST med mål
    assert _land_gap_at(env, (139.5, 200.0), None) > 0.0
    assert env.n_gap == 2
    # icke-takeoff-env: oförändrad semantik (inget mål existerar där)
    b2 = GroundKeepBackend()
    b2.X_WALL = 1e6
    env2 = QWGate2Core(b2, cfg=Gate2Config(spawn_mode="fixed",
                                           vertical_rewards=True),
                       rng=np.random.default_rng(3))
    assert _land_gap_at(env2, (131.6, 200.0), None) > 0.0


def test_flat_hop_pays_no_gap_bonus_and_no_n_gap():
    # FIX A-regressionen (origo-offset-hålet, skeptikerrunda 2): platt hopp
    # över plant golv — span 200 >= 150, äkta hopp, nivåneutral landning —
    # betalar NOLL och räknas inte i n_gap. Gamla origo-tracen mätte här
    # 24 (origo-offset) + ~44 (apex) = 67.8 > GAP_MIN_DEPTH 56 och betalade
    # (skeptikerns fan-probe: 261/261 icke-korsningar).
    env = make_takeoff_env(vertical_rewards=True)
    assert _land_gap(env, pit_floor=None) == 0.0          # platt golv ⇒ diskat
    assert env.n_gap == 0
    # 16-24u-steget (NV-klassens geometri) är också under tröskeln
    assert _land_gap(env, pit_floor=8.0) == 0.0           # eff-djup 24 < 56
    assert env.n_gap == 0
    # och gropen betalar fortfarande (positiv kontroll i samma geometri)
    assert _land_gap(env) > 0.0                           # eff-djup 256
    assert env.n_gap == 1


def test_flat_hop_full_loop_zero_bonus_and_takeoff_terminates_on_landing():
    # Helt varv genom core.step på stubbens PLATTA golv: äkta hopp i
    # 350-450-fart ger span >> 150 (frestande farmgeometri) men fotrelativt
    # djup ~0 ⇒ landing() anropas och betalar 0, n_gap 0. FIX C: episoden
    # termineras på landningsticken (ingen kedjefarmning inom episoden).
    env = make_takeoff_env(states=[STATES[0]], vertical_rewards=True,
                           takeoff_yaw_jitter=0.0, takeoff_pos_jitter=0.0)
    calls = []
    orig = env.air_bonus.landing
    def spy(span, rise, effective_depth, deep_anneal=1.0):
        b = orig(span, rise, effective_depth, deep_anneal=deep_anneal)
        calls.append({"span": span, "depth": effective_depth, "bonus": b})
        return b
    env.air_bonus.landing = spy
    env.reset()
    box = np.zeros(2, dtype=np.float32)
    done, info = False, {}
    for t in range(300):
        _, _, done, info = env.step(box, 1, 0, 1 if t == 0 else 0)
        if done:
            break
    assert done and info["landed"] and not info["stuck"]  # FIX C: terminerad
    assert env.tick < env.cfg.max_ticks                   # ...FÖRE tidstaket
    assert len(calls) == 1                                # exakt en landning
    assert calls[0]["span"] >= 150.0                      # farmbar span...
    assert calls[0]["depth"] < 56.0                       # ...men inget gapdjup
    assert calls[0]["bonus"] == 0.0
    assert info["n_gap"] == 0


def test_non_takeoff_env_does_not_terminate_on_landing():
    # FIX C gäller ENDAST takeoff-spawnade episoder — strövande envs får
    # hoppa och landa fritt utan terminering
    b = StubBackend()
    b.X_WALL = 1e6
    env = QWGate2Core(b, cfg=Gate2Config(spawn_mode="fixed",
                                         vertical_rewards=True),
                      rng=np.random.default_rng(3))
    env.reset()
    box = np.zeros(2, dtype=np.float32)
    was_air = False
    for t in range(300):
        _, _, done, info = env.step(box, 1, 0, 1 if t == 0 else 0)
        if was_air and env.onground:
            assert not done and not info["landed"]
            return
        was_air = not env.onground
    raise AssertionError("ingen landning inträffade i stubbmiljön")


def test_transition_rarity_negative_ref_is_nan_guarded():
    # Skeptikerfix (NaN-vakten): negativt ref hade gett sqrt(negativt) = NaN
    # rakt in i PPO-belöningen
    from rl.rewards_gate2 import TransitionRarity
    tr = TransitionRarity(ref=-5.0)
    assert tr.ref == 0.0
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([300.0, 0.0, 0.0])
    assert np.isfinite(tr.anneal(a, b)) and tr.anneal(a, b) == 0.0
    tr.note(a, b)
    assert np.isfinite(tr.anneal(a, b))


def test_gap_anneal_decays_jackpot_in_env():
    env = make_takeoff_env(vertical_rewards=True, gap_anneal=True,
                           gap_anneal_ref=1.0)
    base = env.air_bonus.gap_base * min(200.0 / env.air_bonus.GAP_MIN_SPAN,
                                        env.air_bonus.GAP_SPAN_CAP)
    b0 = _land_deep_gap(env)
    assert abs(b0 - 2.0 * base) < 1e-9                    # första: full jackpot
    b1 = _land_deep_gap(env)
    assert b1 < b0                                        # avklingar
    for _ in range(28):
        _land_deep_gap(env)
    b30 = _land_deep_gap(env)
    assert b30 < base * 1.25                              # ~baspoäng efter ~25+
    assert env.n_gap == 31                                # gate-räkningen orörd
    # annan transitioncell: jackpotten tillbaka på full extra
    assert abs(_land_deep_gap(env, takeoff_x=3000.0) - 2.0 * base) < 1e-9


def test_gap_anneal_off_by_default():
    env = make_takeoff_env(vertical_rewards=True)
    assert env.gap_rarity is None
    b0 = _land_deep_gap(env)
    assert _land_deep_gap(env) == b0                      # ingen avklingning


def test_sf_env_takeoff_worker_branch_and_datafile():
    from types import SimpleNamespace
    from rl.sf_env import make_env_gate2
    cfg = SimpleNamespace(qw_backend="stub", qw_gate1_mix_workers=0,
                          qw_hex_spawn_workers=0, qw_ra_spawn_workers=0,
                          qw_ledge_spawn_workers=0, qw_takeoff_spawn_workers=2,
                          qw_mega_spawn_workers=1, qw_takeoff_max_ticks=77 * 12,
                          train_dir=None)
    env = make_env_gate2("qw_gate2", cfg, {"worker_index": 1})
    st = env.core.cfg.spawn_takeoff_states
    # 2 korsningar (rq/qr) × 2 ankare, enbart SO-sidan — NV-sidan geometrifälld
    # (platt golv utan gap på kordan + vägg i siktlinjen; se datafilens
    # "geometriverifiering")
    assert st is not None and len(st) == 4
    assert env.core.cfg.max_ticks == 77 * 12              # episodtaket (graften)
    # FIX D: kanoniskt human-lyckat p50 372.8/p90 418.6/max 451.4
    assert env.core.cfg.takeoff_speed_range == (350.0, 450.0)
    # workern EFTER takeoff-bandet är mega (region, inga takeoff-states)
    env2 = make_env_gate2("qw_gate2", cfg, {"worker_index": 2})
    assert env2.core.cfg.spawn_takeoff_states is None
    assert env2.core.cfg.spawn_region is not None
    assert env2.core.cfg.max_ticks == 77 * 60             # fulla 60 s


def test_takeoff_states_lie_on_ledge_mask_with_correct_side_and_aim():
    from rl.jump_gates import QUAD, RING, _side, ledge_centers
    from rl.sf_env import _takeoff_states
    states = _takeoff_states()
    # endast SO-sidans 4 states (NV-sidan borttagen 2026-08-03: uppmätt platt
    # golv utan gap på kordan + vägg i siktlinjen — se datafilens kommentar)
    assert len(states) == 4
    assert len({s["namn"] for s in states}) == 4
    assert all("SO" in s["namn"] for s in states)
    cs = ledge_centers()
    for s in states:
        p = np.asarray(s["pos"], dtype=float)
        # exakt på ett stött OPEN-maskcentrum (snappad, inte fri koordinat)
        d = np.min(np.linalg.norm(cs - p, axis=1))
        assert d < 1e-6, s["namn"]
        assert _side(p) < -100.0, s["namn"]               # SO-sidan
        assert 40.0 < p[2] < 130.0                        # plattformsbandet
        # yaw pekar mot MÅLplattformen
        dst = QUAD if s["namn"].startswith("rq") else RING
        fwd = np.array([np.cos(np.radians(s["yaw"])), np.sin(np.radians(s["yaw"]))])
        to_dst = dst[:2] - p[:2]
        assert float(fwd @ (to_dst / np.linalg.norm(to_dst))) > 0.7, s["namn"]
