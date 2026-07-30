"""An analytic strafe-jumper: what the environment's physics actually allows, and a teacher.

Two jobs. First it establishes the ceiling — a policy that comes in under a hand-written controller
on a straight corridor is short of the physics, not short of the map. Second it is a supervisor that
can answer *any* state, unlike the corpus expert, which could only answer states humans happened to
visit and answered `forwardmove = 0` in 99.4 % of slow ones.

The arithmetic it is built on, from `rtx_nav::strafe::apply_airaccel`. Airborne, `addspeed` is
capped at `AIR_CAP = 30`, so a tick adds at most `A = 30 - v·ŵ` along the wish direction and

    |v'|² = v² + 2A(v·ŵ) + A² = v² + 900 - (v·ŵ)²

which is maximised at `v·ŵ = 0`: **the wish direction exactly perpendicular to the velocity, adding
exactly 900 to v² per airborne tick, whatever the speed.** With `forwardmove = 0` and one strafe key
held, the wish direction is the view's right vector, so "perpendicular to velocity" means aiming the
view straight along the velocity — and re-aiming it every tick as the velocity turns.

That gain being fixed per tick has a consequence worth stating plainly: peak speed on a corridor is
decided by the *number of airborne ticks*, hence by the tick rate and by how fast the run leaves the
ground. Chasing it with a better policy alone cannot beat the arithmetic.

The one place more speed is available is the ground. `apply_groundaccel` limits only the component
*along* the wish direction to `sv_maxspeed`; velocity perpendicular to it is untouched. Circling on
the ground therefore leaves the 320 cap behind — measured here at 483 u/s — and that launch speed
carries straight into the air phase.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

MAP = "/home/benjamin-adm/rex-ml/rtx/playground/qw/maps/100m.bsp"
START = (224.0, -1408.0, 32.0)
END = (224.0, 2900.0, 32.0)
AXIS_DEG = 90.0            # the corridor runs along +Y
PEAK_GATE = 790.0

# Circling turn rate, in degrees per tick. Measured 2026-07-29: 4 deg/tick peaks the ground phase at
# 483 u/s, against 320 for running straight. Slower under-turns and gains less; faster out-runs the
# acceleration and falls back toward 330.
SPIN_OMEGA_DEG = 4.0
# Leave the circle only once the ground phase has banked what it can. At 420 the controller left
# a full lap early and launched at 421 u/s for a 799 peak; holding out to 450 banks 485 and reaches
# 821. Anything above 450 behaves identically — the circle simply cannot give more than 485.
LAUNCH_SPEED = 450.0
LAUNCH_HEADING_TOL = 14.0  # ...and only while pointed down the corridor
HEADING_BAND_DEG = 2.0     # strafe side flips at the edge of this band around the aim
CROSS_GAIN = 0.06          # how hard the aim leans back toward the centreline, deg per unit
CROSS_CAP = 25.0


def _wrap(a: np.ndarray) -> np.ndarray:
    return ((a + 180.0) % 360.0) - 180.0


def act(origin: np.ndarray, vel: np.ndarray, on_ground: np.ndarray, view_yaw: np.ndarray,
        side: np.ndarray, launched: np.ndarray, axis_x: float = START[0],
        axis_deg: float = AXIS_DEG) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One tick of control for `n` runners. Returns `(actions, side, launched)`.

    `side` and `launched` are the controller's own state and must be fed back in each tick.
    """
    n = len(origin)
    sp = np.linalg.norm(vel[:, :2], axis=1)
    hdg = np.degrees(np.arctan2(vel[:, 1], vel[:, 0]))
    cross = origin[:, 0] - axis_x
    # A heading of 90 deg runs along +Y; to shed a positive cross-track the heading must go ABOVE
    # 90, since only then does cos(heading) turn negative and x come back. Leaning the aim the other
    # way looks like a correction and is an accelerant — it held 65 deg all the way to 528 u out.
    aim = axis_deg + np.clip(CROSS_GAIN * cross, -CROSS_CAP, CROSS_CAP)

    # The circle ends the first tick the run is both fast enough and pointed down the corridor.
    launched = launched | ((sp >= LAUNCH_SPEED)
                           & (np.abs(_wrap(hdg - axis_deg)) < LAUNCH_HEADING_TOL))

    err = _wrap(hdg - aim)
    # `side = +1` pushes along Quake's right vector (sin, -cos), which rotates the heading
    # *clockwise*. A heading that has fallen below the aim is therefore raised with -1, not +1 —
    # getting this backwards makes the controller drive itself out of the corridor while still
    # gaining speed, which reads as a plausible run right up until it never arrives.
    side = np.where(err > HEADING_BAND_DEG, 1.0,
                    np.where(err < -HEADING_BAND_DEG, -1.0, side)).astype(np.float32)

    a = np.zeros((n, 4), np.float32)
    spin = ~launched
    # Circling: hold one strafe key and turn at a constant rate, feet on the ground.
    a[spin, 1] = 1.0
    a[spin, 2] = np.radians(SPIN_OMEGA_DEG)
    # Running: view along the velocity so the strafe axis is perpendicular to it, and jump on every
    # ground contact — `pm_step` needs the button released between jumps, so it is pressed only when
    # grounded.
    run = launched
    a[run, 1] = side[run]
    a[run, 2] = np.radians(_wrap(hdg - view_yaw))[run]
    a[run, 3] = (on_ground[run] > 0.5).astype(np.float32)
    return a, side, launched


