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
    window = ab.landing(span=170.0, rise=-30.0, max_floor_depth=100.0)
    assert 0.0 < window < mega
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
    # ramla: ring → ledge NV → ner i gropen
    fall = seg(RING, mid_nv, 30) + [[560, 20, PIT_Z-50, 300]]*5
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
