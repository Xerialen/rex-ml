"""Vectorised QuakeWorld player movement, no collision.

A faithful transcription of QW `pmove.c` PlayerMove order:

    PM_JumpButton  ->  PM_Friction  ->  PM_AirMove  (Accelerate | AirAccelerate)

with `PM_GroundMove`/`PM_FlyMove` reduced to `origin += velocity*frametime`,
i.e. no trace against world geometry. That restriction is deliberate and its
cost is measured, not assumed: `validate()` scores the model against the recorded
(state, usercmd, next state) triples from step 1, split by whether the tick
could have touched anything.

The point of having this in Python is rollout evaluation. Held-out action error
answers "does the policy pick the human's button"; only a rollout answers "does
the resulting path go where the human's path went", which is the quantity BRIEF
step 4's Tracking Guard is defined on.

Constants agree with rtx-nav/src/qphys.rs (AIR_CAP 30, JUMP_VZ 270).
"""

from __future__ import annotations

import numpy as np

from . import config as C

AIR_CAP = 30.0          # PM_AirAccelerate wishspd clamp
JUMP_VZ = 270.0         # PM_JumpButton
DEFAULT = dict(gravity=800.0, stopspeed=100.0, maxspeed=320.0,
               accelerate=10.0, friction=4.0, entgravity=1.0)


def angle_vectors_xy(yaw: np.ndarray):
    """Quake's horizontal forward/right basis in WORLD coordinates.

    `PM_AirMove` sets forward[2] = right[2] = 0 and renormalises, so for the
    horizontal move this is exact -- view pitch has no effect on wishvel.
    """
    cy, sy = np.cos(yaw), np.sin(yaw)
    return np.stack([cy, sy], -1), np.stack([sy, -cy], -1)


def body_basis(dyaw: np.ndarray):
    """The view basis after turning by `dyaw`, expressed in the body frame of the
    tick *before* the turn.

    This is not `angle_vectors_xy(dyaw)` and it is not `angle_vectors_xy(-dyaw)`
    either. Quake's (forward, right) pair is **left-handed** (det = -1), so a
    world rotation does not act on body coordinates as the same rotation.
    Working it out from e_f(t) = (cos t, sin t), e_r(t) = (sin t, -cos t):

        e_f(t+d) . e_f(t) =  cos d      e_f(t+d) . e_r(t) = -sin d
        e_r(t+d) . e_f(t) =  sin d      e_r(t+d) . e_r(t) =  cos d

    Getting this wrong is silent: it leaves the velocity magnitudes right and
    only bends the direction, which reads as a plausible few-u/s residual rather
    than an error. It cost ~30 u/s of median ground error before it was caught.
    """
    c, s = np.cos(dyaw), np.sin(dyaw)
    return np.stack([c, -s], -1), np.stack([s, c], -1)


