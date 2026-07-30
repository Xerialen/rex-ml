"""Constants and tunable thresholds for BRIEF step 1.

Everything that is a *choice* lives here so it shows up in one diff. Everything
that is a *measurement* is reported by validate_sample.py.
"""

from dataclasses import dataclass, asdict, field
from pathlib import Path

STORE = Path("/home/benjamin-adm/dm3-extract/store-dm3")
REPLAY_TICKS = str(STORE / "replay_ticks/**/*.parquet")
USERCMDS = str(STORE / "usercmds/**/*.parquet")
MOVEVARS = str(STORE / "movevars/*.parquet")

OUT_DIR = Path("/home/benjamin-adm/rex-ml/pipeline/out")

# QuakeWorld physics. Measured over store-dm3/movevars: gravity=800 in 100 % of
# 4 567 rows; stopspeed=100; accelerate=10. airaccelerate is 10.0 (3 182 rows) or
# 0.7 (1 290 rows) -- it does not enter step 1, but the air-accel bound below is
# derived from the permissive value.
GRAVITY = 800.0             # units/s^2
JUMP_IMPULSE = 270.0        # PM_JumpButton: velocity[2] += 270
AIR_WISHSPEED_CAP = 30.0    # PM_AirAccelerate clamps wishspd to 30
AIR_ACCELERATE_MAX = 10.0   # worst case seen in movevars

BUTTON_ATTACK = 1
BUTTON_JUMP = 2

U16_TO_DEG = 360.0 / 65536.0


@dataclass(frozen=True)
class Thresholds:
    # ---- track chunking -------------------------------------------------
    msec_min: int = 1              # usercmd frametimes outside [min,max] break a chunk
    msec_max: int = 50
    # ---- ground-contact derivation --------------------------------------
    # `onground` in store-dm3 is unreliable (see AUDIT/PROGRESS): 53 % of ticks
    # flagged airborne have vz == 0 and dz == 0. Ground contact is therefore
    # derived from vertical dynamics and only OR-ed with the flag.
    vz_zero_eps: float = 1e-6      # vz is float32 and exactly 0.0 when supported
    min_air_run: int = 2           # air runs shorter than this are absorbed into ground
    min_ground_run: int = 1        # ground runs shorter than this are absorbed into air
    # ---- impulse detection (external force, not gravity/air-accel) ------
    # Physics bound on an honest airborne tick:
    #   |dvz + g*dt|  <= 0                       (gravity is the only vertical force)
    #   |dv_xy|       <= airaccel*30*dt ~= 4.2   (dt = 14 ms, airaccelerate = 10)
    # Floats, 1-tick quantisation and the replay integrator smear this, so the
    # thresholds are set well above the bound and reported empirically.
    impulse_dvz: float = 60.0      # units/s of unexplained vertical velocity in one tick
    impulse_dvxy: float = 40.0     # units/s of unexplained horizontal velocity in one tick
    # ---- maneuver classification ---------------------------------------
    # Attribution thresholds are set from analyze_rocket.py, which scores each
    # candidate rule against a null that rolls the fire train forward 499 ticks
    # inside each track (same fire rate and burst structure, no causal link).
    # Measured on 25 demos / 245 min:
    #   fire<=12 alone .................. 1.41x lift   0.56 events/min
    #   fire<=3 + upward blast .......... 2.16x        0.28/min
    #   fire<=3 + upward + pitch>10 ..... 2.70x        0.25/min
    #   fire<=3 + upward + pitch>20 ..... 5.33x        0.20/min   <- used
    # 5.33x implies roughly 81 % precision. Recall is deliberately traded away:
    # a mislabelled rocket jump poisons the DMP regression in BRIEF step 2,
    # a missed one only costs a demonstration.
    fire_window_before: int = 3    # ticks: attack edge this long before an impulse still counts
    fire_window_after: int = 1     # ticks after
    rocket_impulse_min: float = 120.0   # |dv| of a blast, well above a 270 jump's vertical-only signature
    rocket_up_min: float = 0.5     # blast must point up: grav_res / |dv| in the body frame
    rocket_pitch_min: float = 20.0  # deg, + is down in Quake -- you look at the floor to rocket jump
    jump_dvz_lo: float = 200.0     # a plain jump is dvz ~ +270 with no fire nearby
    jump_dvz_hi: float = 340.0
    maneuver_pad: int = 2          # ticks of context kept either side of a maneuver anchor
    # ---- trim extraction -------------------------------------------------
    # A trim is a relative equilibrium of the SE(2)-reduced dynamics: the *shape*
    # variables (slip angle phi, turn rate omega) are near-constant. Speed is
    # allowed to drift -- a strafejump gains speed while holding its shape.
    trim_min_len: int = 8               # ticks (~0.1 s at 77 Hz)
    trim_phi_tol: float = 0.20          # rad, max deviation of slip angle from window mean
    trim_omega_tol: float = 3.0         # rad/s, max deviation of turn rate from window mean
    trim_speed_rel_tol: float = 0.35    # max |speed/speed_0 - 1| across the window
    trim_min_speed: float = 40.0        # below this the frame is ill-conditioned; call it idle


THRESHOLDS = Thresholds()


def thresholds_dict() -> dict:
    return asdict(THRESHOLDS)
