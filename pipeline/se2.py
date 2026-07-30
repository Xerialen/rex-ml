"""SE(2)-invariant transform for QuakeWorld POV tracks (BRIEF step 1).

The symmetry group is SE(2) acting on the horizontal plane: translation by
(a, b) and rotation by theta about the world z axis. A world state
(x, y, z, vx, vy, vz, yaw, pitch) maps to

    x'  = R_theta (x, y) + (a, b),   z' = z
    v'  = R_theta (vx, vy),          vz' = vz
    yaw' = yaw + theta,              pitch' = pitch

Every feature this module emits is a function of the state that is unchanged by
that action. Concretely the body frame is Quake's own horizontal view basis
(see AngleVectors / PM_AirMove, which zero the pitch component):

    e_f = ( cos yaw,  sin yaw)      "forward"
    e_r = ( sin yaw, -cos yaw)      "right"

Note this basis is left-handed (det = -1); that is Quake's convention and it is
what makes wishvel_local == (forwardmove, sidemove) exactly, with no sign fix.
The consequence is that a positive slip angle means the velocity points to the
player's right.

Absolute x, y and yaw are carried through for bookkeeping only and are *not*
features. z is kept: it is invariant under the group above.
"""

from __future__ import annotations

import numpy as np

from . import config as C


# --------------------------------------------------------------------------
# angle helpers
# --------------------------------------------------------------------------

def u16_to_rad(a: np.ndarray) -> np.ndarray:
    """QW wire angle (uint16, angle*65536/360) -> radians in [0, 2pi)."""
    return np.deg2rad(a.astype(np.float64) * C.U16_TO_DEG)


def u16_to_signed_deg(a: np.ndarray) -> np.ndarray:
    """QW wire angle -> degrees wrapped to [-180, 180). Used for pitch."""
    d = a.astype(np.float64) * C.U16_TO_DEG
    return np.where(d >= 180.0, d - 360.0, d)


def wrap_pi(a: np.ndarray) -> np.ndarray:
    """Wrap radians to (-pi, pi]."""
    return -((-a + np.pi) % (2.0 * np.pi) - np.pi)


def wrap_180(a: np.ndarray) -> np.ndarray:
    return -((-a + 180.0) % 360.0 - 180.0)


# --------------------------------------------------------------------------
# next-tick linkage
# --------------------------------------------------------------------------

def next_index(demo_key, slot, cmd_ordinal):
    """Index of the immediately following tick, and a validity mask.

    A successor is valid only when it is the same (demo_key, slot) track *and*
    cmd_ordinal advances by exactly one. Gaps (dropped commands, 1.72 % of
    replay_ticks have no usercmd at all) therefore break the chain rather than
    being silently interpolated across.
    """
    n = len(cmd_ordinal)
    nxt = np.arange(1, n + 1, dtype=np.int64)
    valid = np.zeros(n, dtype=bool)
    if n > 1:
        valid[:-1] = (
            (demo_key[1:] == demo_key[:-1])
            & (slot[1:] == slot[:-1])
            & (cmd_ordinal[1:] == cmd_ordinal[:-1] + 1)
        )
    nxt[-1] = n - 1  # clamp; masked out by valid
    nxt = np.minimum(nxt, n - 1)
    return nxt, valid


def prev_index(demo_key, slot, cmd_ordinal):
    n = len(cmd_ordinal)
    prv = np.arange(-1, n - 1, dtype=np.int64)
    valid = np.zeros(n, dtype=bool)
    if n > 1:
        valid[1:] = (
            (demo_key[1:] == demo_key[:-1])
            & (slot[1:] == slot[:-1])
            & (cmd_ordinal[1:] == cmd_ordinal[:-1] + 1)
        )
    prv = np.maximum(prv, 0)
    return prv, valid


# --------------------------------------------------------------------------
# the transform
# --------------------------------------------------------------------------

