import numpy as np

from rl.rewards_gate2 import VoxelNovelty, kinetic_multiplier, reward_gate2
from rl.rewards_gate1 import StepState


def _state(vel, prev_vel=None, pos=(0.0, 0.0, 32.0)):
    return StepState(pos=np.array(pos), vel=np.array(vel, dtype=float),
                     prev_vel=np.array(prev_vel if prev_vel is not None else vel,
                                       dtype=float),
                     onground=False, prev_onground=False, jumped_this_tick=False)


def test_novelty_once_per_voxel_scaled_by_speed():
    nv = VoxelNovelty(bonus_per_voxel=0.1)
    p = np.array([10.0, 10.0, 32.0])
    fast = nv.step(p, 800.0)
    again = nv.step(p, 800.0)
    assert fast > 0.0 and again == 0.0
    nv2 = VoxelNovelty(bonus_per_voxel=0.1)
    slow = nv2.step(p, 100.0)
    assert slow < fast  # långsam upptäckt ger mindre


def test_novelty_reset_clears():
    nv = VoxelNovelty()
    p = np.array([0.0, 0.0, 32.0])
    nv.step(p, 500.0)
    nv.reset()
    assert nv.step(p, 500.0) > 0.0


def test_kinetic_multiplier_penalizes_wall_ahead():
    # 8 strålar i planet; agenten rör sig +X
    dirs = np.array([[np.cos(a), np.sin(a), 0.0]
                     for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)])
    s = _state([600.0, 0.0, 0.0])
    open_fracs = np.ones(8)
    wall_ahead = np.ones(8); wall_ahead[0] = 0.02   # vägg tätt intill i +X
    assert kinetic_multiplier(s, wall_ahead, dirs) < kinetic_multiplier(s, open_fracs, dirs)


def test_collision_dominates():
    dirs = np.array([[1.0, 0.0, 0.0]])
    fracs = np.ones(1)
    crash = _state([50.0, 0.0, 0.0], prev_vel=[700.0, 0.0, 0.0])
    ok = _state([700.0, 0.0, 0.0])
    nv = VoxelNovelty()
    r_crash = reward_gate2(crash, fracs, dirs, nv)
    nv2 = VoxelNovelty()
    r_ok = reward_gate2(ok, fracs, dirs, nv2)
    assert r_crash < -1.0 and r_ok > r_crash


def test_air_bonus_thresholds_from_corpus():
    from rl.rewards_gate2 import AirLandingBonus
    ab = AirLandingBonus()
    # platt bunnyhopp: span 280 men golvdjup ~apex 44 ⇒ ingen gapbonus
    assert ab.landing(span=280.0, rise=0.0, max_floor_depth=44.0) == 0.0
    # SNG→mega (korpus: span p50 182, golvdjup 244) ⇒ djup nivå, ×2
    mega = ab.landing(span=182.0, rise=0.0, max_floor_depth=244.0)
    assert mega > 0.0
    # fönsterinflygning (span 150-191, djup 13-128): grunda varianten ska betala
    # — rise -20 (2026-08-03: landningsnivåkravet rise >= -24, skeptikerfixen
    # mot gropdyk-jackpotten; inflygningar mer än 24 u under avstampet betalar
    # inte längre — gropdyk 48→-224 var straffFRITT farmbart)
    window = ab.landing(span=170.0, rise=-20.0, max_floor_depth=100.0)
    assert 0.0 < window < mega
    assert ab.landing(span=170.0, rise=-30.0, max_floor_depth=100.0) == 0.0
    # klätterhopp (RA-trappan: rise p50 32.8) betalar utan gapkrav
    climb = ab.landing(span=60.0, rise=32.8, max_floor_depth=0.0)
    assert climb > 0.0
    # under klättertröskeln (vanligt hopp på plan mark) ⇒ noll
    assert ab.landing(span=60.0, rise=10.0, max_floor_depth=0.0) == 0.0


