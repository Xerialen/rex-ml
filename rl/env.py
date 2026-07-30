"""Miljökärnan: kopplar backend (qwsim | stub) till obs/action/reward.

Ren numpy och avsiktligt gym-fri — rl/sf_env.py lägger gymnasium-API:t ovanpå
(körs i sim/.venv-sf). Backend-protokollet speglar qwsim-API:t som libqwsim
bygger: reset/step per slot + batchad trace_rays.
"""
from __future__ import annotations

import dataclasses
import numpy as np

from . import spec as S
from .rewards_gate1 import Curriculum, StepState, _collision_loss


class Backend:
    """Protokoll. qwsim-backenden implementerar detta mot C++-modulen."""

    def reset(self, pos, vel, yaw_deg):  # -> None
        raise NotImplementedError

    def step(self, yaw_deg, pitch_deg, forwardmove, sidemove, jump):
        """-> (pos(3,), vel(3,), onground: bool, waterlevel: int, jump_held: bool)"""
        raise NotImplementedError

    def trace_rays(self, origins, dirs, max_dist):  # -> fractions (n,)
        raise NotImplementedError


class StubBackend(Backend):
    """ENDAST för enhetstester av env-loopen. Grovt QW-liknande, INTE fysikexakt:
    platt golv z=32, väggar x=±X_WALL, grav 800, hopp vz=270, markfart klipps 320.
    All riktig träning sker mot qwsim (bit-exakta pmove.c)."""

    X_WALL = 512.0

    def __init__(self):
        self.pos = np.zeros(3, dtype=np.float64)
        self.vel = np.zeros(3, dtype=np.float64)
        self.onground = True
        self.jump_held = False

    def reset(self, pos, vel, yaw_deg):
        self.pos = np.asarray(pos, dtype=np.float64).copy()
        self.vel = np.asarray(vel, dtype=np.float64).copy()
        self.onground = self.pos[2] <= 32.001
        self.jump_held = False

    def step(self, yaw_deg, pitch_deg, forwardmove, sidemove, jump):
        dt = S.TICK_DT
        yaw = np.radians(yaw_deg)
        f = np.array([np.cos(yaw), np.sin(yaw), 0.0])
        r = np.array([np.sin(yaw), -np.cos(yaw), 0.0])
        wish = f * forwardmove + r * sidemove
        wn = np.linalg.norm(wish[:2])
        if wn > 1e-6:
            wish /= wn
        if self.onground:
            if jump and not self.jump_held:
                self.vel[2] = 270.0
                self.onground = False
            else:
                sp = wn and min(320.0, wn)
                self.vel[:2] = wish[:2] * (320.0 if wn > 1e-6 else 0.0) * (sp / 320.0 if sp else 0.0)
        else:
            self.vel[:2] += wish[:2] * 10.0 * dt * 30.0   # grov luftaccel-imitation
            self.vel[2] -= 800.0 * dt
        self.jump_held = bool(jump)
        self.pos += self.vel * dt
        if self.pos[2] <= 32.0:
            self.pos[2] = 32.0
            self.vel[2] = 0.0
            self.onground = True
        for sgn in (1.0, -1.0):
            if sgn * self.pos[0] > self.X_WALL:
                self.pos[0] = sgn * self.X_WALL
                self.vel[0] = 0.0   # väggträff nollar normalkomponenten
        return self.pos.copy(), self.vel.copy(), self.onground, 0, self.jump_held

    def trace_rays(self, origins, dirs, max_dist):
        # analytiskt: golvplan z=32 och väggplan x=±X_WALL
        n = len(dirs)
        frac = np.ones(n, dtype=np.float32)
        for i in range(n):
            best = max_dist
            dz = dirs[i][2]
            if dz < -1e-6:
                t = (origins[i][2] - 32.0) / -dz
                best = min(best, t)
            dx = dirs[i][0]
            if abs(dx) > 1e-6:
                for wall in (self.X_WALL, -self.X_WALL):
                    t = (wall - origins[i][0]) / dx
                    if t > 0:
                        best = min(best, t)
            frac[i] = min(best, max_dist) / max_dist
        return frac


@dataclasses.dataclass
class EpisodeConfig:
    start_pos: tuple = (224.0, -1408.0, 32.0)
    start_yaw: float = 90.0            # +Y, mot målet
    max_ticks: int = 77 * 15           # 15 s
    end_y: float = 2900.0


class QWEnvCore:
    """En slot. Vektoriseringen sker i SF (många env-instanser) eller senare
    direkt i qwsim-batchen; kärnlogiken hålls per-slot och enkel."""

    def __init__(self, backend: Backend, curriculum: Curriculum,
                 obs_spec: S.ObsSpec | None = None, cfg: EpisodeConfig | None = None):
        self.b = backend
        self.cur = curriculum
        self.obs_spec = obs_spec or S.ObsSpec()
        self.cfg = cfg or EpisodeConfig()
        self._reset_state()

    def _reset_state(self):
        self.yaw = self.cfg.start_yaw
        self.pitch = 0.0
        self.tick = 0
        self.pos = np.array(self.cfg.start_pos, dtype=np.float64)
        self.vel = np.zeros(3)
        self.onground = True
        self.waterlevel = 0
        self.jump_held = False
        self.last_action = np.zeros(6, dtype=np.float32)
        self.peak_speed = 0.0
        self.collision_loss_total = 0.0

    def reset(self) -> np.ndarray:
        self._reset_state()
        self.b.reset(self.pos, self.vel, self.yaw)
        # entity-origins svävar över golvet (uppmätt: 100m-start z 32 -> settlad 24);
        # låt gravitationen sätta ned spelaren så episoden börjar stående
        for _ in range(20):
            self.pos, self.vel, self.onground, self.waterlevel, self.jump_held = \
                self.b.step(self.yaw, self.pitch, 0.0, 0.0, False)
            if self.onground:
                break
        return self._obs()

    def _obs(self) -> np.ndarray:
        rs = self.obs_spec.rays
        frac = self.b.trace_rays(rs.origins(self.pos.astype(np.float32), self.yaw),
                                 rs.directions(self.yaw), rs.max_dist)
        kin = self.obs_spec.kinetic(self.vel, self.yaw, self.pitch, self.onground,
                                    self.waterlevel, self.jump_held, self.last_action)
        return np.concatenate([np.asarray(frac, dtype=np.float32), kin])

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
        r = self.cur.reward_fn(st)
        sp = float(np.hypot(self.vel[0], self.vel[1]))
        self.peak_speed = max(self.peak_speed, sp)
        self.collision_loss_total += _collision_loss(st)
        self.last_action = S.flat_action(
            float(box[0]) * S.MAX_DYAW_DEG, float(box[1]) * S.MAX_DPITCH_DEG,
            fwd, side, jump)
        done = self.tick >= self.cfg.max_ticks or self.pos[1] >= self.cfg.end_y
        if done:
            self.cur.end_episode(self.peak_speed, self.collision_loss_total)
        return self._obs(), float(r), done, {"peak_speed": self.peak_speed,
                                             "stage": self.cur.stage}
