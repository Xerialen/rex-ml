#!/usr/bin/env python3
"""Turn the hand-recorded dm3 drill demos into timed start->goal runs.

Each `.qwd` holds one or more attempts at the same drill: the recorder spawns (or `kill`s back
to a spawn), runs to a named item, and repeats. A respawn shows up as a position discontinuity
far larger than any single frame's travel, so that is what splits the file into runs.

A run's *time* is what the loop is graded against, so it is defined narrowly: from the last
frame the player is still stationary at the start to the first frame within ARRIVE units of the
goal. Standing around before moving is not part of the route time.

Endpoints are reported as the nearest name in ~/route-sheet-search/routes.json, so a demo's
own filename is never trusted over its coordinates.
"""

from __future__ import annotations

import csv
import json
import math
import os
import subprocess
import sys

DUMP = os.path.expanduser("~/qwd-corpus/qwd_dump.py")
ROUTES = os.path.expanduser("~/route-sheet-search/routes.json")

# A respawn/teleport moves the player further in one frame than any physics can.
SPLIT_DIST = 300.0
# Arrival radius. Item pickup happens on touch, and the recorded origin is the eye position, so
# this is deliberately generous — the drill runner's own arrival test is 24 xy / 48 z.
ARRIVE = 64.0
# Below this speed the player is treated as not yet under way.
MOVING = 20.0
MIN_RUN_SECS = 0.7


def named_points() -> dict[str, list[float]]:
    pts: dict[str, list[float]] = {}
    for r in json.load(open(ROUTES)):
        pts.setdefault(r["from"], r["from_xyz"])
        pts.setdefault(r["to"], r["to_xyz"])
    pts.update(EXTRA_POINTS)
    return pts


def nearest(pts: dict[str, list[float]], p: list[float]) -> tuple[str, float]:
    best, bd = "?", 1e18
    for k, q in pts.items():
        d = math.dist(p, q)
        if d < bd:
            best, bd = k, d
    return best, bd


def rows_for(path: str) -> list[dict]:
    out = subprocess.run(
        [sys.executable, DUMP, path], capture_output=True, text=True, check=True
    ).stdout
    rows = []
    for r in csv.DictReader(out.splitlines()):
        try:
            rows.append(
                {
                    "t": float(r["time"]),
                    "p": [float(r["x"]), float(r["y"]), float(r["z"])],
                }
            )
        except (ValueError, KeyError):
            continue
    return rows


def _speed_at(rows: list[dict], i: int, back: bool) -> float:
    """Mean speed over the three frames just before (`back`) or just after index `i`."""
    sp = []
    for k in range(1, 4):
        a, b = (i - k, i - k + 1) if back else (i + k - 1, i + k)
        if not (0 <= a and b < len(rows)):
            break
        dt = rows[b]["t"] - rows[a]["t"]
        if dt > 0:
            sp.append(math.dist(rows[b]["p"], rows[a]["p"]) / dt)
    return sum(sp) / len(sp) if sp else 0.0


def split_runs(rows: list[dict]) -> list[list[dict]]:
    """Split into attempts at respawns, keeping teleports inside a run.

    Both move the player further in one frame than physics allows, so distance alone cannot tell
    them apart. Speed can: a teleporter preserves the run (measured ~450 u/s in, and QW sets the
    exit to ~300 u/s out), while a respawn has the player at rest on both sides. A run that spans
    a teleporter is one route and must be timed as one — splitting there dropped the whole
    `ya-to-tele-to-window-to-rl` drill, which is the point of the distinction.
    """
    runs, cur = [], []
    for i, r in enumerate(rows):
        if cur and math.dist(r["p"], cur[-1]["p"]) > SPLIT_DIST:
            teleport = _speed_at(rows, i, back=True) > MOVING and _speed_at(rows, i, back=False) > MOVING
            if not teleport:
                runs.append(cur)
                cur = []
        cur.append(r)
    if cur:
        runs.append(cur)
    return [r for r in runs if len(r) > 8]


def time_run(run: list[dict], goal: list[float], radius: float = ARRIVE) -> dict | None:
    """Clock a run from first motion to first arrival within `radius` of `goal`."""
    arrive_i = None
    for i, r in enumerate(run):
        if math.dist(r["p"], goal) <= radius:
            arrive_i = i
            break
    if arrive_i is None:
        return None
    # Walk *forward* to the frame the recorder first got under way. Searching backwards from the
    # arrival instead finds the last standstill anywhere in the run, which on a multi-leg route
    # (`spawn-lift -> Pent -> Pent Mega`, where the recorder pauses at Pent) silently retimes the
    # drill from the midpoint and reports the wrong start coordinate. Mid-route pauses are counted
    # in the time and surfaced as `pauses` rather than trimmed away.
    start_i = 0
    for i in range(1, arrive_i + 1):
        dt = run[i]["t"] - run[i - 1]["t"]
        if dt > 0 and math.dist(run[i]["p"], run[i - 1]["p"]) / dt >= MOVING:
            start_i = i - 1
            break
    pauses = 0
    moving = True
    for i in range(start_i + 1, arrive_i + 1):
        dt = run[i]["t"] - run[i - 1]["t"]
        if dt <= 0:
            continue
        fast = math.dist(run[i]["p"], run[i - 1]["p"]) / dt >= MOVING
        if moving and not fast:
            pauses += 1
        moving = fast
    secs = run[arrive_i]["t"] - run[start_i]["t"]
    if secs < MIN_RUN_SECS:
        return None
    # Ground actually covered. A teleporter hop is not distance travelled: counting it put the
    # `ya-to-tele-to-window-to-rl` recorder at a mean 930 u/s, which no player reaches. Same
    # threshold and same reason as `corridor_metrics`' `path_len` on the bot side, so the two
    # mean speeds are comparable.
    path = 0.0
    for i in range(start_i + 1, arrive_i + 1):
        step = math.dist(run[i]["p"], run[i - 1]["p"])
        if step < SPLIT_DIST:
            path += step
    return {
        "secs": secs,
        "from_xyz": [round(v) for v in run[start_i]["p"]],
        "to_xyz": [round(v) for v in run[arrive_i]["p"]],
        "frames": arrive_i - start_i,
        "path_len": round(path),
        "mean_speed": round(path / secs) if secs > 0 else 0,
        "pauses": pauses,
    }


