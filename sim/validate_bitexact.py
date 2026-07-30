#!/usr/bin/env python
"""Bit-exactness validation of libqwsim against recorded QWD demos.

For each selected dm3 QWD run: seed a sim slot from the recorded state,
feed the recorded usercmds through the byte-identical mvdsv pmove, and
compare pos/vel tick-for-tick against replay_ticks.

Divergence handling: when the sim leaves the recorded trajectory by more
than CUT_POS/CUT_VEL the tick is counted as clipped, the divergence is
classified (teleport / water / lift / velocity impulse / seq_break / other)
and the slot is re-seeded from the recorded state at that tick — i.e. the
validation segments are cut at events pmove cannot know about (server-side
entities, damage knockback), exactly as anticipated in the brief.

Output: evidence/libqwsim_bitexact.json
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import qwsim  # noqa: E402

STORE = Path("/home/benjamin-adm/dm3-extract/store-dm3")
RT = str(STORE / "replay_ticks/**/*.parquet")
UC = str(STORE / "usercmds/**/*.parquet")
DM = str(STORE / "demos.parquet")
MV = str(STORE / "movevars/*.parquet")
DM3_BSP = "/home/benjamin-adm/mlx/qwserver/serverdir/id1/maps/dm3.bsp"
EVIDENCE = Path("/home/benjamin-adm/rex-ml/evidence/libqwsim_bitexact.json")

ANG = 360.0 / 65536.0

# Ground truth = wire ticks only (wire_state_present): QW protocol quantises
# player origin to 1/8 u (13.3 fixed point) and velocity to 1 u/s (short).
# Non-wire replay_ticks rows are the corpus parser's own forward simulation
# (see `residual` column) — another pmove reimplementation, NOT ground truth.
# Divergence cut thresholds are therefore a bit above one wire quantum:
CUT_POS = 0.5      # u   (wire quantum 0.125)
CUT_VEL = 2.5      # u/s (wire quantum 1.0)

# dm3 func_plat travel volumes from the BSP itself (LUMP_MODELS bounds of the
# *1..*3 submodels named func_plat in the entity lump; plat travel = zsize-8),
# inflated by the player hull. Used only to CLASSIFY divergences.
# trigger_teleport volumes *4/*5 likewise (teleports also classify via the
# >64 u position jump).
def _plat_zone(mins, maxs):
    travel = (maxs[2] - mins[2]) - 8
    return ((mins[0] - 17, mins[1] - 17, mins[2] - travel - 25),
            (maxs[0] + 17, maxs[1] + 17, maxs[2] + 33))

LIFT_ZONES = [
    _plat_zone((593, 657, -291), (655, 719, -129)),
    _plat_zone((593, 833, -127), (655, 895, -1)),
    _plat_zone((449, 833, 17), (575, 895, 191)),
]
TELE_ZONES = [
    ((1169 - 17, -927 - 17, -15 - 25), (1191 + 17, -881 + 17, 15 + 33)),
    ((-519 - 17, -471 - 17, 1 - 25), (-497 + 17, -425 + 17, 47 + 33)),
]


def in_zone(p, zones):
    for lo, hi in zones:
        if lo[0] <= p[0] <= hi[0] and lo[1] <= p[1] <= hi[1] and lo[2] <= p[2] <= hi[2]:
            return True
    return False


def short_angle(raw):
    s = raw.astype(np.int64)
    s = np.where(s >= 32768, s - 65536, s)
    return (s.astype(np.float64) * ANG).astype(np.float32)


def load_demo(con, demo_key):
    df = con.execute(f"""
        select r.cmd_ordinal, r.x, r.y, r.z, r.vx, r.vy, r.vz,
               r.onground, r.jump_held, r.waterlevel, r.wire_state_present,
               r.seq_break,
               u.msec, u.forwardmove, u.sidemove, u.upmove, u.buttons,
               u.pitch, u.yaw
        from read_parquet('{RT}') r
        join read_parquet('{UC}') u using(demo_key, slot, cmd_ordinal)
        where r.demo_key = {demo_key}
        order by r.cmd_ordinal
    """).fetchnumpy()
    return df


def movevars_for(con, movevars_id):
    row = con.execute(f"""
        select gravity, stopspeed, maxspeed, spectatormaxspeed, accelerate,
               airaccelerate, wateraccelerate, friction, waterfriction, entgravity
        from read_parquet('{MV}') where movevars_id = {movevars_id} limit 1
    """).fetchone()
    keys = ["gravity", "stopspeed", "maxspeed", "spectatormaxspeed", "accelerate",
            "airaccelerate", "wateraccelerate", "friction", "waterfriction",
            "entgravity"]
    mv = dict(zip(keys, [float(x) for x in row]))
    # per-demo serverinfo does not carry pm_*: lock the mvdsv defaults
    mv.update(dict(bunnyspeedcap=0, ktjump=1, slidefix=0, airstep=0,
                   pground=0, rampjump=0))
    return mv


def classify(prev_pos, pos, prev_wl, wl, pos_err, vel_err, gap_ticks):
    dp = np.linalg.norm(pos - prev_pos)
    if dp > 64.0 * max(1, gap_ticks) or in_zone(pos, TELE_ZONES) or in_zone(prev_pos, TELE_ZONES):
        return "teleport"
    if wl > 0 or prev_wl > 0:
        return "water"
    if in_zone(pos, LIFT_ZONES) or in_zone(prev_pos, LIFT_ZONES):
        return "lift"
    if vel_err > 20.0 and pos_err < 2.0:
        return "velocity_impulse"
    return "other"


def run_demo(demo_key, df, mv, ktjump):
    mv = dict(mv)
    mv["ktjump"] = ktjump
    qwsim.set_movevars(mv)
    qwsim.alloc_slots(1)
    ids = np.zeros(1, np.int32)

    n = len(df["cmd_ordinal"])
    rec_pos = np.stack([df["x"], df["y"], df["z"]], 1).astype(np.float32)
    rec_vel = np.stack([df["vx"], df["vy"], df["vz"]], 1).astype(np.float32)
    onground = df["onground"].astype(bool)
    jump_held = df["jump_held"].astype(bool)
    waterlevel = df["waterlevel"].astype(np.int64)
    wire = df["wire_state_present"].astype(bool)
    seqbrk = df["seq_break"].astype(bool)
    msec = df["msec"].astype(np.uint8)
    fm = df["forwardmove"].astype(np.int16)
    sm = df["sidemove"].astype(np.int16)
    um = df["upmove"].astype(np.int16)
    bt = df["buttons"].astype(np.uint8)
    pitch = short_angle(df["pitch"])
    yaw = short_angle(df["yaw"])

    def reseed(i):
        qwsim.reset(ids, rec_pos[i:i + 1], rec_vel[i:i + 1],
                    onground=np.array([onground[i]], np.uint8),
                    jump_held=np.array([jump_held[i]], np.uint8))

    # The QWD wire state in frame t is the server ack for the cmd stream and
    # lags it by a variable 0..MAXLAG cmds (network in flight). The corpus
    # parser's own `residual` column shows the same ~1-tick jumps at exactly
    # the lagging checkpoints. At each wire checkpoint we therefore match the
    # recorded state against the sim state 0..MAXLAG cmds earlier and score
    # the best offset; the accepted-offset histogram is reported.
    MAXLAG = globals().get("MAXLAG_OVERRIDE", 12)  # ack lag = RTT/frametime; online povs reach 8-10 cmds
    wire_idx = np.flatnonzero(wire)
    pos_errs, vel_errs, grid_errs = [], [], []
    exact_grid = 0
    cut_causes = Counter()
    lag_hist = Counter()
    seg_lens = []            # segment length in cmd ticks between reseeds
    compared_wire = 0        # wire checkpoints that matched
    compared_cmds = 0        # cmd ticks inside matched spans
    clipped_cmds = 0         # cmd ticks discarded because the span diverged
    skipped_cmds = 0         # unusable (seq_break / msec>50 / pre-first-wire)
    ang = np.zeros((1, 3), np.float32)

    if len(wire_idx) < 2:
        return None

    hist_p = [None] * (MAXLAG + 1)   # sim state after cmd c, c-1, ...
    hist_v = [None] * (MAXLAG + 1)

    def push_hist(p, v):
        hist_p.pop()
        hist_v.pop()
        hist_p.insert(0, p.copy())
        hist_v.insert(0, v.copy())

    def step(j):
        ang[0, 0] = pitch[j]
        ang[0, 1] = yaw[j]
        p, v, og, wl, jh, bl = qwsim.step_batch(
            ids, ang, fm[j:j + 1], sm[j:j + 1], um[j:j + 1],
            bt[j:j + 1], msec[j:j + 1])
        push_hist(p[0], v[0])

    last_d = 1   # most common ack lag; refined from accepted checkpoints
    recent_d = []            # recent accepted lags (for reseed cursor)
    search_wide = True       # full-range lag search only right after reseeds
    w = 0
    skipped_cmds += int(wire_idx[0])

    # cmd cursor: index of the cmd whose post-state the sim currently holds.
    # A wire state that lags by last_d is really the server state after cmd
    # (i - last_d), so reseeding sets the cursor accordingly — otherwise every
    # reseed at a lagging checkpoint shifts the cmd window and cascades cuts.
    cursor = 0

    def hard_reseed(i):
        nonlocal hist_p, hist_v, cursor, last_d, search_wide
        reseed(i)
        hist_p = [rec_pos[i].copy()] + [None] * MAXLAG
        hist_v = [rec_vel[i].copy()] + [None] * MAXLAG
        if recent_d:
            last_d = int(np.median(recent_d[-15:]))
        cursor = i - last_d
        search_wide = True

    hard_reseed(wire_idx[0])
    seg_start = wire_idx[0]
    while w + 1 < len(wire_idx):
        i0, i1 = int(wire_idx[w]), int(wire_idx[w + 1])
        span = range(max(cursor + 1, i0 + 1 - MAXLAG), i1 + 1)
        bad = any(seqbrk[j] or msec[j] > 50 for j in span)
        if bad:
            if i0 + 1 - seg_start > 0:
                seg_lens.append(i0 + 1 - seg_start)
            skipped_cmds += len(span)
            hard_reseed(i1)
            seg_start = i1
            w += 1
            continue
        for j in span:
            step(j)
        cursor = i1
        # lag hysteresis: the ack lag drifts slowly (ping), so keep the last
        # accepted offset while it stays within thresholds; only re-search
        # when it fails. Prevents spurious offset jumps while nearly
        # stationary (states d apart then differ by < CUT_POS).
        def err_at(d):
            if hist_p[d] is None:
                return None
            return (float(np.max(np.abs(hist_p[d] - rec_pos[i1]))),
                    float(np.max(np.abs(hist_v[d] - rec_vel[i1]))))
        # Full-range lag search; among offsets that PASS the thresholds pick
        # the one closest to the previous lag (ack lag drifts slowly, so
        # continuity beats raw error when several offsets pass while the
        # player is slow). If none passes, take the raw best for reporting.
        best, best_pass = None, None
        for d in range(MAXLAG + 1):
            e = err_at(d)
            if e is None:
                continue
            if best is None or e < best[:2]:
                best = (e[0], e[1], d)
            if e[0] <= CUT_POS and e[1] <= CUT_VEL:
                key = (abs(d - last_d), d)
                if best_pass is None or key < best_pass[0]:
                    best_pass = (key, e[0], e[1], d)
        if best_pass is not None:
            _, pe, ve, d = best_pass
        elif best is not None:
            pe, ve, d = best
        else:
            pe, ve, d = float("inf"), float("inf"), last_d
        if pe > CUT_POS or ve > CUT_VEL:
            cause = classify(rec_pos[i0], rec_pos[i1],
                             waterlevel[i0], waterlevel[i1], pe, ve, len(span))
            cut_causes[cause] += 1
            clipped_cmds += len(span)
            if i0 + 1 - seg_start > 0:
                seg_lens.append(i0 + 1 - seg_start)
            hard_reseed(i1)
            seg_start = i1
        else:
            pos_errs.append(pe)
            vel_errs.append(ve)
            lag_hist[d] += 1
            last_d = d
            recent_d.append(d)
            if len(recent_d) > 64:
                del recent_d[:32]
            search_wide = False
            compared_wire += 1
            compared_cmds += len(span)
            # wire-encoding identity: MSG_WriteCoord is (int)(f*8), i.e. the
            # sim origin sent over the wire would be byte-identical to the
            # recorded coords; grid error measured in 1/8-u quanta.
            ge = float(np.max(np.abs(np.trunc(hist_p[d] * 8) - rec_pos[i1] * 8)))
            grid_errs.append(ge)
            if ge == 0.0:
                exact_grid += 1
        w += 1
    if wire_idx[-1] + 1 - seg_start > 0:
        seg_lens.append(int(wire_idx[-1] + 1 - seg_start))
    compared = compared_wire
    clipped = clipped_cmds
    skipped = skipped_cmds

    pos_errs = np.array(pos_errs)
    vel_errs = np.array(vel_errs)
    seg_lens = np.array(seg_lens) if seg_lens else np.array([0])
    return dict(
        demo_key=int(demo_key),
        cmd_ticks_total=int(n - 1),
        wire_checkpoints=int(len(wire_idx)),
        wire_compared=int(compared),
        cmd_ticks_compared=int(compared_cmds),
        cmd_ticks_clipped=int(clipped),
        cmd_ticks_skipped=int(skipped),
        clip_fraction=float(clipped / max(1, compared_cmds + clipped)),
        cut_causes=dict(cut_causes),
        ack_lag_hist=dict(lag_hist),
        pos_err_max=float(pos_errs.max()) if len(pos_errs) else None,
        pos_err_p99=float(np.percentile(pos_errs, 99)) if len(pos_errs) else None,
        pos_err_median=float(np.median(pos_errs)) if len(pos_errs) else None,
        pos_err_frac_le_eighth=float(np.mean(pos_errs <= 0.125)) if len(pos_errs) else None,
        pos_err_frac_le_quarter=float(np.mean(pos_errs <= 0.25)) if len(pos_errs) else None,
        vel_err_max=float(vel_errs.max()) if len(vel_errs) else None,
        vel_err_p99=float(np.percentile(vel_errs, 99)) if len(vel_errs) else None,
        wire_grid_exact_fraction=float(exact_grid / max(1, compared)),
        grid_err_p99_eighths=float(np.percentile(grid_errs, 99)) if len(grid_errs) else None,
        grid_err_max_eighths=float(np.max(grid_errs)) if len(grid_errs) else None,
        segments=int(len(seg_lens)),
        seg_len_median=float(np.median(seg_lens)),
        seg_len_max=int(seg_lens.max()),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=24)
    ap.add_argument("--probe", action="store_true",
                    help="alignment probe on one demo, no json")
    ap.add_argument("--ktjump-sweep", action="store_true")
    args = ap.parse_args()

    con = duckdb.connect()
    demos = con.execute(f"""
        select d.demo_key, d.movevars_id, count(*) n
        from read_parquet('{RT}') r join read_parquet('{DM}') d using(demo_key)
        where d.format='qwd' and d.map='dm3' and d.movevars_id in (49, 39)
        group by 1, 2 order by n desc limit {args.runs}
    """).fetchall()
    print(f"{len(demos)} runs selected", flush=True)

    qwsim.load_bsp(DM3_BSP)

    if args.probe:
        demo_key, mvid, n = demos[0]
        df = load_demo(con, demo_key)
        mv = movevars_for(con, mvid)
        for kt in ([0, 1] if args.ktjump_sweep else [1]):
            r = run_demo(demo_key, df, mv, kt)
            print(f"ktjump={kt}:", json.dumps(r, indent=1))
        return

    results = []
    totals = defaultdict(float)
    causes = Counter()
    all_pos_max = 0.0
    for demo_key, mvid, n in demos:
        df = load_demo(con, demo_key)
        mv = movevars_for(con, mvid)
        r = run_demo(demo_key, df, mv, ktjump=1)
        if r is None:
            continue
        results.append(r)
        totals["compared"] += r["cmd_ticks_compared"]
        totals["clipped"] += r["cmd_ticks_clipped"]
        totals["skipped"] += r["cmd_ticks_skipped"]
        totals["wire"] += r["wire_compared"]
        totals["exact"] += r["wire_grid_exact_fraction"] * r["wire_compared"]
        totals["le8"] += (r["pos_err_frac_le_eighth"] or 0) * r["wire_compared"]
        totals["le4"] += (r["pos_err_frac_le_quarter"] or 0) * r["wire_compared"]
        causes.update(r["cut_causes"])
        if r["pos_err_max"] is not None:
            all_pos_max = max(all_pos_max, r["pos_err_max"])
        print(f"demo {demo_key}: wire_cmp={r['wire_compared']} "
              f"cmds_cmp={r['cmd_ticks_compared']} "
              f"clipped={r['cmd_ticks_clipped']} ({100*r['clip_fraction']:.2f}%) "
              f"pos_max={r['pos_err_max']:.6g} p99={r['pos_err_p99']:.6g} "
              f"grid_exact={100*r['wire_grid_exact_fraction']:.1f}% "
              f"segmed={r['seg_len_median']}", flush=True)

    weighted_p99 = float(np.percentile(
        np.concatenate([[r["pos_err_p99"]] * r["wire_compared"] for r in results
                        if r["pos_err_p99"] is not None]), 99))
    out = dict(
        generated="2026-07-30",
        bsp=DM3_BSP,
        map_checksum2=f"{qwsim.load_bsp(DM3_BSP):08x}",
        selection=dict(format="qwd", map="dm3", movevars_ids=[49, 39],
                       runs=len(results)),
        thresholds=dict(cut_pos=CUT_POS, cut_vel=CUT_VEL),
        pm_vars_locked=dict(ktjump=1, bunnyspeedcap=0, slidefix=0, airstep=0,
                            pground=0, rampjump=0),
        ground_truth_note=(
            "wire_state_present ticks only; QW wire quantises origin to 1/8 u "
            "and velocity to 1 u/s, non-wire replay_ticks rows are the corpus "
            "parser's own reconstruction and are not used as truth"),
        totals=dict(
            wire_checkpoints_compared=int(totals["wire"]),
            cmd_ticks_compared=int(totals["compared"]),
            cmd_ticks_clipped=int(totals["clipped"]),
            cmd_ticks_skipped=int(totals["skipped"]),
            clip_fraction=float(totals["clipped"] /
                                max(1, totals["compared"] + totals["clipped"])),
            wire_grid_exact_fraction=float(totals["exact"] / max(1, totals["wire"])),
            pos_err_frac_le_eighth=float(totals["le8"] / max(1, totals["wire"])),
            pos_err_frac_le_quarter=float(totals["le4"] / max(1, totals["wire"])),
            cut_causes=dict(causes),
            pos_err_max_overall=all_pos_max,
            pos_err_p99_of_per_run_p99=weighted_p99,
        ),
        runs=results,
    )
    EVIDENCE.parent.mkdir(exist_ok=True)
    EVIDENCE.write_text(json.dumps(out, indent=1))
    print("wrote", EVIDENCE)
    print("TOTALS:", json.dumps(out["totals"], indent=1))


if __name__ == "__main__":
    main()