def step(vx, vy, vz, yaw, fmove, smove, jump, old_jump, onground, dt,
         mv=None, air_accel=None, waterlevel=None, basis=None):
    """One PlayerMove tick. Returns (vx, vy, vz, onground_out, old_jump_out).

    Arrays broadcast; every argument may be a scalar or an (N,) array.
    `air_accel` overrides the air-branch acceleration constant. Left as a
    parameter because QW forks disagree about whether PM_AirMove passes
    `accelerate` or `airaccelerate`; fitting it against 1.6 M recorded airborne
    transitions selects **10.0**, i.e. `movevars.accelerate`, which is what
    vanilla QW pmove.c does. Default None therefore reproduces vanilla.
    """
    mv = {**DEFAULT, **(mv or {})}
    vx, vy, vz = map(np.asarray, (vx, vy, vz))
    dt = np.asarray(dt, dtype=np.float64)
    onground = np.asarray(onground, dtype=bool)
    jump = np.asarray(jump, dtype=bool)
    old_jump = np.asarray(old_jump, dtype=bool)
    vx, vy, vz = vx.astype(np.float64), vy.astype(np.float64), vz.astype(np.float64)

    # ---- PM_JumpButton ------------------------------------------------
    # "don't pogo stick": the button must have been released since the last jump
    do_jump = jump & ~old_jump & onground
    vz = np.where(do_jump, vz + JUMP_VZ, vz)
    og = onground & ~do_jump
    old_jump_out = np.where(jump, True, False)

    # ---- PM_Friction ---------------------------------------------------
    # 3D speed, and ground friction only while supported. Applied *after* the
    # jump impulse, which is the ordering in PlayerMove.
    speed = np.sqrt(vx * vx + vy * vy + vz * vz)
    moving = speed >= 1.0
    control = np.maximum(speed, mv["stopspeed"])
    drop = np.where(og, control * mv["friction"] * dt, 0.0)
    newspeed = np.maximum(speed - drop, 0.0)
    scale = np.where(moving, newspeed / np.maximum(speed, 1e-9), 0.0)
    # speed < 1 zeroes the horizontal components only
    vx = np.where(moving, vx * scale, 0.0)
    vy = np.where(moving, vy * scale, 0.0)
    vz = np.where(moving, vz * scale, vz)

    # ---- PM_AirMove ----------------------------------------------------
    fwd, rgt = basis if basis is not None else angle_vectors_xy(
        np.asarray(yaw, dtype=np.float64))
    wx = fwd[..., 0] * fmove + rgt[..., 0] * smove
    wy = fwd[..., 1] * fmove + rgt[..., 1] * smove
    wishspeed = np.hypot(wx, wy)
    has = wishspeed > 1e-9
    dirx = np.where(has, wx / np.maximum(wishspeed, 1e-9), 0.0)
    diry = np.where(has, wy / np.maximum(wishspeed, 1e-9), 0.0)
    wishspeed = np.minimum(wishspeed, mv["maxspeed"])

    cur = vx * dirx + vy * diry
    accel_g = mv["accelerate"]
    accel_a = mv["accelerate"] if air_accel is None else air_accel

    # ground branch: velocity[2] zeroed before accelerating
    vz_g = np.zeros_like(vz)
    add_g = wishspeed - cur
    acc_g = np.minimum(accel_g * dt * wishspeed, np.maximum(add_g, 0.0))
    acc_g = np.where(add_g > 0, acc_g, 0.0)

    # air branch: addspeed uses the capped wish, accelspeed uses the full one --
    # this asymmetry is exactly what makes strafejumping gain speed
    wishspd = np.minimum(wishspeed, AIR_CAP)
    add_a = wishspd - cur
    acc_a = np.minimum(accel_a * wishspeed * dt, np.maximum(add_a, 0.0))
    acc_a = np.where(add_a > 0, acc_a, 0.0)

    acc = np.where(og, acc_g, acc_a)
    vx = vx + acc * dirx
    vy = vy + acc * diry
    vz = np.where(og, vz_g, vz) - mv["entgravity"] * mv["gravity"] * dt

    return vx, vy, vz, og, old_jump_out


def rollout(v0, yaw_seq, fmove, smove, jump, onground0, dt, p0=None,
            mv=None, air_accel=None, freeze_ground=True):
    """Integrate a control sequence open-loop. Shapes: (N,) states, (N, T) controls.

    Returns positions (N, T+1, 3) and velocities (N, T+1, 3).

    With no collision model the sim cannot discover ground contact, so
    `freeze_ground` keeps the caller-supplied onground per tick when given as an
    (N, T) array; pass a scalar to let the jump logic drive it.
    """
    N, T = fmove.shape
    vx, vy, vz = (np.asarray(v0[..., i], np.float64).copy() for i in range(3))
    px, py, pz = ((np.zeros(N) if p0 is None else np.asarray(p0[..., i], np.float64).copy())
                  for i in range(3))
    og = (np.asarray(onground0, bool) if np.ndim(onground0) < 2
          else np.asarray(onground0[:, 0], bool))
    oj = np.zeros(N, bool)
    P = np.empty((N, T + 1, 3))
    V = np.empty((N, T + 1, 3))
    P[:, 0] = np.stack([px, py, pz], -1)
    V[:, 0] = np.stack([vx, vy, vz], -1)
    for t in range(T):
        if freeze_ground and np.ndim(onground0) == 2:
            og = np.asarray(onground0[:, t], bool)
        d = dt[:, t] if np.ndim(dt) == 2 else dt
        vx, vy, vz, og, oj = step(vx, vy, vz, yaw_seq[:, t], fmove[:, t], smove[:, t],
                                  jump[:, t], oj, og, d, mv=mv, air_accel=air_accel)
        px = px + vx * d
        py = py + vy * d
        pz = pz + vz * d
        P[:, t + 1] = np.stack([px, py, pz], -1)
        V[:, t + 1] = np.stack([vx, vy, vz], -1)
    return P, V