def test_cell_rarity_boosts_unseen_damps_oversat():
    from rl.rewards_gate2 import CellRarity
    cr = CellRarity(alpha=0.5)
    camp = np.array([100.0, 100.0, 32.0])
    for _ in range(80):
        cr.note(camp)
    for _ in range(20):
        cr.note(np.array([1000.0, 1000.0, 32.0]))
    cr.end_episode()
    unseen = np.array([-4000.0, -4000.0, 32.0])
    assert cr.mult(unseen) == cr.hi           # aldrig besökt ⇒ max boost
    assert cr.mult(camp) == cr.lo             # 80 % av tiden ⇒ dämpad
    assert cr.mult(unseen) > cr.mult(np.array([1000.0, 1000.0, 32.0]))


def test_novelty_mult_scales_payment():
    p = np.array([50.0, 50.0, 32.0])
    s = _state([500.0, 0.0, 0.0], pos=p)
    dirs = np.array([[1.0, 0.0, 0.0]]); fracs = np.ones(1)
    base = reward_gate2(s, fracs, dirs, VoxelNovelty(), novelty_mult=1.0)
    boosted = reward_gate2(s, fracs, dirs, VoxelNovelty(), novelty_mult=4.0)
    assert boosted > base


def test_jump_gate_ring_quad_detection():
    from rl.jump_gates import analyze, RING, QUAD, PIT_Z
    def seg(a, b, n, z=56.0):
        return [[a[0]+(b[0]-a[0])*t/n, a[1]+(b[1]-a[1])*t/n, z, 500] for t in range(n)]
    mid_nv = [520.0, 400.0]     # NV om ring→quad-axeln, utanför plattformarna
    # lyckat: ring → ledge NV → quad på plattformsnivå
    ok = seg(RING, mid_nv, 30) + seg(mid_nv, QUAD, 30) + [[QUAD[0], QUAD[1], 56, 500]]*5
    # ramla: ring → ledge NV med progression mot quad (d<350) → ner i gropen
    near_q = [650.0, 320.0]     # NV-ledge, 303 u från quad-centrum
    fall = seg(RING, mid_nv, 20) + seg(mid_nv, near_q, 15) + [[620, 120, PIT_Z-50, 300]]*5
    dump = {"episodes": [{"path": ok}, {"path": fall}]}
    res = analyze(dump)
    g = res["gates"]["ring→quad NV"]
    assert g["försök"] == 2 and g["lyckade"] == 1 and g["ramla"] == 1
    assert g["nivå"] == 2
    assert res["gates"]["quad→ring SO"]["nivå"] == 0


def test_jump_gate_item_ladder():
    from rl.jump_gates import analyze, RA
    # RA: närmar sig nerifrån (z<150) och når pickup
    up = [[RA[0], RA[1]-200, 40, 300]]*5 + \
         [[RA[0], RA[1]-100+i*10, 40+i*30, 300] for i in range(10)] + \
         [[RA[0], RA[1], 304, 300]]*3
    dump = {"episodes": [{"path": up}]}
    res = analyze(dump)
    assert res["gates"]["RA-tagningen"]["försök"] == 1
    assert res["gates"]["RA-tagningen"]["lyckade"] == 1


def test_jump_gate_item_airborne_arc_not_attempt():
    # review 4 (analyst 2026-08-02): luftburen hoppbåge som passerar
    # entré+80 inom d2<120 är INTE klättring — samtidighetssamplet måste
    # vara grundat (z-stabilt ±0.5 över ≥3 sampel). Underkända mega-claimet:
    # kedjade bunnyhops in i väggen, apex z 67.8 luftburet, max stödd z = entré.
    from rl.jump_gates import analyze, MEGA_SNG
    x, y = float(MEGA_SNG[0]), float(MEGA_SNG[1])
    ent = 40.0                                     # entré-z (< låg-tröskel 100)
    arc = [[x, y - 250, ent, 300]] * 4 + \
          [[x, y - 200 + i * 20, ent + (140.0 - 5.4 * (i - 5) ** 2), 300]
           for i in range(10)] + \
          [[x, y - 250, ent, 300]] * 4             # båge: apex ent+140 vid d2<120
    res = analyze({"episodes": [{"path": arc}]})
    assert res["gates"]["SNG-mega"]["försök"] == 0
    assert res["gates"]["SNG-mega"]["nivå"] == 0