def transform(a: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """World-frame tick table -> SE(2)-reduced feature table.

    `a` is the dict produced by io_store.to_arrays, sorted by
    (demo_key, slot, cmd_ordinal). Returns a dict of equal-length arrays.
    """
    n = len(a["cmd_ordinal"])
    f = {}

    demo_key = a["demo_key"].astype(np.uint32)
    slot = a["slot"].astype(np.uint8)
    ordi = a["cmd_ordinal"].astype(np.int64)

    nxt, has_next = next_index(demo_key, slot, ordi)
    prv, has_prev = prev_index(demo_key, slot, ordi)

    dt = np.clip(a["msec"].astype(np.float64), C.THRESHOLDS.msec_min,
                 C.THRESHOLDS.msec_max) / 1000.0

    yaw = u16_to_rad(a["yaw"])
    # A null view angle means the wire never carried one for this command. Hold
    # the previous value rather than snapping the body frame to yaw = 0.
    if a.get("yaw_null") is not None and a["yaw_null"].any():
        yaw = _hold_last(yaw, ~a["yaw_null"], demo_key, slot)
    pitch_deg = u16_to_signed_deg(a["pitch"])
    if a.get("pitch_null") is not None and a["pitch_null"].any():
        pitch_deg = _hold_last(pitch_deg, ~a["pitch_null"], demo_key, slot)

    cy, sy = np.cos(yaw), np.sin(yaw)
    vx = a["vx"].astype(np.float64)
    vy = a["vy"].astype(np.float64)
    vz = a["vz"].astype(np.float64)
    x = a["x"].astype(np.float64)
    y = a["y"].astype(np.float64)
    z = a["z"].astype(np.float64)

    # ---- velocity in the body frame -------------------------------------
    v_fwd = vx * cy + vy * sy
    v_right = vx * sy - vy * cy
    speed_xy = np.hypot(vx, vy)
    slip = np.arctan2(v_right, v_fwd)          # 0 = moving where you look

    # ---- control (already expressed in the body frame by construction) ---
    fmove = a["forwardmove"].astype(np.float64)
    smove = a["sidemove"].astype(np.float64)
    umove = a["upmove"].astype(np.float64)
    wish_mag = np.hypot(fmove, smove)
    wish_psi = np.arctan2(smove, fmove)
    has_wish = wish_mag > 1e-9
    wish_f = np.where(has_wish, fmove / np.maximum(wish_mag, 1e-9), 0.0)
    wish_r = np.where(has_wish, smove / np.maximum(wish_mag, 1e-9), 0.0)
    # Angle between wish direction and velocity. This is *the* strafejump
    # variable: QW air-acceleration adds speed while |wish_slip| sits just
    # under pi/2.
    moving = speed_xy > 1e-6
    wish_slip = np.where(has_wish & moving, wrap_pi(wish_psi - slip), np.nan)

    buttons = a["buttons"].astype(np.uint8)
    attack = (buttons & C.BUTTON_ATTACK) != 0
    jump_btn = (buttons & C.BUTTON_JUMP) != 0

    # ---- mouse deltas: the invariant part of the view control ------------
    dyaw = np.where(has_next, wrap_pi(yaw[nxt] - yaw), np.nan)
    dpitch = np.where(has_next, wrap_180(pitch_deg[nxt] - pitch_deg), np.nan)
    omega = dyaw / dt                                   # rad/s, applied i -> i+1
    omega_prev = np.where(has_prev, omega[prv], np.nan)  # turn rate that produced tick i

    # ---- next-state deltas, expressed in the frame at tick i -------------
    dx_w = np.where(has_next, x[nxt] - x, np.nan)
    dy_w = np.where(has_next, y[nxt] - y, np.nan)
    dx_loc = dx_w * cy + dy_w * sy
    dy_loc = dx_w * sy - dy_w * cy
    dz = np.where(has_next, z[nxt] - z, np.nan)

    dvx_w = np.where(has_next, vx[nxt] - vx, np.nan)
    dvy_w = np.where(has_next, vy[nxt] - vy, np.nan)
    dv_fwd = dvx_w * cy + dvy_w * sy
    dv_right = dvx_w * sy - dvy_w * cy
    dvz = np.where(has_next, vz[nxt] - vz, np.nan)
    dv_xy = np.hypot(dvx_w, dvy_w)
    dspeed_xy = np.where(has_next, speed_xy[nxt] - speed_xy, np.nan)

    # Residual of the vertical dynamics against free fall. Zero on an honest
    # airborne tick; large where an external force acted (blast, jump, landing,
    # trigger_push, lift) or where ground support removed gravity.
    grav_res = dvz + C.GRAVITY * dt

    f.update(
        demo_key=demo_key, slot=slot, cmd_ordinal=ordi,
        t=a["t"].astype(np.int32), msec=a["msec"].astype(np.uint8), dt=dt,
        # bookkeeping, NOT features
        x=x, y=y, yaw=yaw,
        # invariant state
        z=z, v_fwd=v_fwd, v_right=v_right, vz=vz,
        speed_xy=speed_xy, slip=slip, omega_prev=omega_prev, pitch_deg=pitch_deg,
        wish_f=wish_f, wish_r=wish_r, wish_mag=wish_mag, wish_slip=wish_slip,
        # invariant action
        forwardmove=fmove, sidemove=smove, upmove=umove,
        dyaw=dyaw, dpitch=dpitch, omega=omega,
        attack=attack, jump_btn=jump_btn,
        # invariant transition
        dx_loc=dx_loc, dy_loc=dy_loc, dz=dz,
        dv_fwd=dv_fwd, dv_right=dv_right, dvz=dvz, dv_xy=dv_xy,
        dspeed_xy=dspeed_xy, grav_res=grav_res,
        # raw flags carried through for segmentation / ablations
        onground_flag=a["onground"].astype(bool),
        jump_held=a["jump_held"].astype(bool),
        waterlevel=a["waterlevel"].astype(np.uint8),
        wire_state_present=a["wire_state_present"].astype(bool),
        seq_break=a["seq_break"].astype(bool),
        has_next=has_next, has_prev=has_prev,
    )
    if "split" in a:
        f["split"] = a["split"]
    return f


def _hold_last(vals, ok, demo_key, slot):
    """Forward-fill `vals` where `ok` is False, restarting at each track."""
    n = len(vals)
    out = vals.copy()
    new_track = np.empty(n, dtype=bool)
    new_track[0] = True
    new_track[1:] = (demo_key[1:] != demo_key[:-1]) | (slot[1:] != slot[:-1])
    src = np.where(ok | new_track, np.arange(n), -1)
    np.maximum.accumulate(src, out=src)
    src = np.maximum(src, 0)
    return out[src]


# --------------------------------------------------------------------------
# invariance check, used by the tests and by validate_sample
# --------------------------------------------------------------------------

INVARIANT_KEYS = (
    "z", "v_fwd", "v_right", "vz", "speed_xy", "slip", "omega_prev", "pitch_deg",
    "wish_f", "wish_r", "wish_mag", "wish_slip",
    "forwardmove", "sidemove", "upmove", "dyaw", "dpitch", "omega",
    "dx_loc", "dy_loc", "dz", "dv_fwd", "dv_right", "dvz", "dv_xy",
    "dspeed_xy", "grav_res",
)


def apply_se2(a: dict[str, np.ndarray], theta: float, tx: float, ty: float) -> dict:
    """Act on a world-frame tick table with a rotation + translation.

    yaw is stored as a uint16 wire angle, so the rotated yaw is re-quantised the
    same way the wire would have -- which is why the invariance test uses a
    tolerance rather than exact equality.
    """
    b = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in a.items()}
    ct, st = np.cos(theta), np.sin(theta)
    x, y = a["x"].astype(np.float64), a["y"].astype(np.float64)
    vx, vy = a["vx"].astype(np.float64), a["vy"].astype(np.float64)
    b["x"] = (ct * x - st * y + tx).astype(a["x"].dtype)
    b["y"] = (st * x + ct * y + ty).astype(a["y"].dtype)
    b["vx"] = (ct * vx - st * vy).astype(a["vx"].dtype)
    b["vy"] = (st * vx + ct * vy).astype(a["vy"].dtype)
    dyaw_u16 = np.rad2deg(theta) / C.U16_TO_DEG
    b["yaw"] = np.mod(a["yaw"].astype(np.float64) + dyaw_u16, 65536.0).astype(np.uint16)
    return b
