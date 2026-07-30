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
