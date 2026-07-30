#!/usr/bin/env python3
"""True strafe ceiling on 100m.bsp measured in the bit-exact mvdsv pmove (libqwsim).

Why this exists: the old ceiling (821.4 u/s, evidence/strafe_ceiling_100m.json) was
measured in the rex_env sim at dt = 1/77 s. The server integrates whole milliseconds
(msec=13 => dt = 0.013 s), and Gate 1 was tightened to peak >= 820 u/s, so the ceiling
must be re-established in the byte-identical physics.

Physics facts read directly from sim/csrc/pmove.c (mvdsv):
  - PM_AirAccelerate: accelspeed = accel * wishspeed * frametime with UNCAPPED
    wishspeed (10 * 320 * 0.013 = 41.6), addspeed capped at 30 - v.w. Since 41.6 > 30
    the cap always binds: optimal wishdir is exactly perpendicular to velocity
    (v.w = 0) and each airborne tick adds exactly 900 to v^2, independent of dt.
    (theta_opt = 90 deg here; the acos((30-a*30*dt)/|v|) form applies only in the
    accelspeed-limited regime, which never occurs with these movevars.)
  - PM_PlayerMove order: CategorizePosition -> CheckJump -> Friction -> AirMove.
    Pressing jump on the tick after landing clears onground BEFORE friction, so a
    perfectly timed bunnyhop suffers zero friction: every run-phase tick is an
    air-accel tick and the ceiling is set by ticks available over the corridor length.

Controller ported from pipeline/strafe_expert.py (steering logic only): ground circle
to bank launch speed, then view locked along velocity with one strafe key, side
flipping in a heading band around the corridor axis, jump on every observed ground
contact.

Output: evidence/strafe_ceiling_qwsim.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml/sim")
import qwsim  # noqa: E402

MAP = "/home/benjamin-adm/mlx/qwserver/serverdir/id1/maps/100m.bsp"
START = np.array([224.0, -1408.0, 32.0], np.float32)
GOAL_Y = 2900.0
AXIS_DEG = 90.0  # corridor runs along +Y
GATE = 820.0
OLD_PEAK = 821.4
MAX_TICKS = 1200  # ~15.6 s at 13 ms

# steering constants ported from strafe_expert.py
HEADING_BAND = 2.0
CROSS_GAIN = 0.06
CROSS_CAP = 25.0
LAUNCH_TOL = 14.0
CURVE_MS = [2000, 4000, 6000, 8000]

EVIDENCE = Path("/home/benjamin-adm/rex-ml/evidence/strafe_ceiling_qwsim.json")


def wrap(a):
    return ((a + 180.0) % 360.0) - 180.0


def msec_stream(mode: str, t: int) -> int:
    """Per-tick msec. 'p13'=pure 13 ms; 'p12'=pure 12 ms; 'mix'=client 77 fps
    pattern (76 ticks of 13 + one of 12 = exactly 1000 ms per 77 cmds)."""
    if mode == "p13":
        return 13
    if mode == "p12":
        return 12
    return 12 if (t % 77) == 76 else 13


def simulate(spin_side, omega, launch_speed, yaw0, msec_mode, band=HEADING_BAND):
    """Run n slots (all arrays same length) and return per-slot stats."""
    n = len(yaw0)
    qwsim.alloc_slots(n)
    ids = np.arange(n, dtype=np.int32)
    pos = np.tile(START, (n, 1)).astype(np.float32)
    vel = np.zeros((n, 3), np.float32)
    ang = np.zeros((n, 3), np.float32)
    ang[:, 1] = yaw0
    qwsim.reset(ids, pos, vel, ang)

    z16 = np.zeros(n, np.int16)
    z8 = np.zeros(n, np.uint8)
    ms13 = np.full(n, 13, np.uint8)

    # settle to the floor
    for _ in range(40):
        p, v, og, wl, jh, bl = qwsim.step_batch(ids, ang, z16, z16, z16, z8, ms13)
        if og.all():
            break
    floor_z = float(p[:, 2].mean())

    view_yaw = np.asarray(yaw0, np.float32).copy()
    side = -np.ones(n, np.float32)
    launched = np.zeros(n, bool)
    og_obs = og.astype(bool)

    peak = np.zeros(n, np.float32)
    peak_y = np.full(n, np.nan, np.float32)
    arrived = np.zeros(n, bool)
    t_ms = np.zeros(n, np.int64)
    arrive_ms = np.full(n, -1, np.int64)
    arrive_speed = np.full(n, np.nan, np.float32)
    gate_tick = np.full(n, -1, np.int64)
    gate_ms = np.full(n, -1, np.int64)
    over_gate = np.zeros(n, np.int64)
    launch_sp = np.full(n, np.nan, np.float32)
    launch_y = np.full(n, np.nan, np.float32)
    launch_ms = np.full(n, -1, np.int64)
    max_cross = np.zeros(n, np.float32)
    blocked_run = np.zeros(n, np.int64)
    curve = np.full((n, len(CURVE_MS)), np.nan, np.float32)

    for t in range(MAX_TICKS):
        live = ~arrived
        if not live.any():
            break
        sp = np.linalg.norm(v[:, :2], axis=1)
        hdg = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
        cross = p[:, 0] - START[0]
        aim = AXIS_DEG + np.clip(CROSS_GAIN * cross, -CROSS_CAP, CROSS_CAP)

        newly = live & ~launched & (sp >= launch_speed) \
            & (np.abs(wrap(hdg - AXIS_DEG)) < LAUNCH_TOL)
        launched |= newly
        launch_sp = np.where(newly, sp, launch_sp)
        launch_y = np.where(newly, p[:, 1], launch_y)
        launch_ms = np.where(newly, t_ms, launch_ms)

        err = wrap(hdg - aim)
        side = np.where(err > band, 1.0,
                        np.where(err < -band, -1.0, side)).astype(np.float32)

        smove = np.where(launched, side * 700, spin_side * 700).astype(np.int16)
        view_yaw = np.where(launched, hdg, view_yaw + omega).astype(np.float32)
        ang[:, 1] = view_yaw
        buttons = np.where(launched & og_obs, 2, 0).astype(np.uint8)
        ms = np.array([msec_stream(m, t) for m in msec_mode], np.uint8)

        p, v, og, wl, jh, bl = qwsim.step_batch(ids, ang, z16, smove, z16, buttons, ms)
        og_obs = og.astype(bool)
        t_ms = np.where(live, t_ms + ms, t_ms)

        sp = np.linalg.norm(v[:, :2], axis=1).astype(np.float32)
        better = live & (sp > peak)
        peak = np.where(better, sp, peak)
        peak_y = np.where(better, p[:, 1], peak_y)
        hit = live & (sp >= GATE)
        first = hit & (gate_tick < 0)
        gate_tick = np.where(first, t + 1, gate_tick)
        gate_ms = np.where(first, t_ms, gate_ms)
        over_gate += hit
        max_cross = np.where(live, np.maximum(max_cross, np.abs(p[:, 0] - START[0])),
                             max_cross)
        blocked_run += (live & launched & (bl != 0))
        for k, thr in enumerate(CURVE_MS):
            take = live & (t_ms >= thr) & np.isnan(curve[:, k])
            curve[take, k] = sp[take]
        just_in = live & (p[:, 1] >= GOAL_Y)
        arrive_ms = np.where(just_in, t_ms, arrive_ms)
        arrive_speed = np.where(just_in, sp, arrive_speed)
        arrived |= just_in

    return dict(peak=peak, peak_y=peak_y, arrived=arrived, arrive_ms=arrive_ms,
                arrive_speed=arrive_speed, gate_tick=gate_tick, gate_ms=gate_ms,
                over_gate=over_gate, launch_sp=launch_sp, launch_y=launch_y,
                launch_ms=launch_ms, max_cross=max_cross, blocked_run=blocked_run,
                curve=curve, floor_z=floor_z)


def corridor_probe():
    """Trace the corridor extents so the controller's room is known, not assumed."""
    o = np.array([[224, -1408, 40], [224, -1408, 40],
                  [224, 700, 40], [224, 700, 40],
                  [224, -1408, 40], [224, -1408, 40]], np.float32)
    d = np.array([[1, 0, 0], [-1, 0, 0], [1, 0, 0], [-1, 0, 0],
                  [0, 1, 0], [0, -1, 0]], np.float32)
    fr, _, ss = qwsim.trace_rays(o, d, 8192.0)
    return dict(half_width_at_start_u=[round(float(fr[0] * 8192), 1),
                                       round(float(fr[1] * 8192), 1)],
                half_width_mid_u=[round(float(fr[2] * 8192), 1),
                                  round(float(fr[3] * 8192), 1)],
                ahead_u=round(float(fr[4] * 8192), 1),
                behind_u=round(float(fr[5] * 8192), 1))