# The goal each demo is an attempt at, taken from the name its recorder gave it, with the
# segment to use where a file holds more than one. Declared rather than inferred: picking the
# "nearest named point" from the data alone confuses RL with RL-spawn (65u apart) and the start
# point with the goal. Every entry is cross-checked against the trajectory's closest approach,
# which `main` prints, so a wrong declaration is visible rather than silent.
#
# `all-4-hexagon-variants.qwd` is deliberately absent: its three segments circle the SNG
# teleport with no named destination, and guessing a goal would fabricate a target time.
DRILLS = {
    "sngspawns-to-sngmega.qwd": (0, "SNG Mega"),
    "lifts-or-ring-to-sngmega.qwd": (0, "SNG Mega"),
    "ralow-to-ratop.qwd": (0, "RA"),
    "ring-to-ratop.qwd": (0, "RA"),
    "highbridge-to-rl.qwd": (0, "RL"),
    "window-to-rl.qwd": (0, "RL"),
    "rj-pent-to-lifts-to-window-to-quad.qwd": (0, "Quad"),
    # v0.1 additions.
    "quad-to-sng.qwd": (0, "SNG"),
    "ratop-to-ssg.qwd": (0, "SSG"),
    "sng-to-quad.qwd": (0, "Quad"),
    "ssg-to-ratop.qwd": (0, "RA"),
    "ya-to-tele-to-window-to-rl.qwd": (0, "RL"),
    # v0.2/v0.3. Three files were renamed between drops and the archives are byte-identical
    # (md5-checked), so only the newer name is listed — keeping both would count one recording
    # twice. `spawn-lift-to-pent` -> `spawn-lift-to-pent-to-pentmega` also moved the goal: the
    # recorder passes Pent at t+4.10s and reaches Pent Mega at t+7.66s, so the drill is the longer
    # one the new name describes.
    "lg-to-pent-to-pentmega.qwd": (0, "Pent Mega"),
    "spawn-lift-to-pent-to-pentmega.qwd": (0, "Pent Mega"),
    "spawn-rl_to_ratop.qwd": (0, "RA"),
    "spawn-ra-tunnel-to-lg.qwd": (0, "LG"),
    "spawn-rarox-to-quad.qwd": (0, "Quad"),
}

# Drills the bot is allowed to rocket-jump on. Everything else runs against a navmesh built with
# `rtx_bot_rocketjump 0` (verified live: rj_links drops 2021 -> 0), because that cvar is read only
# at navmesh build time — setting it on a built mesh leaves every rocket-jump link in place.
RJ_ALLOWED = {"rj-pent-to-lifts-to-window-to-quad"}

# The two weapons the v0.1 demos aim at are not in the route sheet. Taken from the live server's
# own `Items` verb (`rex-drills <port> items`) rather than guessed, so they are the same origins
# the bot's own goal-snapping sees.
EXTRA_POINTS = {
    "SNG": [-512.0, 448.0, 96.0],  # weapon_supernailgun
    "SSG": [1776.0, -656.0, -48.0],  # weapon_supershotgun
}
# The RL runs pass the item at ~81u / ~118u: `RL`'s listed origin is the pickup's own origin and
# the demo records the eye position, so a wider radius is needed for those two than for a goal
# the recorder actually stood on.
ARRIVE_BY_GOAL = {"RL": 128.0, "Pent Mega": 128.0}


def main() -> None:
    pts = named_points()
    report = {}
    for name, (seg, goal_name) in DRILLS.items():
        path = os.path.join("dm3-drillar", name)
        runs = split_runs(rows_for(path))
        run = runs[seg]
        goal = pts[goal_name]
        radius = ARRIVE_BY_GOAL.get(goal_name, ARRIVE)
        closest = min(math.dist(r["p"], goal) for r in run)
        timed = time_run(run, goal, radius)
        if timed is None:
            print(f"{name:38} seg{seg} -> {goal_name}: NO ARRIVAL (closest {closest:.0f}u)")
            continue
        timed.update({"goal_name": goal_name, "seg": seg, "closest_u": round(closest)})
        print(
            f"{name:38} seg{seg} -> {goal_name:9} {timed['secs']:6.2f}s"
            f"  from [{timed['from_xyz'][0]:5} {timed['from_xyz'][1]:5} {timed['from_xyz'][2]:5}]"
            f"  closest {closest:5.0f}u"
        )
        report[name] = timed
    json.dump(report, open("human_times.json", "w"), indent=1)
    print(f"\nwrote human_times.json — {len(report)} timed drills")


if __name__ == "__main__":
    main()
