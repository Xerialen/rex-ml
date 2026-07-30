"""Observations- och handlingsspec för DRL-agenten (Grundlag v3).

Ren numpy — inga gym/torch-beroenden här. SF-wrappern (rl/sf_env.py) lägger
gymnasium-spaces ovanpå. Alla konstanter är medvetet samlade här så att en
ändring av strålmönster eller skalning är EN diff.
"""
from __future__ import annotations

import dataclasses
import numpy as np

TICK_DT = 1.0 / 77.0

# Handlingsrum: Tuple(Box(2), Discrete(2), Discrete(3), Discrete(2)) i SF-termer.
#   Box[0] = dyaw  i [-1, 1] -> grader/tick
#   Box[1] = dpitch i [-1, 1] -> grader/tick
#   Discrete(2) = framåtknapp (0/1)   — fristående: QW-bunny kräver släppt W
#   Discrete(3) = sidled (0=ingen, 1=vänster, 2=höger)
#   Discrete(2) = hopp (0/1)
MAX_DYAW_DEG = 15.0    # 15°/tick @77 Hz = 1155°/s; half-beat behöver snabba teckenbyten
MAX_DPITCH_DEG = 10.0
PITCH_MIN, PITCH_MAX = -70.0, 80.0

# usercmd-magnituder vid full deflektion. Servern klipper wishspeed mot maxspeed,
# så >=320 är ekvivalent på marken; riktningen styrs av kvoten fwd/side.
# MÄTT 2026-07-30 ur korpusens usercmds (16,3 M/16,7 M nollskilda cmds):
# ±508 dominerar (40,5 % av forwardmove, 27,6/28,3 % av sidemove) — klassisk
# cl_forwardspeed/cl_sidespeed-config. Vi matchar människorna.
FORWARDMOVE = 508.0
SIDEMOVE = 508.0

SPEED_NORM = 800.0     # Gate 1-målet; hastigheter normaliseras mot denna


@dataclasses.dataclass(frozen=True)
class RaySpec:
    """Perceptionsstrålar i agentens yaw-ram (Lidar-stil, manifestets val).

    Azimuter tätare framåt (rörelseriktningen är där besluten fattas i 800 UPS),
    glesare bakåt. Elevationer täcker golvlutning, horisont och överhäng.
    Separata golvprober rakt ned-framåt ger trappor/avsatser tidigt.
    """
    front_az_deg: tuple = tuple(np.linspace(-90, 90, 17))        # 17 st, 11.25° steg
    rear_az_deg: tuple = tuple(np.linspace(101.25, 258.75, 8))   # 8 st bakåt, glest
    elevations_deg: tuple = (-30.0, 0.0, 20.0)
    floor_probe_ahead_u: tuple = (48.0, 96.0, 192.0, 384.0)      # golvhöjd framför
    max_dist: float = 2048.0

    @property
    def n_rays(self) -> int:
        n_sphere = (len(self.front_az_deg) + len(self.rear_az_deg)) * len(self.elevations_deg)
        return n_sphere + len(self.floor_probe_ahead_u) + 2  # + rakt ned + rakt upp

    def directions(self, yaw_deg: float) -> np.ndarray:
        """(n_rays, 3) enhetsvektorer i världsram för given yaw. Golvproberna
        returneras som riktningar från offsetpunkter — se origins()."""
        dirs = []
        az_all = list(self.front_az_deg) + list(self.rear_az_deg)
        for el in self.elevations_deg:
            el_r = np.radians(el)
            for az in az_all:
                a = np.radians(yaw_deg + az)
                dirs.append([np.cos(a) * np.cos(el_r), np.sin(a) * np.cos(el_r), np.sin(el_r)])
        for _ in self.floor_probe_ahead_u:
            dirs.append([0.0, 0.0, -1.0])
        dirs.append([0.0, 0.0, -1.0])
        dirs.append([0.0, 0.0, 1.0])
        return np.asarray(dirs, dtype=np.float32)

    def origins(self, pos: np.ndarray, yaw_deg: float) -> np.ndarray:
        """(n_rays, 3) startpunkter: ögonhöjd för sfärstrålar, framskjutna punkter
        för golvproberna."""
        eye = pos + np.array([0.0, 0.0, 22.0], dtype=np.float32)  # QW view height
        n_sphere = (len(self.front_az_deg) + len(self.rear_az_deg)) * len(self.elevations_deg)
        origins = np.tile(eye, (self.n_rays, 1)).astype(np.float32)
        fwd = np.array([np.cos(np.radians(yaw_deg)), np.sin(np.radians(yaw_deg)), 0.0])
        for i, ahead in enumerate(self.floor_probe_ahead_u):
            origins[n_sphere + i] = eye + fwd * ahead
        return origins