def test_jump_gate_axial_pit_jump_not_side_attempt():
    # review 5 (analyst 2026-08-02): axialt gaphopp rakt ut i gropen fick
    # SO-etikett av 2 luftburna sampel strax utanför dödzonen med progression
    # intjänad i fritt fall UNDER ledgebandet. v5: sidogate kräver ledgeband-
    # närvaro (z 40-130, |perp| 100-300), progression i bandet och |side_acc|
    # >= 300. Axiala korsningar bokförs separat.
    from rl.jump_gates import QUAD, RING, analyze
    ax = (QUAD - RING)[:2]
    axn = ax / np.hypot(*ax)
    perp = np.array([-axn[1], axn[0]])          # +perp = NV-sidan
    path = [[*(QUAD[:2] - axn[:2] * 0), 56.0, 300]] * 4      # står på quad
    for k in range(10):                          # båge mot ring, sjunkande z
        pos2 = QUAD[:2] - axn * (80.0 + 60.0 * k) - perp * (104.0 if k in (4, 5) else 40.0)
        z = 30.0 - 6.0 * k                       # under bandet, över LEDGE_Z (-20)
        path.append([pos2[0], pos2[1], z, 300])  # d(ring) sjunker under 350
    path.append([*(RING[:2] + axn * 260), -150.0, 300])       # gropen
    res = analyze({"episodes": [{"path": path}]})
    assert all(v["försök"] == 0 for k, v in res["gates"].items() if "→" in k)
    assert res["axiala_gropkorsningar"]["försök"] == 1
    assert res["axiala_gropkorsningar"]["ramla"] == 1


def test_jump_gate_ledge_crossing_counts_with_mass():
    # positiv kontroll v6: riktig SO-maskvandring hela vägen som når fram
    # räknas som lyckat med korrekt sidoetikett.
    from rl.jump_gates import QUAD, RING, analyze
    path = [[*QUAD[:2], 56.0, 300]] * 4 + _so_ledge_walk() + \
           [[*RING[:2], 56.0, 300]] * 3
    res = analyze({"episodes": [{"path": path}]})
    g = res["gates"]["quad→ring SO"]
    assert (g["försök"], g["lyckade"]) == (1, 1)


def _ledge_walk(sign=-1, d_ring_stop=270.0):
    # verklig ledgevandring quad→ring ur v6-masken (analyst-review 6:
    # syntetiska perp-bandbanor kan hamna i gropens luftrum). sign=-1 SO
    # (har verkligt gap d_ring 330-555), +1 NV (kontinuerlig).
    from rl.jump_gates import RING, QUAD, _d2, _side, ledge_centers
    cs = ledge_centers()
    sel = [p for p in cs if _side(p) * sign > 0
           and _d2(p, RING) > d_ring_stop and _d2(p, QUAD) > 270.0]
    sel.sort(key=lambda p: -_d2(p, RING))         # från quad-sidan mot ring
    return [[p[0], p[1], p[2] + 8.0, 300] for p in sel[::3]]


def _so_ledge_walk(d_ring_stop=270.0):
    return _ledge_walk(-1, d_ring_stop)


def test_jump_gate_midgap_fall_counts_as_side_attempt():
    # v5.1/v6: mittgropsfall — genuin SO-maskvandring som ramlar före d<350
    # (gapmitten d=392) ska räknas; in-mask-progression 450.
    from rl.jump_gates import QUAD, RING, _d2, analyze
    walk = [q for q in _ledge_walk(+1) if _d2(q, RING) > 360.0]  # NV, ~360-450
    assert any(_d2(q, RING) < 450.0 for q in walk)
    path = [[*QUAD[:2], 56.0, 300]] * 4 + walk + \
           [[QUAD[0] - 300.0, QUAD[1] - 150.0, -150.0, 300]]   # gropen
    res = analyze({"episodes": [{"path": path}]})
    g = res["gates"]["quad→ring NV"]
    assert (g["försök"], g["ramla"]) == (1, 1)