def run(n: int = 8, max_ticks: int = 1600, tick_dt: float = 1.0 / 77.0) -> dict:
    import rex_env

    env = rex_env.PyVecEnv.from_path(MAP, [START, END], n, 24.0, max_ticks)
    env.reset()
    side = -np.ones(n, np.float32)
    launched = np.zeros(n, bool)
    peak = np.zeros(n, np.float32)
    launch_speed = np.zeros(n, np.float32)
    done = np.zeros(n, bool)
    arrived = np.zeros(n, bool)
    ticks = np.zeros(n, np.int64)
    air = np.zeros(n, np.int64)
    cross = np.zeros(n, np.float32)

    for _ in range(max_ticks + 2):
        o, v, g, y = env.origins, env.velocities, env.on_ground, env.view_yaws
        sp = np.linalg.norm(v[:, :2], axis=1)
        live = ~done
        peak = np.where(live, np.maximum(peak, sp), peak)
        cross = np.where(live, np.maximum(cross, np.abs(o[:, 0] - START[0])), cross)
        was = launched.copy()
        a, side, launched = act(o, v, g, y, side, launched)
        launch_speed = np.where(launched & ~was, sp, launch_speed)
        air += (live & (g < 0.5)).astype(np.int64)
        ticks += live.astype(np.int64)
        _, parts, dn = env.step(a)
        parts = np.asarray(parts)
        for i in np.flatnonzero(live & np.asarray(dn)):
            done[i] = True
            arrived[i] = parts[i, 4] > 0
        if done.all():
            break

    return {
        "n": n, "tick_dt": tick_dt,
        "peak_max": round(float(peak.max()), 1),
        "peak_median": round(float(np.median(peak)), 1),
        "launch_speed_median": round(float(np.median(launch_speed)), 1),
        "arrival_rate": round(float(arrived.mean()), 3),
        "median_time_s": round(float(np.median(ticks[arrived]) * tick_dt), 2) if arrived.any() else None,
        "frac_airborne": round(float(air.sum() / max(ticks.sum(), 1)), 3),
        "max_cross_track_u": round(float(cross.max()), 1),
        "passes_peak_gate": bool(peak.max() >= PEAK_GATE),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    a = ap.parse_args()
    r = run(a.n)
    print(f"analytisk strafe-jumper: topp {r['peak_max']:.1f} u/s "
          f"(avstamp {r['launch_speed_median']:.0f}), ankomst {r['arrival_rate'] * 100:.0f} %, "
          f"tid {r['median_time_s']} s, luft {r['frac_airborne'] * 100:.1f} %, "
          f"drift {r['max_cross_track_u']:.1f} u")
    print(f"grind {PEAK_GATE:.0f} u/s: {'KLARAR' if r['passes_peak_gate'] else 'KLARAR INTE'}")
    out = Path("/home/benjamin-adm/rex-ml/evidence/strafe_ceiling_100m.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, indent=1))
    print(f"skrev {out}")


if __name__ == "__main__":
    main()


# --- following a planned path, not a fixed axis ------------------------------------------------
#
# The corridor controller aims at a constant heading. A dm3 route is a polyline, so the only change
# needed is where the aim comes from: a lookahead point on the path instead of `AXIS_DEG`, and
# cross-track measured against the path instead of against one axis. Everything that makes the speed
# — circle first, then view along velocity with one strafe key and a jump on every ground contact —
# is untouched, because that part is physics and does not care what shape the route is.

LOOKAHEAD_U = 260.0        # roughly a jump's worth of travel; shorter oscillates, longer cuts corners


def _project(path: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Nearest point on the polyline and the point `LOOKAHEAD_U` further along it, per runner."""
    seg_a, seg_b = path[:-1], path[1:]
    d = seg_b - seg_a
    denom = np.maximum((d * d).sum(1), 1e-6)
    t = np.clip(((p[:, None, :] - seg_a[None]) * d[None]).sum(2) / denom[None], 0.0, 1.0)
    proj = seg_a[None] + t[..., None] * d[None]
    k = np.linalg.norm(proj - p[:, None, :], axis=2).argmin(1)
    n = np.arange(len(p))
    seg_len = np.linalg.norm(d, axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg_len)])
    here = cum[k] + t[n, k] * seg_len[k]
    ahead = np.minimum(here + LOOKAHEAD_U, cum[-1])
    # Walk the arclength back to a point.
    j = np.clip(np.searchsorted(cum, ahead, side="right") - 1, 0, len(seg_len) - 1)
    frac = np.clip((ahead - cum[j]) / np.maximum(seg_len[j], 1e-6), 0.0, 1.0)
    look = seg_a[j] + frac[:, None] * d[j]
    return proj[n, k], look


def act_path(origin: np.ndarray, vel: np.ndarray, on_ground: np.ndarray, view_yaw: np.ndarray,
             side: np.ndarray, launched: np.ndarray, path: np.ndarray
             ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One tick of control along a planned path. Same contract as :func:`act`."""
    n = len(origin)
    sp = np.linalg.norm(vel[:, :2], axis=1)
    hdg = np.degrees(np.arctan2(vel[:, 1], vel[:, 0]))
    on_path, look = _project(path, origin)

    to_look = look[:, :2] - origin[:, :2]
    aim = np.degrees(np.arctan2(to_look[:, 1], to_look[:, 0]))
    # Signed cross-track: positive means the runner sits to the left of the path's own direction, so
    # the correction has the same handedness as the corridor version.
    off = origin[:, :2] - on_path[:, :2]
    ax = np.stack([np.cos(np.radians(aim)), np.sin(np.radians(aim))], 1)
    cross = off[:, 0] * (-ax[:, 1]) + off[:, 1] * ax[:, 0]
    aim = aim - np.clip(CROSS_GAIN * cross, -CROSS_CAP, CROSS_CAP)

    launched = launched | ((sp >= LAUNCH_SPEED) & (np.abs(_wrap(hdg - aim)) < LAUNCH_HEADING_TOL))
    err = _wrap(hdg - aim)
    side = np.where(err > HEADING_BAND_DEG, 1.0,
                    np.where(err < -HEADING_BAND_DEG, -1.0, side)).astype(np.float32)

    a = np.zeros((n, 4), np.float32)
    spin = ~launched
    a[spin, 1] = 1.0
    a[spin, 2] = np.radians(SPIN_OMEGA_DEG)
    run = launched
    a[run, 1] = side[run]
    a[run, 2] = np.radians(_wrap(hdg - view_yaw))[run]
    a[run, 3] = (on_ground[run] > 0.5).astype(np.float32)
    return a, side, launched