@dataclasses.dataclass(frozen=True)
class ObsSpec:
    rays: RaySpec = RaySpec()

    # kinetiska features: vel i yaw-ram (3) /SPEED_NORM, fart /SPEED_NORM,
    # sin+cos(yaw - vel_heading), pitch/90, onground, waterlevel/3, jump_held,
    # förra tickens (dyaw, dpitch, fwd, side_l, side_r, jump)
    N_KIN = 3 + 1 + 2 + 1 + 1 + 1 + 1 + 6

    @property
    def n_obs(self) -> int:
        return self.rays.n_rays + self.N_KIN

    def kinetic(self, vel: np.ndarray, yaw_deg: float, pitch_deg: float,
                onground: bool, waterlevel: int, jump_held: bool,
                last_action: np.ndarray) -> np.ndarray:
        yaw_r = np.radians(yaw_deg)
        c, s = np.cos(yaw_r), np.sin(yaw_r)
        # rotera vel in i yaw-ramen (x = framåt, y = vänster)
        vx = c * vel[0] + s * vel[1]
        vy = -s * vel[0] + c * vel[1]
        speed_h = float(np.hypot(vel[0], vel[1]))
        if speed_h > 1.0:
            dh = np.arctan2(vel[1], vel[0]) - yaw_r
            sh, ch = np.sin(dh), np.cos(dh)
        else:
            sh, ch = 0.0, 1.0
        k = np.array([
            vx / SPEED_NORM, vy / SPEED_NORM, vel[2] / SPEED_NORM,
            speed_h / SPEED_NORM, sh, ch, pitch_deg / 90.0,
            1.0 if onground else 0.0, waterlevel / 3.0,
            1.0 if jump_held else 0.0,
        ], dtype=np.float32)
        return np.concatenate([k, last_action.astype(np.float32)])


def action_to_usercmd(box: np.ndarray, fwd: int, side: int, jump: int,
                      yaw_deg: float, pitch_deg: float):
    """Mappa nätets handling -> (ny yaw, ny pitch, forwardmove, sidemove, buttons).

    Sidled: 1=vänster => sidemove < 0 i QW-konvention? OBS: QW usercmd sidemove>0
    är HÖGER. Vänster = -SIDEMOVE.
    """
    dyaw = float(np.clip(box[0], -1.0, 1.0)) * MAX_DYAW_DEG
    dpitch = float(np.clip(box[1], -1.0, 1.0)) * MAX_DPITCH_DEG
    yaw = (yaw_deg + dyaw) % 360.0
    pitch = float(np.clip(pitch_deg + dpitch, PITCH_MIN, PITCH_MAX))
    forwardmove = FORWARDMOVE if fwd == 1 else 0.0
    sidemove = 0.0
    if side == 1:
        sidemove = -SIDEMOVE
    elif side == 2:
        sidemove = SIDEMOVE
    return yaw, pitch, forwardmove, sidemove, bool(jump)


def flat_action(dyaw: float, dpitch: float, fwd: int, side: int, jump: int) -> np.ndarray:
    """Förra-handling-featuren i observationen (6 värden)."""
    return np.array([dyaw / MAX_DYAW_DEG, dpitch / MAX_DPITCH_DEG,
                     float(fwd), 1.0 if side == 1 else 0.0,
                     1.0 if side == 2 else 0.0, float(jump)], dtype=np.float32)