def test_jump_gate_ungrounded_source_platform_is_axial():
    # v6 (analyst-review 6, ep14-klassen): källplattformsvistelse utan ett enda
    # grundat sampel (ren luftpassage över quad) kvalificerar inte sidogate.
    from rl.jump_gates import QUAD, RING, _d2, analyze
    walk = [q for q in _ledge_walk(+1) if _d2(q, RING) > 360.0]
    ups = [[QUAD[0], QUAD[1], z, 300] for z in (44.0, 88.0, 70.0, 96.0)]
    from rl.jump_gates import PIT_2D
    path = ups + walk + \
           [[PIT_2D[0], PIT_2D[1], -150.0, 300]]
    res = analyze({"episodes": [{"path": path}]})
    assert all(v["försök"] == 0 for k, v in res["gates"].items() if "→" in k)
    assert res["axiala_gropkorsningar"]["försök"] == 1


def test_jump_gate_band_graze_low_mass_is_axial():
    # v5.1/v6: kort maskgraze — når progression (<450) men sidomassan under
    # 14 u·s ⇒ axial, inte sidogate.
    from rl.jump_gates import QUAD, RING, _d2, _side, analyze, ledge_centers
    cs = [p for p in ledge_centers()
          if _side(p) > 0 and 360.0 < _d2(p, RING) < 450.0]   # NV: kontinuerlig
    cs.sort(key=lambda p: abs(_side(p)))          # minsta sidosignalen
    graze = [[p[0], p[1], p[2] + 8.0, 300] for p in cs[:2]]
    assert abs(sum(_side(q) for q in graze)) * 0.026 < 14.0
    path = [[*QUAD[:2], 56.0, 300]] * 4 + graze + \
           [[QUAD[0] - 300.0, QUAD[1] - 150.0, -150.0, 300]]   # gropen
    res = analyze({"episodes": [{"path": path}]})
    assert all(v["försök"] == 0 for k, v in res["gates"].items() if "→" in k)
    assert res["axiala_gropkorsningar"]["försök"] == 1


def test_jump_gate_anchored_midgap_fall_is_gate():
    # v6.1 "förankrat fall" (analyst-review 7): grundad maskvandring på käll-
    # kanten + luftbåge som når min-d < 450 UTANFÖR masken + grop ⇒ gate-ramla.
    from rl.jump_gates import QUAD, RING, _d2, _side, analyze, ledge_centers
    nv = [p for p in ledge_centers() if _side(p) > 0
          and p[2] == 48.0 and _d2(p, RING) > 500.0 and _d2(p, QUAD) > 270.0]
    nv.sort(key=lambda p: -_d2(p, RING))
    walk = [[p[0], p[1], 56.0, 300] for p in nv[-8:]]    # de 8 NÄRMAST ringen
                                                         # (konstant z ⇒ grundad)
    edge = np.array(walk[-1][:2])
    to_ring = (RING[:2] - edge) / np.linalg.norm(RING[:2] - edge)
    arc = []
    for k in range(1, 5):                                # luftbåge mot ring
        pos2 = edge + to_ring * (45.0 * k)
        arc.append([pos2[0], pos2[1], 56.0 + 30.0 - 9.0 * k * k, 300])
    from rl.jump_gates import PIT_2D
    path = [[*QUAD[:2], 56.0, 300]] * 4 + walk + arc + \
           [[PIT_2D[0], PIT_2D[1], -150.0, 300]]         # gropen (dPit=0)
    res = analyze({"episodes": [{"path": path}]})
    assert any(_d2(np.array(q), RING) < 450.0 for q in arc)
    g = res["gates"]["quad→ring NV"]
    assert (g["försök"], g["ramla"]) == (1, 1)


