"""Sample Factory-adapter: gymnasium.Env ovanpå QWEnvCore.

Körs i sim/.venv-sf (gymnasium 0.29.1, sample-factory 2.1.1). Kärnan (rl/env.py)
är gym-fri; det här skalet gör bara spaces + API-formen SF kräver:
konstruktor (full_env_name, cfg, render_mode) + register_env-fabrik.

Handlingsrum (STACK.md-skissen, nativt stöd via TupleActionDistribution):
    Tuple(Box(2) platt 1-D, Discrete(2) fwd, Discrete(3) side, Discrete(2) jump)
"""
from __future__ import annotations

import gymnasium as gym
import numpy as np

from rl import spec as S
from rl.env import EpisodeConfig, QWEnvCore, StubBackend
from rl.rewards_gate1 import Curriculum


def _make_backend(cfg):
    """qwsim när den finns; stub annars (endast smoke — träning kräver qwsim)."""
    backend_name = getattr(cfg, "qw_backend", "qwsim") if cfg is not None else "qwsim"
    if backend_name == "stub":
        return StubBackend()
    from rl.qwsim_backend import QwsimBackend  # landar med libqwsim (agent B)
    return QwsimBackend(cfg)


class QWGate1Env(gym.Env):
    def __init__(self, full_env_name: str, cfg=None, render_mode=None):
        self.name = full_env_name
        self.render_mode = render_mode
        self.core = QWEnvCore(_make_backend(cfg), Curriculum(), cfg=EpisodeConfig())
        n_obs = self.core.obs_spec.n_obs
        self.observation_space = gym.spaces.Box(-4.0, 4.0, shape=(n_obs,), dtype=np.float32)
        self.action_space = gym.spaces.Tuple((
            gym.spaces.Box(-1.0, 1.0, shape=(2,), dtype=np.float32),
            gym.spaces.Discrete(2),   # framåt
            gym.spaces.Discrete(3),   # sidled: ingen/vänster/höger
            gym.spaces.Discrete(2),   # hopp
        ))

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        return self.core.reset().astype(np.float32), {}

    def step(self, action):
        box, fwd, side, jump = action
        obs, r, done, info = self.core.step(np.asarray(box, dtype=np.float32),
                                            int(fwd), int(side), int(jump))
        # SF/gymnasium: terminated (mål/krash) vs truncated (tidsgräns)
        truncated = done and self.core.tick >= self.core.cfg.max_ticks
        terminated = done and not truncated
        return obs.astype(np.float32), r, terminated, truncated, info

    def render(self):
        return None


def register(name: str = "qw_gate1"):
    from sample_factory.envs.env_utils import register_env
    register_env(name, lambda fen, cfg, render_mode=None: QWGate1Env(fen, cfg, render_mode))
