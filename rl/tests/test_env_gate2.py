import numpy as np

from rl.env import StubBackend
from rl.env_gate2 import QWGate2Core, Gate2Config, STUCK_TICKS, load_spawns


def make_env(**kw):
    kw.setdefault("spawn_mode", "fixed")
    b = StubBackend()
    b.X_WALL = 1e6          # dm3-spawns ligger utanför stubbens korridorväggar
    return QWGate2Core(b, cfg=Gate2Config(**kw),
                       rng=np.random.default_rng(7))


def test_spawns_load_and_are_six():
    assert len(load_spawns()) == 6


def test_reset_uses_spawn_positions():
    env = make_env()
    obs = env.reset()
    assert obs.shape == (env.obs_spec.n_obs,)
    starts = {tuple(p[:2]) for p, _ in env.spawns}
    assert tuple(env.pos[:2]) in starts   # settling ändrar bara z


def test_stuck_terminates_with_penalty():
    env = make_env()
    env.reset()
    total = 0.0
    done = False
    for _ in range(STUCK_TICKS + 5):
        obs, r, done, info = env.step(np.zeros(2), fwd=0, side=0, jump=0)
        total += r
        if done:
            break
    assert done and info["stuck"]
    assert total < -4.0  # slutstraffet dominerar


def test_moving_agent_not_stuck_and_counts_speed():
    env = make_env(max_ticks=77)
    env.reset()
    for _ in range(77):
        obs, r, done, info = env.step(np.zeros(2), fwd=1, side=0, jump=0)
        if done:
            break
    assert not info["stuck"]
    assert info["mean_speed_counted"] > 100.0
    assert info["novel_voxels"] > 3


def test_spawn_region_filters():
    b = StubBackend()
    b.X_WALL = 1e6          # stubbens korridorväggar clampar annars dm3-spawnens x
    env = QWGate2Core(b,
                      cfg=Gate2Config(spawn_mode="fixed", spawn_region=((-1000, -400, -50), (-500, 0, 50))),
                      rng=np.random.default_rng(3))
    for _ in range(10):
        env.reset()
        assert tuple(env.pos[:2]) == (-880.0, -232.0)   # settling ändrar bara z