def test_jump_gate_airborne_overflight_is_axial():
    # v6.1: ep5/ep23-klassen — enbart LUFTBUREN maskkontakt (z varierar över
    # kolumnerna, aldrig grundad i transiten) + min-d < 450 + grop ⇒ axial.
    from rl.jump_gates import QUAD, RING, _d2, _side, analyze, ledge_centers
    nv = [p for p in ledge_centers() if _side(p) > 0
          and 360.0 < _d2(p, RING) < 700.0 and _d2(p, QUAD) > 270.0]
    nv.sort(key=lambda p: -_d2(p, RING))
    from rl.jump_gates import PIT_2D
    fly = [[p[0], p[1], p[2] + 20.0 + 7.0 * (i % 5), 300]
           for i, p in enumerate(nv[-10:])]              # närmast ringen; dz>0.5
    path = [[*QUAD[:2], 56.0, 300]] * 4 + fly + \
           [[PIT_2D[0], PIT_2D[1], -150.0, 300]]
    res = analyze({"episodes": [{"path": path}]})
    assert all(v["försök"] == 0 for k, v in res["gates"].items() if "→" in k)
    assert res["axiala_gropkorsningar"]["försök"] == 1


def test_jump_gate_retreat_requires_pit_exposure():
    # v7.2 (analyst-review 9): retreat utan gropexponering är sidogolvs-
    # cirkulation ⇒ inte gate-försök. v7.3 (analyst_73G_review): tröskeln 192
    # (korsningsenvelopen) — dPit i dörrtröskelgapet 192..260 räcker INTE
    # (botens underkända NV-retreat @8.9G-proben låg på 256).
    from rl.jump_gates import PIT_2D, QUAD, RING, _d2, _side, analyze, ledge_centers
    nv = [p for p in ledge_centers() if _side(p) > 0
          and _d2(p, PIT_2D) > 280.0 and _d2(p, QUAD) > 270.0 and _d2(p, RING) > 270.0]
    far = sorted([p for p in nv if _d2(p, RING) > 450.0], key=lambda p: -_d2(p, RING))
    mid = sorted([p for p in nv if _d2(p, RING) < 450.0], key=lambda p: _d2(p, RING))
    assert far and mid
    plat = [[*QUAD[:2], 56.0, 300]] * 4
    walk = [[p[0], p[1], 56.0, 300] for p in (far[:4] + mid[:3])]
    # cirkulation: in-mask-progression (d<450) men min dPit >= 280 hela vägen
    loop = plat + walk + walk[::-1] + plat
    r1 = analyze({"episodes": [{"path": loop}]})
    assert r1["gates"]["quad→ring NV"]["försök"] == 0
    import numpy as np
    m0 = np.array(mid[0][:2])
    u = (m0 - PIT_2D) / np.hypot(*(m0 - PIT_2D))
    # dörrtröskelzonen: dipp på dPit 200 (gamla bandet, i humandatas tomma gap)
    # ⇒ INTE retreat i v7.3
    dip200 = PIT_2D + u * 200.0
    near = plat + walk + [[dip200[0], dip200[1], 30.0, 300]] + walk[::-1] + plat
    r2 = analyze({"episodes": [{"path": near}]})
    assert r2["gates"]["quad→ring NV"]["försök"] == 0
    # genuint exponerad: dipp dPit 180 < RETREAT_PIT_R ⇒ gate-retreat
    dip180 = PIT_2D + u * 180.0
    expo = plat + walk + [[dip180[0], dip180[1], 30.0, 300]] + walk[::-1] + plat
    r3 = analyze({"episodes": [{"path": expo}]})
    g = r3["gates"]["quad→ring NV"]
    assert (g["försök"], g["retreat"]) == (1, 1)


