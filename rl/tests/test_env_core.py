"""Enhetstester för env-kärnan mot StubBackend (fysikfritt — loop/spec/curriculum).

Körs i huvud-venven: python -m pytest rl/tests/ -q
"""
import numpy as np
import pytest

from rl import spec as S
from rl.env import QWEnvCore, StubBackend, EpisodeConfig
from rl.rewards_gate1 import (Curriculum, StageCriteria, StepState,
                              reward_stage1, reward_stage4)


def make_env(max_ticks=77):
    return QWEnvCore(StubBackend(), Curriculum(),
                     cfg=EpisodeConfig(max_ticks=max_ticks))


def test_obs_shape_and_range():
    env = make_env()
    obs = env.reset()
    assert obs.shape == (env.obs_spec.n_obs,)
    n_rays = env.obs_spec.rays.n_rays
    assert np.all(obs[:n_rays] >= 0.0) and np.all(obs[:n_rays] <= 1.0)
    assert np.isfinite(obs).all()


def test_ray_geometry_counts():
    rs = S.RaySpec()
    dirs = rs.directions(yaw_deg=37.0)
    assert dirs.shape == (rs.n_rays, 3)
    norms = np.linalg.norm(dirs, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_forward_run_progresses_and_rewards_positive():
    env = make_env(max_ticks=77 * 3)
    env.reset()
    total = 0.0
    for _ in range(77 * 3):
        obs, r, done, info = env.step(np.zeros(2), fwd=1, side=0, jump=0)
        total += r
        if done:
            break
    assert env.pos[1] > env.cfg.start_pos[1] + 500  # kom framåt
    assert total > 0.0                              # steg 1 belönar framdrift


def test_action_mapping_side_signs():
    yaw, pitch, fm, sm, jb = S.action_to_usercmd(
        np.zeros(2), fwd=0, side=1, jump=0, yaw_deg=0.0, pitch_deg=0.0)
    assert sm < 0  # vänster är negativ sidemove i QW
    yaw, pitch, fm, sm, jb = S.action_to_usercmd(
        np.zeros(2), fwd=0, side=2, jump=0, yaw_deg=0.0, pitch_deg=0.0)
    assert sm > 0


def test_yaw_wraps_and_pitch_clamps():
    yaw, pitch, *_ = S.action_to_usercmd(
        np.array([1.0, 1.0]), 0, 0, 0, yaw_deg=359.0, pitch_deg=79.0)
    assert 0.0 <= yaw < 360.0
    assert pitch <= S.PITCH_MAX


def test_stage4_wall_hit_penalized():
    s = StepState(pos=np.array([224.0, 0.0, 32.0]),
                  vel=np.array([0.0, 100.0, 0.0]),
                  prev_vel=np.array([0.0, 500.0, 0.0]),
                  onground=False, prev_onground=False, jumped_this_tick=False)
    assert reward_stage4(s) < reward_stage1(s)  # 400 u/s förlust straffas hårt


def test_curriculum_advances_and_terminates():
    crit = StageCriteria(min_episodes=5)
    cur = Curriculum(crit, window=5)
    for _ in range(5):
        cur.end_episode(peak_speed=350.0, collision_loss_total=0.0)
    assert cur.stage == 1
    for _ in range(5):
        cur.end_episode(peak_speed=600.0, collision_loss_total=0.0)
    assert cur.stage == 2
    for _ in range(5):
        cur.end_episode(peak_speed=600.0, collision_loss_total=0.0)
    assert cur.stage == 3
    for _ in range(4):
        cur.end_episode(peak_speed=810.0, collision_loss_total=50.0)
    assert not cur.done
    cur.end_episode(peak_speed=810.0, collision_loss_total=50.0)
    assert cur.done  # Gate 1-KANDIDAT — beviset sker på riktiga servern


def test_curriculum_does_not_advance_below_threshold():
    crit = StageCriteria(min_episodes=5)
    cur = Curriculum(crit, window=5)
    for _ in range(50):
        cur.end_episode(peak_speed=200.0, collision_loss_total=0.0)
    assert cur.stage == 0