# --------------------------------------------------------------------------
# fitting and validation against the corpus
# --------------------------------------------------------------------------

def fit_air_accel(vx, vy, yaw, fmove, smove, dt, dvx, dvy, grid=None, basis=None):
    """Least-squares pick of the air-branch acceleration constant.

    QW forks disagree about whether PM_AirMove passes `accelerate` or
    `airaccelerate`; movevars in this corpus carries both (10.0 and 0.7/10.0).
    Rather than guess, score a grid against the recorded horizontal velocity
    change on airborne ticks.
    """
    grid = grid if grid is not None else np.concatenate(
        [np.arange(0.5, 3.0, 0.1), np.arange(3.0, 22.0, 0.5)])
    fwd, rgt = basis if basis is not None else angle_vectors_xy(yaw)
    wx = fwd[..., 0] * fmove + rgt[..., 0] * smove
    wy = fwd[..., 1] * fmove + rgt[..., 1] * smove
    ws = np.hypot(wx, wy)
    has = ws > 1e-9
    dirx = np.where(has, wx / np.maximum(ws, 1e-9), 0.0)
    diry = np.where(has, wy / np.maximum(ws, 1e-9), 0.0)
    ws_c = np.minimum(ws, DEFAULT["maxspeed"])
    cur = vx * dirx + vy * diry
    add = np.minimum(ws_c, AIR_CAP) - cur
    best = (None, np.inf)
    for a in grid:
        acc = np.minimum(a * ws_c * dt, np.maximum(add, 0.0))
        acc = np.where(add > 0, acc, 0.0)
        err = np.hypot(dvx - acc * dirx, dvy - acc * diry)
        m = float(np.median(err))
        if m < best[1]:
            best = (float(a), m)
    return best


def load_transitions(tag: str = "step1", limit_batches: int = 3, where: str = ""):
    """Recorded (state_i, usercmd_{i+1}) -> state_{i+1} triples, in the body frame of i.

    Two alignment facts from step 1 are baked in here:

      * `replay_ticks[i]` is the **pre-move** state and `usercmd[i]` drives the
        transition i -> i+1. Step 1 originally recorded the opposite reading;
        the jump-apex measurement (dvz = 270 - g*dt) is consistent with both, so
        it could not settle it. Predicting velocity settles it outright:
        cmd i gives an exact median and 65.2 % of air ticks within 1 u/s,
        cmd i+1 gives 63.2 % and a worse tail. The step 1 feature table pairs
        state i with action i, so its (s, a) tuples were already correct.
      * consequently the move uses the view angles of tick **i**, so in the body
        frame of tick i the wish basis is the identity, not a rotation by dyaw.
    """
    import duckdb
    con = duckdb.connect()
    con.execute("SET threads TO 16")
    files = f"{C.OUT_DIR}/{tag}_ticks/part-*.parquet"
    extra = f"AND {where}" if where else ""
    q = f"""
      SELECT v_fwd, v_right, vz, dyaw, msec, ground_state, waterlevel, is_impulse,
             dv_fwd, dv_right, dvz, speed_xy,
             lead(forwardmove) OVER w AS f1,
             lead(sidemove)    OVER w AS s1,
             lead(jump_btn)    OVER w AS j1,
             lead(ground_state) OVER w AS g1,
             forwardmove AS f0, sidemove AS s0, jump_btn AS j0
      FROM read_parquet('{files}')
      WHERE batch < {limit_batches} {extra}
      WINDOW w AS (PARTITION BY demo_key, slot ORDER BY cmd_ordinal)
      QUALIFY has_next
    """
    t = con.execute(q).arrow()
    if not hasattr(t, "column_names"):
        t = t.read_all()
    return {n: np.asarray(t.column(n).combine_chunks().to_numpy(zero_copy_only=False))
            for n in t.column_names}