def test_jump_gate_item_single_sample_stair_sprint_rejected():
    # v7.3 (analyst_73G_review, underkände RA-claimet @7.35G): ETT samtidighets-
    # sampel på låg höjd (trappspring i full fart) kvalificerar inte — kräver
    # dwell >= 0.15 s ELLER max grundad >= entré+130.
    from rl.jump_gates import APPROACH_MIN, RA, analyze
    x, y = float(RA[0]), float(RA[1])
    ent = 0.0
    # sprint: in lågt, passerar en +104-avsats med EXAKT ett kvalificerande
    # sampel (grundat kräver z-stabilitet: 3 sampel på samma z), vidare ut
    plat104 = [[x, y + 116, 104.0, 300]] * 3          # d2 116 < APPROACH_MIN
    path = [[x, y - 280, ent, 300]] * 4 + \
           [[x, y - 150, ent, 300]] * 2 + plat104 + \
           [[x, y - 150, ent, 300]] * 2 + [[x, y - 350, ent, 300]] * 3
    res = analyze({"episodes": [{"path": path}]})
    assert res["gates"]["RA-tagningen"]["försök"] == 0


def test_jump_gate_item_dwell_qualifies():
    # v7.3: samma lågklättring men med dwell >= 0.15 s (>=6 sampel @26 ms)
    # i samtidighetsvillkoret ⇒ försök (ej lyckat — pickup nås ej).
    from rl.jump_gates import RA, analyze
    x, y = float(RA[0]), float(RA[1])
    ent = 0.0
    plat104 = [[x, y + 116, 104.0, 300]] * 8          # 8 sampel: 6 grundade
    path = [[x, y - 280, ent, 300]] * 4 + \
           [[x, y - 150, ent, 300]] * 2 + plat104 + \
           [[x, y - 150, ent, 300]] * 2 + [[x, y - 350, ent, 300]] * 3
    res = analyze({"episodes": [{"path": path}]})
    g = res["gates"]["RA-tagningen"]
    assert (g["försök"], g["lyckade"]) == (1, 0)


def test_jump_gate_item_apex_quasi_stable_not_grounded():
    # bågAPEX är kvasi-z-stabil (dz 0.4/0.1 @26 ms) men behåller gravitationens
    # kurvatur d²z ≈ −0.5 — exakta samplen ur underkända mega-claimet (ep6,
    # sample 2282: z 67.4/67.8/67.7 på d2 117). Får inte räknas som grundat.
    from rl.jump_gates import analyze, MEGA_SNG
    x, y = float(MEGA_SNG[0]), float(MEGA_SNG[1])
    zs = [-16.0, -16.0, -16.0, 63.0, 65.0, 66.5, 67.4, 67.8, 67.7, 67.0,
          65.8, 64.0, -16.0, -16.0]
    ys = [y - 250, y - 250, y - 250, y - 135, y - 130, y - 126, y - 121,
          y - 117, y - 113, y - 109, y - 105, y - 102, y - 250, y - 250]
    path = [[x, yy, zz, 300] for yy, zz in zip(ys, zs)]
    res = analyze({"episodes": [{"path": path}]})
    assert res["gates"]["SNG-mega"]["försök"] == 0


def test_height_reward_speed_scaled_and_bounded():
    from rl.rewards_gate2 import height_reward, HEIGHT_Z_MIN, HEIGHT_Z_MAX
    # stillastående på RA-toppen betalar noll (anti-camping)
    assert height_reward(304.0, 0.0, 2.0) == 0.0
    hi = height_reward(304.0, 550.0, 2.0)          # högt och snabbt
    lo = height_reward(-264.0, 750.0, 2.0)         # gårgolv, snabbare
    assert hi > lo * 5                              # höjden dominerar golvet
    # rarity-dämpning halverar campad höjd
    assert height_reward(304.0, 550.0, 2.0, mult=0.5) < hi
    # utanför spannet klipps
    assert height_reward(HEIGHT_Z_MAX + 500, 550.0, 2.0) == height_reward(HEIGHT_Z_MAX, 550.0, 2.0)
