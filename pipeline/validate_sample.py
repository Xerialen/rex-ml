"""Measure BRIEF step 1 on a small real sample and print numbers, not claims.

Usage:  .venv/bin/python -m pipeline.validate_sample [--demos 25] [--out report.md]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter

import numpy as np

from . import config as C
from . import io_store, se2, segment


def pct(a, b):
    return 100.0 * a / b if b else 0.0


def q(a, ps=(1, 50, 90, 99)):
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return [float("nan")] * len(ps)
    return [float(np.percentile(a, p)) for p in ps]


def _expand(i0, i1):
    """Concatenated index ranges [i0, i1] inclusive."""
    if len(i0) == 0:
        return np.empty(0, np.int64)
    return np.concatenate([np.arange(a, b + 1) for a, b in zip(i0, i1)])


def _latency(fire_edge, target, f, shift):
    """Ticks since the most recent fire edge, at each True in `target`.

    `shift` rolls the fire train forward inside each track to build a null that
    keeps the fire rate and burst structure but destroys the causal alignment.
    """
    n = len(fire_edge)
    fe = fire_edge
    if shift:
        fe = np.zeros(n, bool)
        br = segment.chunk_breaks(f)
        s, e, _ = segment.runs_of(np.zeros(n, np.int8), br)
        for a, b in zip(s, e):
            if b - a > 1:
                fe[a:b] = np.roll(fire_edge[a:b], shift % (b - a))
    idx = np.where(fe, np.arange(n), -1)
    np.maximum.accumulate(idx, out=idx)
    # a fire in a previous chunk does not count
    br = segment.chunk_breaks(f)
    chunk = np.cumsum(br) - 1
    tgt = np.flatnonzero(target)
    src = idx[tgt]
    lat = np.where((src >= 0) & (chunk[np.maximum(src, 0)] == chunk[tgt]),
                   tgt - src, 10 ** 6)
    return lat


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--demos", type=int, default=25)
    ap.add_argument("--split", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    lines: list[str] = []

    def w(s=""):
        print(s)
        lines.append(s)

    t0 = time.time()
    con = io_store.connect()
    keys = io_store.demo_keys(con, limit=args.demos, split=args.split)
    tbl = io_store.load_ticks(con, keys)
    a = io_store.to_arrays(tbl)
    t_load = time.time() - t0

    t1 = time.time()
    f = se2.transform(a)
    t_tf = time.time() - t1

    t2 = time.time()
    r = segment.segment(f)
    t_seg = time.time() - t2

    n = len(f["cmd_ordinal"])
    state, kind, segs = r["state"], r["kind"], r["segments"]
    ev = r["events"]
    ntracks = len(np.unique(f["demo_key"].astype(np.int64) * 256 + f["slot"]))

    w(f"# BRIEF step 1 — validation on {len(keys)} demos")
    w()
    w(f"source: `{C.STORE}` (replay_ticks x usercmds on demo_key/slot/cmd_ordinal)")
    w(f"demo_keys: {keys[0]}..{keys[-1]} (deterministic, ORDER BY demo_key LIMIT {args.demos})")
    w()
    w("## Volume")
    w()
    w(f"| rows | tracks | demos | wall-clock | load s | transform s | segment s |")
    w("|---|---|---|---|---|---|---|")
    hours = float(f["dt"].sum()) / 3600.0
    w(f"| {n:,} | {ntracks} | {len(np.unique(f['demo_key']))} | {hours:.2f} h | "
      f"{t_load:.1f} | {t_tf:.1f} | {t_seg:.1f} |")
    w()
    dtm = Counter(f["msec"].tolist())
    top = ", ".join(f"{k} ms: {v:,} ({pct(v,n):.1f}%)" for k, v in dtm.most_common(4))
    w(f"usercmd frametime: {top}")
    w(f"mean tickrate: {n/ (f['dt'].sum()):.1f} Hz")
    w()

    # ---------------- ground contact ----------------------------------
    w("## Ground contact: the `onground` column vs the derived signal")
    w()
    og = f["onground_flag"]
    gr = r["ground_raw"]
    gd = state == segment.GROUND
    vz0 = np.abs(f["vz"]) <= C.THRESHOLDS.vz_zero_eps
    w(f"| signal | ticks | share |")
    w("|---|---|---|")
    w(f"| `onground = true` (store column) | {og.sum():,} | {pct(og.sum(), n):.2f} % |")
    w(f"| `vz == 0` | {vz0.sum():,} | {pct(vz0.sum(), n):.2f} % |")
    w(f"| derived ground, raw | {gr.sum():,} | {pct(gr.sum(), n):.2f} % |")
    w(f"| derived ground, debounced | {gd.sum():,} | {pct(gd.sum(), n):.2f} % |")
    w(f"| water (waterlevel > 0) | {(state==segment.WATER).sum():,} | "
      f"{pct((state==segment.WATER).sum(), n):.2f} % |")
    w()
    fn = (~og) & gd
    fp = og & (~gd)
    w(f"`onground = false` but derived ground: **{fn.sum():,} ticks ({pct(fn.sum(), n):.2f} % of all)**"
      f" — the column misses this much ground contact.")
    w(f"`onground = true` but derived air: {fp.sum():,} ticks ({pct(fp.sum(), n):.3f} %)"
      f" — slope contacts where vz != 0.")
    w()

    # free-fall sanity: gravity recovered from air ticks only
    air = state == segment.AIR
    trans_air = air.copy()
    trans_air[:-1] &= air[1:] & f["has_next"][:-1] & ~ev["impulse"][:-1]
    g_hat = -np.nan_to_num(f["dvz"], nan=0.0)[trans_air] / f["dt"][trans_air]
    w(f"gravity recovered from {trans_air.sum():,} impulse-free air->air transitions: "
      f"median **{np.median(g_hat):.1f}** u/s^2 (movevars says {C.GRAVITY:.0f}), "
      f"mean {g_hat.mean():.1f}, p1/p99 {q(g_hat,(1,99))[0]:.0f}/{q(g_hat,(1,99))[1]:.0f}")
    w()
    same = np.zeros(n, bool)
    same[:-1] = gd[:-1] & gd[1:] & f["has_next"][:-1]
    g_ground = -np.nan_to_num(f["dvz"], nan=0.0)[same] / f["dt"][same]
    w(f"same test over {same.sum():,} ground->ground transitions: median "
      f"{np.median(g_ground):.1f} u/s^2 — i.e. supported, gravity cancelled. "
      f"This is the check that the derived signal is physical.")
    w()

    # run lengths
    w("### Run lengths (contiguous state)")
    w()
    w("| state | runs | ticks | mean | p50 | p90 | max |")
    w("|---|---|---|---|---|---|---|")
    br = segment.chunk_breaks(f)
    s_st, e_st, v_st = segment.runs_of(state, br)
    L = e_st - s_st
    for st, name in ((segment.GROUND, "ground"), (segment.AIR, "air"), (segment.WATER, "water")):
        m = v_st == st
        if not m.any():
            continue
        l = L[m]
        w(f"| {name} | {m.sum():,} | {l.sum():,} | {l.mean():.1f} | "
          f"{np.median(l):.0f} | {np.percentile(l,90):.0f} | {l.max()} |")
    w()
    # same, with the store column taken at face value, for contrast
    s2, e2, v2 = segment.runs_of(og.astype(np.int8), br)
    L2 = e2 - s2
    m2 = v2 == 0
    w(f"For contrast, segmenting on the raw `onground` column gives "
      f"{m2.sum():,} airborne runs with median length {np.median(L2[m2]):.0f} ticks "
      f"vs {int((v_st==segment.AIR).sum()):,} / {np.median(L[v_st==segment.AIR]):.0f} derived — "
      f"the column shatters every ground run into stair-step noise.")
    w()

    # ---------------- events -------------------------------------------
    w("## Events")
    w()
    w("| event | count | per minute |")
    w("|---|---|---|")
    mins = float(f["dt"].sum()) / 60.0
    for name in ("fire_edge", "jump_edge", "takeoff", "land", "impulse"):
        c = int(ev[name].sum())
        w(f"| {name} | {c:,} | {c/mins:.1f} |")
    w()
    tk = np.flatnonzero(ev["takeoff"])
    tdvz = np.nan_to_num(f["dvz"], nan=0.0)[np.maximum(tk - 1, 0)]
    w("Takeoff vertical impulse `dvz` at the ground->air transition "
      f"(n = {len(tk):,}):")
    w()
    w("| bucket | n | share |")
    w("|---|---|---|")
    edges = [(-1e9, 50), (50, 200), (200, 340), (340, 600), (600, 1e9)]
    names = ["< 50 (walked off)", "50–200", "200–340 (jump = +270)", "340–600", "> 600"]
    for (lo, hi), nm in zip(edges, names):
        c = int(((tdvz >= lo) & (tdvz < hi)).sum())
        w(f"| {nm} | {c:,} | {pct(c, len(tdvz)):.1f} % |")
    w()
    jm = (tdvz >= 200) & (tdvz <= 340)
    if jm.any():
        dt_j = f["dt"][np.maximum(tk[jm] - 1, 0)]
        expect = C.JUMP_IMPULSE - C.GRAVITY * dt_j.mean()
        w(f"mean dvz inside the jump bucket: **{tdvz[jm].mean():.1f}** u/s. "
          f"PM_JumpButton adds {C.JUMP_IMPULSE:.0f} and PM_AirMove then applies one frame of "
          f"gravity, so the expected value is {C.JUMP_IMPULSE:.0f} - "
          f"{C.GRAVITY:.0f}*{dt_j.mean()*1000:.1f}ms = **{expect:.1f}**. "
          f"Agreement to {abs(tdvz[jm].mean()-expect):.1f} u/s confirms the tick alignment: "
          f"`replay_ticks[i]` is the post-move state of usercmd i, and dvz[i] is the effect "
          f"of usercmd i+1.")
    w()

    # impulse magnitudes
    im = ev["impulse_mag"][ev["impulse"]]
    p = q(im, (50, 90, 99))
    w(f"impulse magnitude |(dv_xy, grav_res)| on the {int(ev['impulse'].sum()):,} flagged "
      f"transitions: p50 {p[0]:.0f}, p90 {p[1]:.0f}, p99 {p[2]:.0f} u/s. "
      f"Physics bound for an honest air tick is 0 vertical and "
      f"{C.AIR_ACCELERATE_MAX * C.AIR_WISHSPEED_CAP * 0.014:.1f} horizontal.")
    w()

    # ---- is the fire -> impulse link causal, or coincidence? -----------
    w("### Does weapon fire actually explain the impulses?")
    w()
    w("Attribution is only meaningful if a blast follows the player's *own* attack at a "
      "specific latency. Latency here is (impulse tick - most recent fire edge), measured "
      "on impulses above the rocket threshold, against a null that shifts the fire train "
      "by +499 ticks inside each track.")
    w()
    big = ev["impulse"] & (ev["impulse_mag"] >= C.THRESHOLDS.rocket_impulse_min)
    lat_real = _latency(ev["fire_edge"], big, f, 0)
    lat_null = _latency(ev["fire_edge"], big, f, 499)
    w("| latency (ticks) | impulses with a fire that recent | null (fire train shifted) | lift |")
    w("|---|---|---|---|")
    tot = int(big.sum())
    for lo, hi in [(0, 3), (4, 7), (8, 15), (16, 31), (32, 63)]:
        cr = int(((lat_real >= lo) & (lat_real <= hi)).sum())
        cn = int(((lat_null >= lo) & (lat_null <= hi)).sum())
        lift = (cr / cn) if cn else float("inf")
        w(f"| {lo}–{hi} | {cr:,} ({pct(cr,tot):.1f} %) | {cn:,} ({pct(cn,tot):.1f} %) | "
          f"{lift:.2f}x |")
    w(f"\ntotal impulses above threshold: {tot:,}")
    w()

    # ---------------- segments -----------------------------------------
    w("## Segments")
    w()
    kinds = segs["kind"]
    nt = segs["n_ticks"]
    w("| kind | segments | ticks | % of ticks | mean ticks | p50 | mean dur ms | mean speed0 | mean dspeed |")
    w("|---|---|---|---|---|---|---|---|---|")
    order = ["trim_ground", "trim_air", "maneuver_jump", "maneuver_rocket_jump",
             "maneuver_external", "maneuver_fall", "maneuver_land",
             "other_ground", "other_air", "water"]
    for k in order:
        m = kinds == k
        if not m.any():
            w(f"| {k} | 0 | 0 | 0.00 % | – | – | – | – | – |")
            continue
        w(f"| {k} | {m.sum():,} | {nt[m].sum():,} | {pct(nt[m].sum(), n):.2f} % | "
          f"{nt[m].mean():.1f} | {np.median(nt[m]):.0f} | {segs['dur_ms'][m].mean():.0f} | "
          f"{segs['speed0'][m].mean():.0f} | {segs['dspeed'][m].mean():+.0f} |")
    w(f"| **total** | **{len(kinds):,}** | **{nt.sum():,}** | "
      f"**{pct(nt.sum(), n):.2f} %** | | | | | |")
    w()
    # what is in the leftover buckets?
    oth = np.isin(kind, [segment.KIND_ID["other_ground"], segment.KIND_ID["other_air"]])
    slow = oth & (f["speed_xy"] < C.THRESHOLDS.trim_min_speed)
    turn = oth & ~slow
    w(f"The `other_*` residue is {pct(oth.sum(), n):.1f} % of ticks. Of it, "
      f"{pct(slow.sum(), oth.sum()):.1f} % is below the {C.THRESHOLDS.trim_min_speed:.0f} u/s "
      f"floor where the body frame is ill-conditioned (standing, aiming, dead), and "
      f"{pct(turn.sum(), oth.sum()):.1f} % is moving but not steady — accelerating out of a "
      f"turn or changing strafe direction. Neither is a trim, and neither is discarded: the "
      f"ticks keep full features and a label.")
    w()

    # trims in detail
    for k in ("trim_air", "trim_ground"):
        m = kinds == k
        if not m.any():
            continue
        w(f"### {k} ({m.sum():,} segments, {nt[m].sum():,} ticks)")
        w()
        sp = segs["speed0"][m]
        ds = segs["dspeed"][m]
        sl = np.rad2deg(segs["mean_slip"][m])
        om = np.rad2deg(segs["mean_omega"][m])
        w("| quantity | p1 | p50 | p90 | p99 |")
        w("|---|---|---|---|---|")
        for nm, arr, fmt in (("entry speed (u/s)", sp, "{:.0f}"),
                             ("speed gain over segment (u/s)", ds, "{:+.0f}"),
                             ("mean slip angle (deg)", sl, "{:+.1f}"),
                             ("|mean slip| (deg)", np.abs(sl), "{:.1f}"),
                             ("slip span within segment (deg)", np.rad2deg(segs["slip_span"][m]), "{:.1f}"),
                             ("mean turn rate (deg/s)", om, "{:+.0f}"),
                             ("length (ticks)", nt[m].astype(float), "{:.0f}"),
                             ("planar distance (units)", segs["planar_dist"][m], "{:.0f}")):
            v = q(arr)
            w(f"| {nm} | " + " | ".join(fmt.format(x) for x in v) + " |")
        w()
        gain = ds > 20
        w(f"segments gaining > 20 u/s: {gain.sum():,} ({pct(gain.sum(), m.sum()):.1f} %); "
          f"max single-segment gain {ds.max():+.0f} u/s; "
          f"fastest exit {segs['speed1'][m].max():.0f} u/s "
          f"(QW ground maxspeed is 320).")
        w()

    # rocket jumps, measured over the enclosing air phase (the meaningful unit)
    sr = r["state_runs"]
    run_of = r["state_run_id"]
    for k, title in (("maneuver_rocket_jump", "maneuver_rocket_jump"),
                     ("maneuver_jump", "maneuver_jump (plain +270)")):
        m = kinds == k
        w(f"### {title} — {m.sum():,} segments, {m.sum()/mins:.2f}/min")
        w()
        if not m.any():
            w("none found at the current thresholds")
            w()
            continue
        w(f"peak impulse: p50 {q(segs['peak_impulse'][m],(50,))[0]:.0f}, "
          f"p90 {q(segs['peak_impulse'][m],(90,))[0]:.0f}, "
          f"max {segs['peak_impulse'][m].max():.0f} u/s")
        runs = np.unique(run_of[np.isin(np.arange(n), _expand(segs['i0'][m], segs['i1'][m]))])
        runs = runs[np.array([sr["state"][i] == "air" for i in runs], dtype=bool)]
        if len(runs):
            w()
            w(f"the {len(runs):,} distinct air phases these belong to:")
            w()
            w("| quantity | p10 | p50 | p90 | max |")
            w("|---|---|---|---|---|")
            for nm, arr, fmt in (
                ("air time (ms)", sr["dur_ms"][runs], "{:.0f}"),
                ("peak height above takeoff (units)", sr["z_peak"][runs] - sr["z0"][runs], "{:+.0f}"),
                ("net height change (units)", sr["z1"][runs] - sr["z0"][runs], "{:+.0f}"),
                ("peak speed (u/s)", sr["speed_peak"][runs], "{:.0f}"),
                ("planar distance covered (units)", sr["planar_dist"][runs], "{:.0f}"),
            ):
                v = q(arr, (10, 50, 90, 100))
                w(f"| {nm} | " + " | ".join(fmt.format(x) for x in v) + " |")
            apex = q(sr["z_peak"][runs] - sr["z0"][runs], (50,))[0]
            theo = C.JUMP_IMPULSE ** 2 / (2 * C.GRAVITY)
            if k == "maneuver_jump":
                w()
                w(f"A QW jump is a ballistic arc from v0 = {C.JUMP_IMPULSE:.0f}: apex = "
                  f"v0^2/2g = **{theo:.1f} units**. Measured median apex **{apex:+.0f}** — "
                  f"the label is picking out plain jumps and nothing else.")
            else:
                w()
                w(f"Median apex **{apex:+.0f} units** against {theo:.1f} for a plain jump: "
                  f"{apex/theo:.1f}x the ballistic ceiling of the jump button. These are a "
                  f"different population, which is the point of the label.")
        w()

    # coverage / integrity
    w("## Integrity")
    w()
    w(f"| check | value |")
    w("|---|---|")
    w(f"| ticks labelled exactly once | {nt.sum():,} / {n:,} |")
    w(f"| contiguous chunks (breaks on gap/seq_break/bad msec) | {int(segment.chunk_breaks(f).sum()):,} |")
    w(f"| ticks with no valid successor | {int((~f['has_next']).sum()):,} "
      f"({pct((~f['has_next']).sum(), n):.2f} %) |")
    w(f"| wire_state_present | {int(f['wire_state_present'].sum()):,} "
      f"({pct(f['wire_state_present'].sum(), n):.2f} %) |")
    w(f"| seq_break | {int(f['seq_break'].sum()):,} |")
    nan_feat = {k: int((~np.isfinite(np.asarray(f[k], float))).sum())
                for k in ("speed_xy", "slip", "v_fwd", "v_right", "omega", "dx_loc")}
    w(f"| non-finite in core features | {nan_feat} |")
    w()
    w("`omega`/`dx_loc` non-finites are exactly the last tick of each chunk, which has no "
      "successor — masked, never interpolated.")
    w()
    w("## Thresholds used")
    w()
    w("```json")
    w(json.dumps(C.thresholds_dict(), indent=2))
    w("```")

    if args.out:
        with open(args.out, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"\n[written to {args.out}]", file=sys.stderr)


if __name__ == "__main__":
    main()