def predict(g, air_accel=None, mv=None):
    """Predicted next-tick velocity in the body frame of tick i."""
    dt = np.clip(g["msec"].astype(np.float64), 1, 50) / 1000.0
    og = g["ground_state"] == 0
    n = len(g["v_fwd"])
    ident = (np.tile([1.0, 0.0], (n, 1)), np.tile([0.0, 1.0], (n, 1)))
    vx, vy, vz, og_out, _ = step(
        g["v_fwd"], g["v_right"], g["vz"], None,
        g["f0"].astype(np.float64), g["s0"].astype(np.float64),
        g["j0"].astype(bool), np.zeros(n, bool), og, dt,
        mv=mv, air_accel=air_accel, basis=ident)
    # Ground contact clips vertical velocity: PM_GroundMove traces into the floor
    # and PM_CategorizePosition re-zeroes vz. Without world geometry the sim
    # cannot discover that, so where the recorded next state is still supported
    # the clip is applied from the known contact state rather than guessed.
    still_ground = g["g1"] == 0
    vz = np.where(still_ground, 0.0, vz)
    return vx, vy, vz


def validate(tag: str = "step1", limit_batches: int = 3, air_accel: float | None = None):
    """Score the sim against recorded transitions. Returns a dict of measurements."""
    g = load_transitions(tag, limit_batches)
    dt = np.clip(g["msec"].astype(np.float64), 1, 50) / 1000.0
    og = g["ground_state"] == 0
    water = g["waterlevel"] > 0
    clean_air = (~og) & (~water) & (~g["is_impulse"].astype(bool))

    if air_accel is None:
        na = int(clean_air.sum())
        ident = (np.tile([1.0, 0.0], (na, 1)), np.tile([0.0, 1.0], (na, 1)))
        air_accel, _ = fit_air_accel(
            g["v_fwd"][clean_air], g["v_right"][clean_air], None,
            g["f0"][clean_air].astype(np.float64), g["s0"][clean_air].astype(np.float64),
            dt[clean_air], g["dv_fwd"][clean_air], g["dv_right"][clean_air], basis=ident)

    vx, vy, vz = predict(g, air_accel=air_accel)
    ex = vx - (g["v_fwd"] + g["dv_fwd"])
    ey = vy - (g["v_right"] + g["dv_right"])
    ez = vz - (g["vz"] + g["dvz"])
    exy = np.hypot(ex, ey)

    out = dict(air_accel=float(air_accel), n=int(len(g["v_fwd"])))
    for name, m in (("air, no impulse", clean_air),
                    ("air, with impulse", (~og) & (~water) & g["is_impulse"].astype(bool)),
                    ("ground", og & ~water),
                    ("water", water)):
        if not m.any():
            continue
        out[name] = dict(
            n=int(m.sum()),
            xy_p50=round(float(np.percentile(exy[m], 50)), 3),
            xy_p90=round(float(np.percentile(exy[m], 90)), 3),
            xy_p99=round(float(np.percentile(exy[m], 99)), 3),
            z_p50=round(float(np.percentile(np.abs(ez[m]), 50)), 3),
            z_p90=round(float(np.percentile(np.abs(ez[m]), 90)), 3),
            frac_under_1=round(float((exy[m] < 1.0).mean()), 4),
            frac_under_4=round(float((exy[m] < 4.0).mean()), 4),
        )
    return out


if __name__ == "__main__":
    import json
    r = validate()
    print(json.dumps(r, indent=2, default=float))
