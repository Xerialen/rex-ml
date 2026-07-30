#!/usr/bin/env python3
"""Rank every sweep setting against the regime-A baseline, on the same seven drills.

Two columns matter and they are reported side by side on purpose: seconds against the human's
recorded time, and ground actually covered. The baseline blames 71 % of the gap on distance, so a
setting that saves seconds without saving distance did something other than fix the routing — worth
seeing rather than averaging away.

Baseline medians come from 5 reps and sweep medians from 2, so a difference under roughly a second
is not evidence. The point of the sweep is to find a knob worth measuring properly, not to grade one.
"""

from __future__ import annotations

import json
import os
import statistics as st
import sys
from collections import defaultdict

SEL = [
    "sng-to-quad",
    "spawn-rarox-to-quad",
    "ssg-to-ratop",
    "ratop-to-ssg",
    "quad-to-sng",
    "sngspawns-to-sngmega",
    "ring-to-ratop",
]
GUARD = "sngspawns-to-sngmega"  # the one route the bot still wins; a knob that breaks it is not a win


def summarise(path: str) -> dict | None:
    try:
        d = json.load(open(path))["result"]
    except (OSError, KeyError, json.JSONDecodeError):
        return None
    marg, plen = defaultdict(list), defaultdict(list)
    fails = 0
    for r in d["drills"]:
        k = r["id"].rsplit("-r", 1)[0]
        if k not in SEL:
            continue
        if "margin_secs" in r:
            marg[k].append(r["margin_secs"])
        if "metrics" in r and r["outcome"].startswith("arrived"):
            plen[k].append(r["metrics"]["path_len"])
        if not r["outcome"].startswith("arrived"):
            fails += 1
    if not marg:
        return None
    return {
        "secs": {k: st.median(v) for k, v in marg.items()},
        "path": {k: st.median(v) for k, v in plen.items()},
        "total_secs": sum(st.median(v) for v in marg.values()),
        "total_path": sum(st.median(v) for v in plen.values()),
        "fails": fails,
        "n_drills": len(marg),
    }


def main() -> None:
    base = summarise("evidence/t1_norj_baseline.raw.json")
    if base is None:
        sys.exit("no baseline envelope")
    outdir = sys.argv[1] if len(sys.argv) > 1 else "evidence/sweep"
    rows = []
    for f in sorted(os.listdir(outdir)):
        if not f.endswith(".raw.json"):
            continue
        s = summarise(os.path.join(outdir, f))
        if s:
            rows.append((f[: -len(".raw.json")], s))
    rows.sort(key=lambda r: -r[1]["total_secs"])

    # Compare each setting to the baseline restricted to the drills that setting actually finished.
    # Otherwise a knob that makes the worst drill fail outright drops its -14 s from the total and
    # ranks first for having broken the bot.
    for _, s in rows:
        common = [k for k in s["secs"] if k in base["secs"]]
        s["d_secs"] = s["total_secs"] - sum(base["secs"][k] for k in common)
        s["d_path"] = s["total_path"] - sum(base["path"][k] for k in common if k in base["path"])
    rows.sort(key=lambda r: -r[1]["d_secs"])

    print(f"{'setting':26} {'margin':>8} {'vs base':>8} {'path Δ':>8} {'guard':>7} {'fails':>6}  drills")
    print(f"{'BASELINE (5 reps)':26} {base['total_secs']:8.1f} {'':>8} {'':>8} "
          f"{base['secs'][GUARD]:+7.2f} {base['fails']:6d}  {base['n_drills']}/{len(SEL)}")
    for name, s in rows:
        g = s["secs"].get(GUARD)
        gs = f"{g:+7.2f}" if g is not None else f"{'--':>7}"
        print(f"{name:26} {s['total_secs']:8.1f} {s['d_secs']:+8.1f} {s['d_path']:+8.0f} "
              f"{gs} {s['fails']:6d}  {s['n_drills']}/{len(SEL)}")

    better = [r for r in rows if r[1]["d_secs"] > 1.0]
    print()
    if better:
        print("worth measuring properly (>1 s better than baseline):")
        for name, s in better:
            print(f"  {name}: {s['d_secs']:+.1f}s, path {s['d_path']:+.0f}u")
    else:
        print("No setting beats the baseline by more than 1 s. On this evidence the existing")
        print("controller cannot be tuned to the human's times with the knobs it exposes.")


if __name__ == "__main__":
    main()