def main():
    qwsim.set_num_threads(16)
    checksum = qwsim.load_bsp(MAP)
    qwsim.set_movevars(qwsim.default_movevars())
    mv = qwsim.get_movevars()
    print(f"map checksum2={checksum:08x}  movevars={mv}", flush=True)
    walls = corridor_probe()
    print("corridor probe:", walls, flush=True)

    # --- calibration: circle chirality x turn rate x launch speed x 4 phases ------
    chirs, omegas, launches, phases = [-1, 1], [3.0, 4.0, 5.0, 6.0], \
        [430.0, 450.0, 470.0, 485.0], [0.0, 90.0, 180.0, 270.0]
    combos = [(c, c * w, ls, ph) for c in chirs for w in omegas
              for ls in launches for ph in phases]
    spin_side = np.array([c[0] for c in combos], np.float32)
    omega = np.array([c[1] for c in combos], np.float32)
    launch = np.array([c[2] for c in combos], np.float32)
    yaw0 = np.array([c[3] for c in combos], np.float32)
    modes = ["p13"] * len(combos)
    r = simulate(spin_side, omega, launch, yaw0, modes)

    best = {}
    for i, (c, w, ls, ph) in enumerate(combos):
        key = (c, abs(w), ls)
        val = (float(r["peak"][i]), bool(r["arrived"][i]), ph)
        if key not in best or val > best[key]:
            best[key] = val
    # rank by peak, then arrival; among ties prefer the HIGHER launch threshold —
    # a low threshold makes unlucky phases leave the circle before it is done banking
    ranked = sorted(best.items(),
                    key=lambda kv: (round(kv[1][0], 1), kv[1][1], kv[0][2]),
                    reverse=True)
    for key, val in ranked[:6]:
        print(f"  cal chir={key[0]:+d} omega={key[1]:.0f} launch={key[2]:.0f}: "
              f"peak {val[0]:.1f} arrived={val[1]} (phase {val[2]:.0f})", flush=True)
    (b_chir, b_omega, b_launch), _ = ranked[0]
    print(f"calibrated: chir={b_chir:+d} omega={b_omega:.0f} deg/tick "
          f"launch={b_launch:.0f} u/s", flush=True)

    # --- main measurement: 8 start phases x 3 msec modes ---------------------------
    phases8 = [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0]
    mode_list = ["p13", "mix", "p12"]
    rows = []
    for mode in mode_list:
        n = len(phases8)
        rr = simulate(np.full(n, b_chir, np.float32),
                      np.full(n, b_chir * b_omega, np.float32),
                      np.full(n, b_launch, np.float32),
                      np.array(phases8, np.float32), [mode] * n)
        for i in range(n):
            rows.append(dict(
                msec_mode=mode, yaw0=phases8[i],
                peak=round(float(rr["peak"][i]), 1),
                peak_y=round(float(rr["peak_y"][i]), 0),
                launch_speed=round(float(rr["launch_sp"][i]), 1),
                launch_y=round(float(rr["launch_y"][i]), 0),
                launch_ms=int(rr["launch_ms"][i]),
                gate820_tick=int(rr["gate_tick"][i]),
                gate820_ms=int(rr["gate_ms"][i]),
                ticks_over_820=int(rr["over_gate"][i]),
                arrived=bool(rr["arrived"][i]),
                arrive_ms=int(rr["arrive_ms"][i]),
                arrive_speed=(round(float(rr["arrive_speed"][i]), 1)
                              if rr["arrived"][i] else None),
                speed_at_2_4_6_8_s=[None if np.isnan(x) else round(float(x), 1)
                                    for x in rr["curve"][i]],
                max_cross_u=round(float(rr["max_cross"][i]), 1),
                blocked_ticks_run=int(rr["blocked_run"][i]),
            ))
        pk = np.array([row["peak"] for row in rows if row["msec_mode"] == mode])
        print(f"mode {mode}: peaks {sorted(pk.tolist())}  "
              f"max {pk.max():.1f} median {np.median(pk):.1f}", flush=True)

    p13 = np.array([row["peak"] for row in rows if row["msec_mode"] == "p13"])
    mix = np.array([row["peak"] for row in rows if row["msec_mode"] == "mix"])
    p12 = np.array([row["peak"] for row in rows if row["msec_mode"] == "p12"])
    best_row = max(rows, key=lambda row: row["peak"])

    out = dict(
        generated="2026-07-30",
        map=MAP,
        map_checksum2=f"{checksum:08x}",
        movevars=mv,
        sim="libqwsim (bit-exact mvdsv pmove), server integrates whole msec",
        corridor=dict(start=[float(x) for x in START], goal_y=GOAL_Y,
                      probe=walls),
        physics_note=(
            "PM_AirAccelerate: accelspeed = accelerate*wishspeed*dt = 41.6 > 30-cap "
            "=> optimal wishdir perpendicular to velocity, +900 u^2/s^2 per airborne "
            "tick regardless of dt; jump pressed the tick after landing clears "
            "onground before PM_Friction, so a perfect bunnyhop is friction-free"),
        controller=dict(source="pipeline/strafe_expert.py steering logic",
                        spin_side=int(b_chir), spin_omega_deg_per_tick=b_omega,
                        launch_speed=b_launch, heading_band_deg=HEADING_BAND,
                        cross_gain=CROSS_GAIN, cross_cap=CROSS_CAP),
        gate=GATE,
        old_rex_env_peak=OLD_PEAK,
        summary=dict(
            peak_max_msec13=round(float(p13.max()), 1),
            peak_median_msec13=round(float(np.median(p13)), 1),
            peak_max_mixed_12_13=round(float(mix.max()), 1),
            peak_median_mixed_12_13=round(float(np.median(mix)), 1),
            peak_max_msec12=round(float(p12.max()), 1),
            peak_median_msec12=round(float(np.median(p12)), 1),
            gate_820_reached_msec13=bool(p13.max() >= GATE),
            gate_820_reached_mixed=bool(mix.max() >= GATE),
            runs_over_gate_msec13=int((p13 >= GATE).sum()),
            runs_over_gate_mixed=int((mix >= GATE).sum()),
            best_run=best_row,
            delta_vs_old_ceiling=round(float(p13.max()) - OLD_PEAK, 1),
        ),
        runs=rows,
    )
    EVIDENCE.parent.mkdir(exist_ok=True)
    EVIDENCE.write_text(json.dumps(out, indent=1))
    print("wrote", EVIDENCE)
    print(json.dumps(out["summary"], indent=1))


if __name__ == "__main__":
    main()
