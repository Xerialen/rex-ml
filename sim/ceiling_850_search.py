#!/usr/bin/env python3
"""Search for a known-physics path to peak 850 u/s on 100m.bsp (libqwsim, bit-exact).

Baseline: sim/strafe_ceiling_qwsim.py measured 833.4 peak (msec=13, straight-corridor
controller, stop at goal_y=2900). Owner sub-goal is peak 850. Since every airborne tick
adds exactly +900 u^2/s^2 (addspeed cap always binds; perfect bunny is friction-free),
v^3 grows linearly with PATH LENGTH at fixed dt: v^3 ~= v0^3 + 1350 * L_path / dt.
The ceiling is corridor-length-limited, so the search space is exactly "buy more path":

  A. serpentine: run at a constant heading offset +-phi from the corridor axis,
     flipping at the walls -> path factor 1/cos(phi). Turning is FREE in v^2 terms
     (the same perpendicular +30 add that accelerates is what turns the velocity);
     the only cost is corridor width consumed by the turn radius r = v^2*dt/30.
  B. rear start: walk back to the rear wall (y=-2176) before the launch circle,
     buying ~400-500 u of extra path (launch_y ~-1930 vs ~-1400..-1520). The
     start gate is a 40-high curb at y~-1680 (x 0..512) flanked by posts at
     x 600..616 and x -104..-92 (from y~-1528) -> walk back, circle and launch
     through the clear right lane x 636..736.
  C. overrun: keep accelerating past the finish line y=2900 toward the far wall
     (y=3584). The "barrier" at y~3068 is a floating sign (z 104..128, x -72..632)
     with 16-high floor trims; the side lanes x<-104 and x>664 are fully clear.
     Reported separately: peak past the finish is not "peak during the 100m run".
  D. msec regimes: AM101 (vendor/mvdsv-src/src/sv_user.c SV_RunCmd) only trims a
     cmd's msec DOWN when claimed msec exceeds elapsed wall time (+ a bank capped at
     500 ms); there is NO lower bound on msec (byte, >=1 accepted; msec>50 is split).
     So msec=12 is legal at <=83.3 cmds/s wall-honest; anything below 12 needs a cmd
     rate above the community-standard 77 fps => reported as protocol exploitation,
     separated from the honest 77 Hz client (13/12 mix, 12.987 ms avg).

Geometry probed via trace_rays (this file re-probes and records it):
  corridor x in [-256, 768] (usable ~[-220, 732] with 16u player halfwidth + margin),
  y in [-2176, 3584], flat floor z=0, ceiling z=256, movevars bunnyspeedcap=0,
  airstep=0, rampjump=0 -> no vertical geometry to exploit (no ramps or stairs
  anywhere on the course; the only 3D features are the start curb and finish sign).

Output: evidence/ceiling_850_search.json
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
AXIS_DEG = 90.0
TARGET = 850.0
MAX_TICKS = 5000

# corridor bounds with player halfwidth 16 + safety margin
X_LO, X_HI = -220.0, 732.0
BACK_Y = -1990.0          # circle entry y for rear starts (rear wall at -2176)
# start gate: curb x 0..512 (40 high) at y~-1680 plus posts at x 600..616 and
# x -104..-92 from y~-1528 -> clear lanes x 636..736 (right), x -240..-124
# (left). A rear launch needs heading ~90 INSIDE a lane; for a clockwise
# circle (spin -1) that is its west-most point => left lane, for a counter-
# clockwise circle (spin +1) its east-most point => right lane.
BACK_LANE_CW, BACK_LANE_CCW = -182.0, 686.0
LANE_HALF = 46.0
# the ground circle is entered heading SOUTH, which for a CW circle is its east
# extreme and for a CCW circle its west extreme; the launch (heading north)
# happens ~2r away on the opposite extreme. r ~= v/omega ~= 90 u near launch
# speed, so enter the circle ~180 u to the lane's inside, south of the gate.
CIRC_ENTRY_OFF = 180.0
SERP_ON_Y = -1440.0       # rear starts: hold the lane until past the start gate
OVERRUN_STOP_Y = 3480.0   # far wall at 3584
STRAIGHTEN_Y = 2450.0     # overrun: leave the weave here to line up with a gap lane
# clear lanes through y~3068: beside the sign/trims, or under the sign
# (16-high floor trims sit at x~-104..-40 and x~600..664, y 3052..3100)
GAP_LANES = np.array([-170.0, 300.0, 706.0], np.float32)

HEADING_BAND = 2.0
CROSS_GAIN = 0.06
CROSS_CAP = 25.0
LAUNCH_TOL = 14.0
LAUNCH_BY_MODE = {"p13": 485.0, "mix": 485.0, "p12": 450.0, "p6": 420.0}

EVIDENCE = Path("/home/benjamin-adm/rex-ml/evidence/ceiling_850_search.json")


def wrap(a):
    return ((a + 180.0) % 360.0) - 180.0


def msec_stream(mode: str, t: int) -> int:
    if mode == "p13":
        return 13
    if mode == "p12":
        return 12
    if mode == "p6":
        return 6
    return 12 if (t % 77) == 76 else 13  # mix: honest 77 Hz client, 12.987 ms avg


def simulate(cfgs, trace=False):
    """cfgs: list of dicts with keys mode, yaw0, spin_side, omega, launch,
    serp_phi (0 = centering controller), back_start (bool), overrun (bool).
    trace=True additionally returns a per-tick log for slot 0
    [t_ms, y, x, speed, onground, blocked]."""
    n = len(cfgs)
    qwsim.alloc_slots(n)
    ids = np.arange(n, dtype=np.int32)
    pos = np.tile(START, (n, 1)).astype(np.float32)
    vel = np.zeros((n, 3), np.float32)
    ang = np.zeros((n, 3), np.float32)
    yaw0 = np.array([c["yaw0"] for c in cfgs], np.float32)
    ang[:, 1] = yaw0
    qwsim.reset(ids, pos, vel, ang)

    mode = [c["mode"] for c in cfgs]
    spin_side = np.array([c["spin_side"] for c in cfgs], np.float32)
    omega = np.array([c["omega"] for c in cfgs], np.float32)
    launch_thr = np.array([c["launch"] for c in cfgs], np.float32)
    phi = np.array([c["serp_phi"] for c in cfgs], np.float32)
    back = np.array([c["back_start"] for c in cfgs], bool)
    back_lane = np.where(spin_side < 0, BACK_LANE_CW, BACK_LANE_CCW
                         ).astype(np.float32)
    overrun = np.array([c["overrun"] for c in cfgs], bool)
    lane = np.full(n, np.nan, np.float32)  # overrun gap lane, chosen on the fly

    z16 = np.zeros(n, np.int16)
    z8 = np.zeros(n, np.uint8)
    ms13 = np.full(n, 13, np.uint8)
    for _ in range(40):  # settle to floor
        p, v, og, wl, jh, bl = qwsim.step_batch(ids, ang, z16, z16, z16, z8, ms13)
        if og.all():
            break

    # phase: 0 walk-back, 1 circle, 2 run
    phase = np.where(back, 0, 1).astype(np.int8)
    view_yaw = yaw0.copy()
    side = -np.ones(n, np.float32)
    serp_dir = np.ones(n, np.float32)     # +1 = drifting toward X_HI
    og_obs = og.astype(bool)
    circ_ticks = np.zeros(n, np.int64)
    tick_log = []

    peak_pre = np.zeros(n, np.float32)          # max speed at/before goal crossing
    peak_pre_y = np.full(n, np.nan, np.float32)
    peak_all = np.zeros(n, np.float32)          # max speed anywhere (overrun incl.)
    peak_all_y = np.full(n, np.nan, np.float32)
    crossed = np.zeros(n, bool)
    cross_ms = np.full(n, -1, np.int64)
    cross_speed = np.full(n, np.nan, np.float32)
    done = np.zeros(n, bool)
    t_ms = np.zeros(n, np.int64)
    launch_sp = np.full(n, np.nan, np.float32)
    launch_y = np.full(n, np.nan, np.float32)
    min_x = np.full(n, np.inf, np.float32)
    max_x = np.full(n, -np.inf, np.float32)
    blocked_run = np.zeros(n, np.int64)
    t850_ms = np.full(n, -1, np.int64)
    t850_y = np.full(n, np.nan, np.float32)

    for t in range(MAX_TICKS):
        live = ~done
        if not live.any():
            break
        was_live0 = bool(live[0])
        sp = np.linalg.norm(v[:, :2], axis=1)
        hdg = np.degrees(np.arctan2(v[:, 1], v[:, 0]))

        # ---- phase 0: walk into the side lane, south past the gate, then ------
        # sidestep to the circle entry point (the start-gate curb at y~-1680
        # spans x 0..512: go around, not over)
        wb = live & (phase == 0)
        circ_x = back_lane + np.where(spin_side < 0, 1.0, -1.0) * CIRC_ENTRY_OFF
        wb_lane = np.where(p[:, 1] > -1750.0, back_lane, circ_x)
        wb_yaw = np.where((p[:, 1] > -1500.0)
                          & (np.abs(p[:, 0] - wb_lane) > LANE_HALF),
                          np.where(wb_lane < p[:, 0], 180.0, 0.0),
                          270.0 - np.clip(0.2 * (p[:, 0] - wb_lane),
                                          -40.0, 40.0))
        phase = np.where(wb & (p[:, 1] <= BACK_Y), 1, phase)

        # ---- phase 1: ground circle to bank launch speed ----------------------
        # the circle's attainable speed depends on where it drifts (rear starts
        # enter it with 320 u/s of momentum), so the threshold decays slowly
        # after 250 circle ticks: a launch is guaranteed near the local cap
        # instead of phase-locking below a fixed threshold forever
        circ = live & (phase == 1)
        circ_ticks = circ_ticks + circ
        eff_thr = np.maximum(launch_thr - 0.15 * np.maximum(circ_ticks - 250, 0),
                             400.0)
        newly = circ & (sp >= eff_thr) & (np.abs(wrap(hdg - AXIS_DEG)) < LAUNCH_TOL)
        # rear starts must launch INSIDE their clear lane so the run threads the
        # start gate instead of clipping a post or the curb
        newly &= ~back | (np.abs(p[:, 0] - back_lane) < LANE_HALF)
        phase = np.where(newly, 2, phase)
        launch_sp = np.where(newly, sp, launch_sp)
        launch_y = np.where(newly, p[:, 1], launch_y)

        # ---- phase 2: bunny run ----------------------------------------------
        run = live & (phase == 2)
        # serpentine flip: turn depth r*(1-cos 2phi covered at mid-turn = 1-cos phi)
        dt_arr = np.array([msec_stream(m, t) for m in mode], np.float32) * 0.001
        r_turn = sp * sp * dt_arr / 30.0
        phir = np.radians(phi)
        depth = r_turn * (1.0 - np.cos(phir)) + 2.0 * sp * dt_arr * np.sin(phir) + 40.0
        serp_dir = np.where(run & (phi > 0) & (serp_dir > 0)
                            & (p[:, 0] > X_HI - depth), -1.0, serp_dir)
        serp_dir = np.where(run & (phi > 0) & (serp_dir < 0)
                            & (p[:, 0] < X_LO + depth), 1.0, serp_dir)
        # heading 90-phi has +x component => dir=+1 uses target 90-phi
        serp_aim = AXIS_DEG - serp_dir * phi
        # centering lane: rear starts hold the side lane (with a stiffer gain)
        # until past the start gate
        in_lane_hold = back & (p[:, 1] < SERP_ON_Y)
        lane_x = np.where(in_lane_hold, back_lane, START[0])
        lane_gain = np.where(in_lane_hold, 0.15, CROSS_GAIN)
        lane_cap = np.where(in_lane_hold, 20.0, CROSS_CAP)
        center_aim = AXIS_DEG + np.clip(lane_gain * (p[:, 0] - lane_x),
                                        -lane_cap, lane_cap)
        serp_active = (phi > 0) & (p[:, 1] >= np.where(back, SERP_ON_Y, -1e9))
        # overrun: straighten into the NEAREST clear gap lane past STRAIGHTEN_Y
        straighten = overrun & (p[:, 1] >= STRAIGHTEN_Y)
        pick = straighten & np.isnan(lane)
        if pick.any():
            near = GAP_LANES[np.argmin(
                np.abs(p[:, 0, None] - GAP_LANES[None, :]), axis=1)]
            lane = np.where(pick, near, lane)
        gap_aim = AXIS_DEG + np.clip(
            CROSS_GAIN * (p[:, 0] - np.where(np.isnan(lane), 224.0, lane)),
            -CROSS_CAP, CROSS_CAP)
        aim = np.where(serp_active, serp_aim, center_aim)
        aim = np.where(straighten, gap_aim, aim)

        err = wrap(hdg - aim)
        side = np.where(err > HEADING_BAND, 1.0,
                        np.where(err < -HEADING_BAND, -1.0, side)).astype(np.float32)

        fmove = np.where(wb, 700, 0).astype(np.int16)
        smove = np.where(run, side * 700,
                         np.where(circ, spin_side * 700, 0)).astype(np.int16)
        view_yaw = np.where(run, hdg,
                            np.where(circ, view_yaw + omega, wb_yaw)
                            ).astype(np.float32)
        ang[:, 1] = view_yaw
        buttons = np.where(run & og_obs, 2, 0).astype(np.uint8)
        ms = np.array([msec_stream(m, t) for m in mode], np.uint8)

        p, v, og, wl, jh, bl = qwsim.step_batch(ids, ang, fmove, smove, z16,
                                                buttons, ms)
        og_obs = og.astype(bool)
        t_ms = np.where(live, t_ms + ms, t_ms)

        sp = np.linalg.norm(v[:, :2], axis=1).astype(np.float32)
        pre = live & ~crossed
        b1 = pre & (sp > peak_pre)
        peak_pre = np.where(b1, sp, peak_pre)
        peak_pre_y = np.where(b1, p[:, 1], peak_pre_y)
        b2 = live & (sp > peak_all)
        peak_all = np.where(b2, sp, peak_all)
        peak_all_y = np.where(b2, p[:, 1], peak_all_y)
        f850 = live & (sp >= TARGET) & (t850_ms < 0)
        t850_ms = np.where(f850, t_ms, t850_ms)
        t850_y = np.where(f850, p[:, 1], t850_y)
        min_x = np.where(live, np.minimum(min_x, p[:, 0]), min_x)
        max_x = np.where(live, np.maximum(max_x, p[:, 0]), max_x)
        blocked_run = np.where(run, blocked_run + (bl != 0), blocked_run)

        just = pre & (p[:, 1] >= GOAL_Y) & (phase == 2)
        cross_ms = np.where(just, t_ms, cross_ms)
        cross_speed = np.where(just, sp, cross_speed)
        crossed |= just
        done |= just & ~overrun
        done |= crossed & overrun & (p[:, 1] >= OVERRUN_STOP_Y)

        if trace and was_live0:
            # logged for every executed tick of slot 0 INCLUDING the
            # goal-crossing tick (done is set on that tick, after this)
            tick_log.append([int(t_ms[0]), round(float(p[0, 1]), 1),
                             round(float(p[0, 0]), 1), round(float(sp[0]), 2),
                             int(og[0]), int(bl[0])])

    out = []
    for i, c in enumerate(cfgs):
        out.append(dict(
            mode=c["mode"], yaw0=float(c["yaw0"]), serp_phi=float(c["serp_phi"]),
            spin=int(c["spin_side"]),
            back_start=bool(c["back_start"]), overrun=bool(c["overrun"]),
            lane=(None if np.isnan(lane[i]) else float(lane[i])),
            launch_speed=round(float(launch_sp[i]), 1),
            launch_y=round(float(launch_y[i]), 0),
            peak_pre_goal=round(float(peak_pre[i]), 1),
            peak_pre_goal_y=round(float(peak_pre_y[i]), 0),
            speed_at_goal=(round(float(cross_speed[i]), 1)
                           if crossed[i] else None),
            goal_ms=int(cross_ms[i]),
            peak_total=round(float(peak_all[i]), 1),
            peak_total_y=round(float(peak_all_y[i]), 0),
            first_850_ms=int(t850_ms[i]),
            first_850_y=(None if t850_ms[i] < 0 else round(float(t850_y[i]), 0)),
            min_x=round(float(min_x[i]), 0), max_x=round(float(max_x[i]), 0),
            blocked_ticks_run=int(blocked_run[i]),
            finished=bool(done[i]),
        ))
    if trace:
        return out, tick_log
    return out


def probe_geometry():
    ys = np.arange(-2100.0, 3500.0, 400.0)
    o = np.array([[224.0, y, 40.0] for y in ys], np.float32)
    dp, _, _ = qwsim.trace_rays(o, np.tile([[1.0, 0, 0]], (len(ys), 1)
                                           ).astype(np.float32), 8192.0)
    dn, _, _ = qwsim.trace_rays(o, np.tile([[-1.0, 0, 0]], (len(ys), 1)
                                           ).astype(np.float32), 8192.0)
    return dict(
        x_walls=[round(float(224 + dp.max() * 8192), 0),
                 round(float(224 - dn.max() * 8192), 0)],
        y_walls=[-2176.0, 3584.0],
        width_u=1024.0, floor_z=0.0, ceiling_z=256.0,
        finish_sign=dict(y=3068.0, z_span=[104.0, 128.0], x_span=[-72.0, 632.0],
                         trims="16-high floor trims near x -104..-40 and "
                               "600..664, y 3052..3100",
                         note="floating: passable underneath and via side lanes"),
        start_gate=dict(curb=dict(y=-1680.0, height=40.0, x_span=[0.0, 512.0]),
                        posts=dict(y_from=-1528.0,
                                   x_spans=[[-104.0, -92.0], [600.0, 616.0]]),
                        note="STEPSIZE 18 cannot climb the curb; clear lanes "
                             "x 636..736 and x -240..-124"),
        vertical="airstep=0, rampjump=0, flat floor, no ramps/stairs: "
                 "no vertical geometry to exploit on this map")


def grid(modes, phis, backs, overruns, phases, spins=((-1, 4.0),)):
    cfgs = []
    for m in modes:
        for ph in phis:
            for bk in backs:
                for ov in overruns:
                    for sp in spins:
                        for y0 in phases:
                            cfgs.append(dict(
                                mode=m, yaw0=y0, spin_side=sp[0],
                                omega=sp[0] * sp[1],
                                launch=LAUNCH_BY_MODE[m], serp_phi=ph,
                                back_start=bk, overrun=ov))
    return cfgs


def summarize(rows, key="peak_pre_goal"):
    v = np.array([r[key] for r in rows], np.float32)
    return dict(n=len(rows), max=round(float(v.max()), 1),
                median=round(float(np.median(v)), 1),
                best=max(rows, key=lambda r: r[key]))


def main():
    qwsim.set_num_threads(16)
    checksum = qwsim.load_bsp(MAP)
    qwsim.set_movevars(qwsim.default_movevars())
    mv = qwsim.get_movevars()
    print(f"map checksum2={checksum:08x}", flush=True)
    geo = probe_geometry()
    print("geometry:", geo, flush=True)

    phases = [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0]
    experiments = {}

    # A. replication of the 833.4 baseline (straight controller, honest msec=13)
    rows = simulate(grid(["p13"], [0.0], [False], [False], phases))
    experiments["A_baseline_p13"] = dict(
        desc="replication of strafe_ceiling_qwsim.py (straight, stop at goal)",
        summary=summarize(rows), runs=rows)
    print("A baseline p13:", experiments["A_baseline_p13"]["summary"], flush=True)

    # B. serpentine sweep, honest msec=13, finish-line peak
    rows = simulate(grid(["p13"], [15.0, 25.0, 35.0, 45.0, 55.0], [False],
                         [False], phases))
    by_phi = {}
    for phv in [15.0, 25.0, 35.0, 45.0, 55.0]:
        sel = [r for r in rows if r["serp_phi"] == phv]
        by_phi[str(phv)] = summarize(sel)
        print(f"B serp phi={phv}: {by_phi[str(phv)]['max']} "
              f"(median {by_phi[str(phv)]['median']})", flush=True)
    experiments["B_serpentine_p13"] = dict(
        desc="constant heading offset +-phi, wall-flip; peak at/before goal",
        summary_by_phi=by_phi, runs=rows)
    best_phi = max(by_phi, key=lambda k: by_phi[k]["max"])
    bphi = float(best_phi)

    # C. rear start, honest msec=13: straight and best-phi serpentine,
    # both circle chiralities (each maps to its own clear start-gate lane)
    c_rows = simulate(grid(["p13"], [0.0, bphi], [True], [False], phases,
                           spins=((-1, 4.0), (1, 4.0))))
    c_straight = summarize([r for r in c_rows if r["serp_phi"] == 0.0])
    c_serp = summarize([r for r in c_rows if r["serp_phi"] == bphi])
    experiments["C_rear_start_p13"] = dict(
        desc=f"walk back to y={BACK_Y}, circle at rear wall, launch ~600u earlier",
        straight=c_straight, serp_best_phi=c_serp, best_phi=bphi, runs=c_rows)
    print("C rear straight:", c_straight["max"], " rear serp:", c_serp["max"],
          flush=True)

    # best honest msec=13 finish-line config found so far (for D/E/F/verify)
    b_rows = experiments["B_serpentine_p13"]["runs"]
    cand = experiments["A_baseline_p13"]["runs"] + b_rows + c_rows
    best13 = max(cand, key=lambda r: r["peak_pre_goal"])
    best_cfg = dict(phi=best13["serp_phi"], back=best13["back_start"],
                    yaw0=best13["yaw0"], spin=best13["spin"])
    best_spins = ((best_cfg["spin"], 4.0),)
    print("best honest p13 so far:", best13["peak_pre_goal"], best_cfg, flush=True)

    # D. overrun past the finish line (reported separately), honest msec=13
    rows = simulate(grid(["p13"], [0.0, best_cfg["phi"]], [best_cfg["back"]],
                         [True], phases, spins=best_spins))
    experiments["D_overrun_p13"] = dict(
        desc="continue past goal (clear lanes at the y~3068 sign) to y~3480: "
             "NOT a 100m-run peak; peak_total may lie beyond the finish line",
        summary=summarize(rows, key="peak_total"), runs=rows)
    print("D overrun:", experiments["D_overrun_p13"]["summary"]["max"], flush=True)

    # E. best finish-line config under the honest 77 Hz mix (12.987 ms avg)
    rows = simulate(grid(["mix"], [best_cfg["phi"]], [best_cfg["back"]],
                         [False], phases, spins=best_spins))
    experiments["E_best_mix77"] = dict(
        desc="best honest config under the true 77 Hz client msec stream",
        summary=summarize(rows), runs=rows)
    print("E mix77:", experiments["E_best_mix77"]["summary"]["max"], flush=True)

    # F. msec regimes for the same config: p12 (83.3 Hz) and p6 (166.7 Hz);
    # at 6 ms per tick the ground circle needs a slower per-tick spin rate
    rows = simulate(grid(["p12"], [best_cfg["phi"]], [best_cfg["back"]],
                         [False], phases, spins=best_spins)
                    + grid(["p6"], [best_cfg["phi"]], [best_cfg["back"]],
                           [False], phases, spins=((best_cfg["spin"], 2.0),)))
    f12 = summarize([r for r in rows if r["mode"] == "p12"])
    f6 = summarize([r for r in rows if r["mode"] == "p6"])
    experiments["F_msec_regimes"] = dict(
        desc="same config at msec=12 (needs 83.3 cmds/s) and msec=6 (166.7 "
             "cmds/s): server-accepted but above the 77 fps community standard "
             "=> protocol exploitation, kept separate",
        p12=f12, p6=f6, runs=rows)
    print("F p12:", f12["max"], " p6:", f6["max"], flush=True)

    # ---- standalone verification of the single best honest finish-line run ----
    # re-simulate it alone with a per-tick trace and PROVE the peak lies at or
    # before the goal-crossing tick under the claimed msec stream
    honest_rows = ([r for r in cand if not r["overrun"]]
                   + [r for r in experiments["E_best_mix77"]["runs"]])
    v_row = max(honest_rows, key=lambda r: r["peak_pre_goal"])
    v_cfg = [dict(mode=v_row["mode"], yaw0=v_row["yaw0"],
                  spin_side=v_row["spin"], omega=v_row["spin"] * 4.0,
                  launch=LAUNCH_BY_MODE[v_row["mode"]],
                  serp_phi=v_row["serp_phi"], back_start=v_row["back_start"],
                  overrun=False)]
    v_out, tick_log = simulate(v_cfg, trace=True)
    v = v_out[0]
    speeds = [row[3] for row in tick_log]
    pk_i = int(np.argmax(speeds))
    pk = tick_log[pk_i]
    goal_ticks = [i for i, row in enumerate(tick_log) if row[1] >= GOAL_Y]
    cross_i = goal_ticks[0] if goal_ticks else -1
    verification = dict(
        config=dict(mode=v_row["mode"], yaw0=v_row["yaw0"],
                    serp_phi=v_row["serp_phi"], back_start=v_row["back_start"]),
        reproduced_peak=round(float(max(speeds)), 1),
        grid_peak=v_row["peak_pre_goal"],
        peak_matches_grid=bool(abs(max(speeds) - v_row["peak_pre_goal"]) < 0.5),
        peak_tick=dict(t_ms=pk[0], y=pk[1], x=pk[2], speed=pk[3]),
        goal_cross_t_ms=(tick_log[cross_i][0] if cross_i >= 0 else None),
        peak_at_or_before_goal_cross=bool(cross_i >= 0 and pk_i <= cross_i),
        note="trace ends at the goal-crossing tick (overrun disabled), so every "
             "logged tick incl. the peak is at or before the finish line",
        speed_curve_every_10_ticks=[tick_log[i] for i in
                                    range(0, len(tick_log), 10)],
        peak_window=tick_log[max(0, pk_i - 10):pk_i + 2],
        columns=["t_ms", "y", "x", "speed", "onground", "blocked"],
    )
    print("verification:", {k: verification[k] for k in
                            ("reproduced_peak", "grid_peak", "peak_tick",
                             "peak_at_or_before_goal_cross")}, flush=True)

    honest_best = verification["reproduced_peak"]

    out = dict(
        generated="2026-07-30",
        map=MAP, map_checksum2=f"{checksum:08x}", movevars=mv,
        sim="libqwsim (bit-exact mvdsv pmove)",
        target=TARGET,
        baseline_prior=dict(file="evidence/strafe_ceiling_qwsim.json",
                            peak_max_msec13=833.4, peak_max_msec12=842.9),
        geometry=geo,
        physics=dict(
            per_tick_gain_u2="+900 (addspeed cap 30 always binds, wishdir "
                             "perpendicular; independent of dt)",
            growth_law="v^3 ~= v0^3 + 1350 * L_path / dt (path-length limited)",
            turning="free in v^2: the perpendicular +30 add is also the turn",
            am101="SV_RunCmd trims msec only when claimed msec > elapsed wall ms "
                  "(+bank capped 500 ms); no lower bound on msec (sv_speedcheck "
                  "default 1). Honest 77 Hz = 13/12 mix; msec=12 needs 83.3 "
                  "cmds/s; below 12 is >83 Hz = protocol exploitation."),
        experiments=experiments,
        verification=verification,
        conclusion=dict(
            honest_77hz_best_verified_peak_at_or_before_goal=honest_best,
            reached_850_honest=bool(honest_best >= TARGET
                                    and verification["peak_matches_grid"]
                                    and verification[
                                        "peak_at_or_before_goal_cross"]),
            overrun_peak_beyond_finish=experiments["D_overrun_p13"]["summary"][
                "max"],
            p12_83hz_peak=experiments["F_msec_regimes"]["p12"]["max"],
            p6_167hz_peak=experiments["F_msec_regimes"]["p6"]["max"],
        ),
    )
    EVIDENCE.parent.mkdir(exist_ok=True)
    EVIDENCE.write_text(json.dumps(out, indent=1))
    print("wrote", EVIDENCE)
    print(json.dumps(out["conclusion"], indent=1))


if __name__ == "__main__":
    main()
