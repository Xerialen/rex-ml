#!/usr/bin/env python3
"""Lay the bot's trajectory next to the recorder's for one drill.

The open question this exists for: the bot covers well over the human's distance, and the summary
metrics cannot say whether that is a *different route* or the *same route travelled badly*. Two
proxies were tried and both were the wrong instrument — `planned_path_len` turned out to be the
bot's current, possibly window-bounded route rather than a plan to the goal (it came out shorter
than the straight line on 10 of 15 drills), and `reverse_frames` is measured against the straight
chord, so every legitimate climb scores high on it (`ralow-to-ratop`: 42 % reverse while matching
the human's distance to within 1 %). This compares the paths themselves.

The human side comes from the owner's own `dm3-drillar-routes.json`, so the run boundaries are his
definition, not a second guess at them.

usage: compare_path.py <evidence.json> <drill-id> [near_u]
"""

from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
from pathlib import Path

DEMOS = Path(__file__).resolve().parent.parent / "demos" / "dm3-drillar"
ROUTES = DEMOS / "dm3-drillar-routes.json"
DUMP = Path.home() / "qwd-corpus" / "qwd_dump.py"
# A teleporter hop is not distance travelled; same threshold as `corridor_metrics`' `path_len`.
HOP = 300.0


def human_path(drill_id: str) -> tuple[list[list[float]], float]:
    src = json.load(open(ROUTES))
    dm = next((d for d in src["demos"] if d["route"] == drill_id), None)
    if dm is None:
        sys.exit(f"{drill_id} is not in {ROUTES.name}")
    run = dm["fastest"]
    t = dm["target"]
    t0 = run.get("start_time_s")
    if t0 is None:  # `fastest` is a digest; fall back to the full run record
        t0 = dm["runs"][0]["start_time_s"]
    t1 = t0 + (t["reach_time_s"] if t.get("reach_time_s") else run["travel_time_s"])
    out = subprocess.run(
        [sys.executable, str(DUMP), str(DEMOS / dm["demo"])], capture_output=True, text=True, check=True
    ).stdout
    pts = []
    for r in csv.DictReader(out.splitlines()):
        try:
            ts = float(r["time"])
            p = [float(r["x"]), float(r["y"]), float(r["z"])]
        except (ValueError, KeyError):
            continue
        pts.append((ts, p))
    if not pts:
        sys.exit("no samples parsed")
    # Demo time is absolute; the route file's times are relative to the first playerinfo sample.
    base = pts[0][0]
    return [p for ts, p in pts if t0 <= ts - base <= t1], t1 - t0


def bot_path(evidence: str, drill_id: str) -> list[list[float]]:
    d = json.load(open(evidence))["result"]
    for r in d["drills"]:
        if r["id"].rsplit("-r", 1)[0] == drill_id and "traj" in r:
            return [[s[1], s[2], s[3]] for s in r["traj"]]
    sys.exit(f'no dumped trajectory for {drill_id} in {evidence} (set "dump_traj": true)')


def path_len(p: list[list[float]]) -> float:
    return sum(d for d in (math.dist(p[i], p[i - 1]) for i in range(1, len(p))) if d < HOP)


def near_any(p: list[float], path: list[list[float]], near: float) -> bool:
    for q in path:
        if abs(p[0] - q[0]) <= near and abs(p[1] - q[1]) <= near and math.dist(p, q) <= near:
            return True
    return False


def plot(hp: list[list[float]], bp: list[list[float]], w: int = 78, h: int = 22) -> str:
    pts = hp + bp
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0 = min(xs), min(ys)
    s = min((w - 1) / max(1.0, max(xs) - x0), (h - 1) / max(1.0, max(ys) - y0))
    grid = [[" "] * w for _ in range(h)]
    for path, ch in ((bp, "b"), (hp, "H")):
        for p in path:
            cx, cy = int((p[0] - x0) * s), h - 1 - int((p[1] - y0) * s)
            if 0 <= cx < w and 0 <= cy < h:
                grid[cy][cx] = "#" if grid[cy][cx] not in (" ", ch) else ch
    return "\n".join("".join(r) for r in grid)


def main() -> None:
    ev, drill = sys.argv[1], sys.argv[2]
    near = float(sys.argv[3]) if len(sys.argv) > 3 else 96.0
    hp, hsecs = human_path(drill)
    bp = bot_path(ev, drill)
    hl, bl = path_len(hp), path_len(bp)
    on = sum(near_any(p, hp, near) for p in bp) / max(1, len(bp))
    cov = sum(near_any(p, bp, near) for p in hp) / max(1, len(hp))
    print(f"{drill}: human {hl:.0f}u in {hsecs:.2f}s ({len(hp)} samples), bot {bl:.0f}u ({len(bp)} samples), "
          f"detour {bl/max(hl,1):.2f}x")
    print(f"  bot samples within {near:.0f}u of the human's path : {100*on:5.1f}%")
    print(f"  human samples the bot ever came within {near:.0f}u of: {100*cov:5.1f}%")
    run = 0
    for i, p in enumerate(bp):
        if not near_any(p, hp, near):
            run += 1
            if run >= 10:
                q = bp[i - 9]
                print(f"  first sustained divergence at sample {i-9}: [{q[0]:.0f} {q[1]:.0f} {q[2]:.0f}]")
                break
        else:
            run = 0
    else:
        print("  no sustained divergence — the bot stays in the human's corridor throughout")
    print()
    print("Reading: high overlap with a large detour means the same corridor travelled badly")
    print("(back-and-forth, overshoot). Low overlap means a different route entirely.")
    print(f"\ntop-down (H = human, b = bot, # = both):\n{plot(hp, bp)}")


if __name__ == "__main__":
    main()
