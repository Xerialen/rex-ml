"""Diagnostic: what actually distinguishes a self rocket jump from any other impulse?

`fire_edge` alone gives ~1.9x lift over a shifted-fire null (validate_sample),
which is far too weak to label with. This script measures candidate
discriminators on real data so the classifier is set from evidence:

  * latency to the last attack edge vs to the last attack-held tick
    (a held rocket launcher fires every 0.8 s but produces one rising edge)
  * blast direction in the body frame -- a self blast pushes you up and away
    from where you are aiming; an enemy rocket arrives from an arbitrary angle
  * view pitch at fire time -- you look down to rocket jump

Usage: .venv/bin/python -m pipeline.analyze_rocket [--demos 25]
"""

from __future__ import annotations

import argparse

import numpy as np

from . import config as C
from . import io_store, se2, segment


def last_true_distance(flag: np.ndarray, chunk: np.ndarray) -> np.ndarray:
    """Ticks since `flag` was last True, within the same chunk. 1e6 if never."""
    n = len(flag)
    idx = np.where(flag, np.arange(n), -1)
    np.maximum.accumulate(idx, out=idx)
    ok = (idx >= 0) & (chunk[np.maximum(idx, 0)] == chunk)
    return np.where(ok, np.arange(n) - idx, 10 ** 6)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--demos", type=int, default=25)
    args = ap.parse_args(argv)

    con = io_store.connect()
    keys = io_store.demo_keys(con, limit=args.demos)
    a = io_store.to_arrays(io_store.load_ticks(con, keys))
    f = se2.transform(a)
    r = segment.segment(f)
    ev, state = r["events"], r["state"]
    n = len(f["cmd_ordinal"])
    br = segment.chunk_breaks(f)
    chunk = np.cumsum(br) - 1
    mins = float(f["dt"].sum()) / 60.0

    print(f"{n:,} ticks, {len(keys)} demos, {mins:.1f} min of play\n")

    big = ev["impulse"] & (ev["impulse_mag"] >= C.THRESHOLDS.rocket_impulse_min)
    print(f"impulses >= {C.THRESHOLDS.rocket_impulse_min:.0f} u/s while airborne: "
          f"{int(big.sum()):,}  ({big.sum()/mins:.1f}/min)\n")

    # ---- 1. edge vs held ------------------------------------------------
    d_edge = last_true_distance(ev["fire_edge"], chunk)
    d_held = last_true_distance(f["attack"], chunk)
    print("--- ticks since last attack, at big impulses vs at all air ticks ---")
    air = state == segment.AIR
    print(f"{'window':>10} | {'edge@impulse':>13} | {'edge@air':>10} | {'lift':>5} | "
          f"{'held@impulse':>13} | {'held@air':>10} | {'lift':>5}")
    for lo, hi in [(0, 1), (0, 3), (0, 7), (0, 15), (16, 40)]:
        me = ((d_edge >= lo) & (d_edge <= hi))
        mh = ((d_held >= lo) & (d_held <= hi))
        pe_i, pe_a = me[big].mean() * 100, me[air].mean() * 100
        ph_i, ph_a = mh[big].mean() * 100, mh[air].mean() * 100
        print(f"{lo:>4}-{hi:<5} | {pe_i:12.1f}% | {pe_a:9.1f}% | {pe_i/max(pe_a,1e-9):5.2f} | "
              f"{ph_i:12.1f}% | {ph_a:9.1f}% | {ph_i/max(ph_a,1e-9):5.2f}")

    # ---- 2. blast direction in the body frame ---------------------------
    print("\n--- blast direction at big impulses, body frame ---")
    dvf = np.nan_to_num(f["dv_fwd"], nan=0.0)
    dvr = np.nan_to_num(f["dv_right"], nan=0.0)
    dvv = np.nan_to_num(f["grav_res"], nan=0.0)   # vertical, gravity removed
    mag = np.sqrt(dvf ** 2 + dvr ** 2 + dvv ** 2) + 1e-9
    up = dvv / mag                       # +1 = pure upward blast
    fwd = dvf / mag                      # -1 = pushed straight backwards
    pitch = f["pitch_deg"]               # + = looking down in Quake's convention

    near = d_edge <= 7
    groups = [("big impulse, fire <=7 ticks ago", big & near),
              ("big impulse, no recent fire", big & ~near),
              ("all airborne ticks", air)]
    print(f"{'group':>34} | {'n':>7} | {'up>0.5':>7} | {'up>0.8':>7} | "
          f"{'fwd<-0.3':>8} | {'up>.5&look-down':>15} | {'med pitch':>9}")
    for name, m in groups:
        if not m.any():
            continue
        print(f"{name:>34} | {int(m.sum()):7,} | {up[m].mean()*0+np.mean(up[m]>0.5)*100:6.1f}% | "
              f"{np.mean(up[m]>0.8)*100:6.1f}% | {np.mean(fwd[m]<-0.3)*100:7.1f}% | "
              f"{np.mean((up[m]>0.5)&(pitch[m]>10))*100:14.1f}% | {np.median(pitch[m]):8.1f}")

    # ---- 3. joint test: the classifier candidate ------------------------
    print("\n--- candidate rule: big impulse AND up>0.5 AND fire<=W AND pitch>P ---")
    print(f"{'W':>3} {'P':>5} | {'n selected':>11} | {'per min':>8} | "
          f"{'null (fire shifted)':>19} | {'lift':>6}")
    shifted = _shift_fire(ev["fire_edge"], br, 499)
    d_edge_null = last_true_distance(shifted, chunk)
    for W in (3, 7, 12):
        for P in (0.0, 10.0, 20.0):
            sel = big & (up > 0.5) & (d_edge <= W) & (pitch > P)
            nul = big & (up > 0.5) & (d_edge_null <= W) & (pitch > P)
            lift = sel.sum() / max(nul.sum(), 1e-9)
            print(f"{W:>3} {P:>5.0f} | {int(sel.sum()):11,} | {sel.sum()/mins:8.2f} | "
                  f"{int(nul.sum()):19,} | {lift:6.2f}")

    # ---- 4. what do the selected events look like? ----------------------
    sel = big & (up > 0.5) & (d_edge <= 7) & (pitch > 10.0)
    if sel.any():
        print(f"\n--- {int(sel.sum()):,} events selected by (W=7, P=10) ---")
        for nm, arr in (("impulse magnitude (u/s)", ev["impulse_mag"][sel]),
                        ("vertical component (u/s)", dvv[sel]),
                        ("view pitch (deg, + = down)", pitch[sel]),
                        ("speed before (u/s)", f["speed_xy"][sel])):
            p = np.percentile(arr, [10, 50, 90])
            print(f"  {nm:<28} p10 {p[0]:8.1f}  p50 {p[1]:8.1f}  p90 {p[2]:8.1f}")


def _shift_fire(fire_edge, br, shift):
    n = len(fire_edge)
    out = np.zeros(n, bool)
    s, e, _ = segment.runs_of(np.zeros(n, np.int8), br)
    for x, y in zip(s, e):
        if y - x > 1:
            out[x:y] = np.roll(fire_edge[x:y], shift % (y - x))
    return out


if __name__ == "__main__":
    main()
