#!/usr/bin/env python3
"""Extract per-run start/end coordinates and travel time from dm3 drill .qwd demos.

Uses the strict QWD v2 extractor (qw-demo-miner/qwd/v2) to get playerinfo rows
for the recording client, then segments each demo into motion runs separated by
stationary periods.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, "/mnt/c/Users/benya/projects/quakeworld/qw-demo-miner/qwd/v2")
from qwd_v2.extractor import extract_file  # noqa: E402

DRILLS = Path("/mnt/c/Users/benya/Downloads/dm3-drillar")
OUT = DRILLS / "dm3-drillar-routes.json"
# Authoritative dm3 item spawns, from mvd_analyzer:
#   curl 'localhost:8080/v1/maps/dm3/entities?types=item' -o dm3-items.json
ITEMS = DRILLS / "dm3-items.json"

# Route-name token -> the dm3 item entity it means, as (kind, loc).
TARGETS = {
    "rl": ("rl", "RL"),
    "lg": ("lg", "water.LG"),
    "ssg": ("ssg", "YA"),
    "sng": ("sng", "SNG"),
    "quad": ("quad", "Quad"),
    "pent": ("pent", "Pent"),
    "ring": ("ring", "Ring"),
    "ratop": ("ra", "RA"),
    "ra": ("ra", "RA"),
    "pentmega": ("mh", "Pent"),
    "sngmega": ("mh", "SNG.MH"),
    "hillmega": ("mh", "hill"),
}
# Suffixes that are recorder annotations, not route targets.
NAME_SUFFIXES = ("xer",)
AT_ITEM = 100.0      # units: end origin this close counts as "reached the item"
NEAR_ITEM = 250.0    # units: beyond this the drill did not end at its named target

MOVING_SPEED = 1.0      # units/s; below this the player counts as stationary
SPLIT_STILL_S = 0.10    # any stationary gap this long cuts the motion apart
MERGE_STILL_S = 0.35    # ...but real runs are rejoined across a momentary stop
MIN_RUN_DIST = 200.0    # units of path length; shorter hops are warm-up jitter
MIN_RUN_S = 0.30        # ignore shorter blips
MARGIN = 1.12           # "lowest acceptable" = 12% slower than actual


def load_items() -> list[dict]:
    return json.loads(ITEMS.read_text(encoding="utf-8"))["entities"]


def nearest_item(pos, items) -> dict:
    best = min(items, key=lambda e: math.dist(pos, [e["x"], e["y"], e["z"]]))
    return {
        "kind": best["kind"],
        "loc": best["loc"],
        "class": best["class"],
        "pos": [best["x"], best["y"], best["z"]],
        "distance": r3(math.dist(pos, [best["x"], best["y"], best["z"]])),
    }


def route_tokens(stem: str) -> list[str]:
    """'(spawn)rl-to-ratop-xer' -> ['rl', 'ratop']"""
    name = stem.split(")")[-1] if stem.startswith("(") else stem
    toks = []
    for part in name.replace("_", "-").split("-to-"):
        words = [w.lower() for w in part.strip("-").split("-") if w]
        while len(words) > 1 and words[-1] in NAME_SUFFIXES:
            words.pop()
        if words:
            toks.append(words[-1])
    return toks


def named_target(token: str, items) -> dict | None:
    key = TARGETS.get(token)
    if key is None:
        return None
    kind, loc = key
    for e in items:
        if e["kind"] == kind and e["loc"] == loc:
            return {"token": token, "kind": kind, "loc": loc,
                    "pos": [e["x"], e["y"], e["z"]]}
    return None


def f(v):
    return float(v)


def r3(v):
    return round(v, 3)


def analyse(path: Path, items) -> dict:
    ex = extract_file(str(path))
    man = ex.manifest
    if not man["completeness"]:
        rej = man.get("rejection_reason") or {}
        return {
            "demo": path.name,
            "route": path.stem,
            "map": "dm3",
            "parsed": False,
            "reason": "recorded with FTE protocol extensions the strict QWD "
                      "extractor does not implement; re-record without them "
                      "to include this route",
            "rejection": rej,
        }

    seg = next(r for r in ex.rows if r["event"] == "segment")
    local_slot = seg["local_slot"]
    pi = [r for r in ex.rows
          if r["event"] == "playerinfo" and r["player"] == local_slot]

    t0 = f(pi[0]["packet_time"])
    samples = []
    for r in pi:
        samples.append({
            "t": f(r["packet_time"]) - t0,
            "pos": [f(r["origin_x"]), f(r["origin_y"]), f(r["origin_z"])],
            "speed": math.sqrt(f(r["velocity_x"]) ** 2
                               + f(r["velocity_y"]) ** 2
                               + f(r["velocity_z"]) ** 2),
        })

    moving = [s["speed"] > MOVING_SPEED for s in samples]

    # 1. Cut motion apart at every stationary gap of SPLIT_STILL_S or more.
    raw = []
    i = 0
    n = len(samples)
    while i < n:
        if not moving[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and moving[j + 1]:
            j += 1
        if raw:
            pi_prev, pj_prev = raw[-1]
            if samples[i]["t"] - samples[pj_prev]["t"] < SPLIT_STILL_S:
                raw[-1] = (pi_prev, j)
                i = j + 1
                continue
        raw.append((i, j))
        i = j + 1

    # 2. Drop warm-up jitter: repositioning at the start point, not a route.
    #    Measured as path length, not net displacement — a route that loops
    #    back toward its start still covers real ground.
    def path_len(a, b):
        return sum(math.dist(samples[k]["pos"], samples[k + 1]["pos"])
                   for k in range(a, b))

    kept = [(a, b) for a, b in raw if path_len(a, b) >= MIN_RUN_DIST]
    dropped = len(raw) - len(kept)

    # 3. Rejoin what a momentary mid-route stop split apart.
    blocks = []
    for a, b in kept:
        if blocks and samples[a]["t"] - samples[blocks[-1][1]]["t"] < MERGE_STILL_S:
            blocks[-1] = (blocks[-1][0], b)
        else:
            blocks.append((a, b))

    runs = []
    for idx, (a, b) in enumerate(blocks, 1):
        # anchor on the last stationary sample before, and first after
        sa = max(a - 1, 0)
        sb = min(b + 1, n - 1)
        dur = samples[sb]["t"] - samples[sa]["t"]
        if dur < MIN_RUN_S:
            continue
        start, end = samples[sa], samples[sb]
        dist = math.dist(start["pos"], end["pos"])
        peak = max(s["speed"] for s in samples[a:b + 1])
        runs.append({
            "run": idx,
            "start_pos": [r3(v) for v in start["pos"]],
            "end_pos": [r3(v) for v in end["pos"]],
            "start_time_s": r3(start["t"]),
            "end_time_s": r3(end["t"]),
            "travel_time_s": r3(dur),
            "min_acceptable_time_s": r3(dur * MARGIN),
            "straight_line_distance": r3(dist),
            "peak_speed": r3(peak),
            # False => the demo starts/ends mid-motion, so the measured time is
            # truncated at that end and understates the real travel time.
            "start_anchored": sa != a and samples[sa]["speed"] <= MOVING_SPEED,
            "end_anchored": sb != b and samples[sb]["speed"] <= MOVING_SPEED,
            "start_nearest_item": nearest_item(start["pos"], items),
            "end_nearest_item": nearest_item(end["pos"], items),
            "_span": (a, b),
        })
    # renumber after filtering
    for k, run in enumerate(runs, 1):
        run["run"] = k

    out = {
        "demo": path.name,
        "route": path.stem,
        "map": "dm3",
        "level_name": seg["map"],
        "protocol": seg["protocol"],
        "demo_id_sha256": man["demo_id"],
        "demo_duration_s": r3(samples[-1]["t"]),
        "sample_count": len(samples),
        "parsed": True,
        "warmup_blocks_dropped": dropped,
        "run_count": len(runs),
        "runs": runs,
    }
    # Does the run actually get to the item the route name promises? Measure
    # against the closest approach anywhere in the run, not just the end —
    # some drills run past the target and stop elsewhere.
    toks = route_tokens(path.stem)
    out["route_tokens"] = toks
    tgt = named_target(toks[-1], items) if toks else None
    if tgt and runs:
        last = runs[-1]
        a, b = last["_span"]
        closest_i, closest_d = a, math.inf
        for k in range(a, b + 1):
            d = math.dist(samples[k]["pos"], tgt["pos"])
            if d < closest_d:
                closest_i, closest_d = k, d
        reach_t = samples[closest_i]["t"] - last["start_time_s"]
        out["target"] = {
            "token": tgt["token"],
            "item": f"{tgt['kind']}@{tgt['loc']}",
            "pos": tgt["pos"],
            "closest_distance": r3(closest_d),
            "end_distance": r3(math.dist(last["end_pos"], tgt["pos"])),
            "reach_time_s": r3(reach_t),
            "min_acceptable_reach_time_s": r3(reach_t * MARGIN),
            "status": ("reached" if closest_d <= AT_ITEM
                       else "near" if closest_d <= NEAR_ITEM
                       else "off_target"),
            "ends_at_target": math.dist(last["end_pos"], tgt["pos"]) <= NEAR_ITEM,
            "source": "mvd_analyzer dm3 entity corpus",
        }
    elif toks:
        out["target"] = {"token": toks[-1], "status": "unmapped",
                         "note": "no dm3 item entity mapped for this name token"}

    for r in runs:
        r.pop("_span", None)

    if runs:
        best = min(runs, key=lambda r: r["travel_time_s"])
        out["fastest"] = {
            "run": best["run"],
            "start_pos": best["start_pos"],
            "end_pos": best["end_pos"],
            "travel_time_s": best["travel_time_s"],
            "min_acceptable_time_s": best["min_acceptable_time_s"],
        }
    return out


def main() -> int:
    items = load_items()
    demos = sorted(DRILLS.glob("*.qwd"))
    results = [analyse(p, items) for p in demos]
    doc = {
        "source_dir": str(DRILLS),
        "map": "dm3",
        "extractor": "qw-demo-miner qwd/v2 strict QWD extractor",
        "units": {
            "coordinates": "Quake units (x, y, z)",
            "time": "seconds (demo-relative, t=0 at first playerinfo)",
            "speed": "Quake units per second",
        },
        "definitions": {
            "run": f"a motion segment: cut at every stationary gap >= "
                   f"{SPLIT_STILL_S}s, pieces covering less than {MIN_RUN_DIST} "
                   f"units of path discarded as warm-up jitter, then rejoined "
                   f"across stops shorter than {MERGE_STILL_S}s",
            "start_pos/end_pos": "origin at the last stationary sample before "
                                 "the run and the first stationary sample after it",
            "travel_time_s": "measured wall time between those two samples",
            "min_acceptable_time_s": f"travel_time_s * {MARGIN} — lowest acceptable "
                                     "level (12% slower than the recorded run)",
            "*_nearest_item": "closest dm3 item spawn to that origin, from the "
                              "mvd_analyzer entity corpus (dm3-items.json)",
            "target": "the item the route name's last token promises, resolved "
                      "from the mvd_analyzer dm3 entity corpus. closest_distance "
                      "is the run's closest approach to it (reached <= "
                      f"{AT_ITEM}, near <= {NEAR_ITEM}, else off_target); "
                      "reach_time_s is start -> that closest approach. When "
                      "ends_at_target is false the drill ran past the item and "
                      "stopped elsewhere, so reach_time_s — not travel_time_s — "
                      "is the route time",
        },
        "regenerated_from": "only the .qwd files currently present in source_dir; "
                            "removed demos drop out on every run",
        "summary": {
            "demos_found": len(results),
            "demos_parsed": sum(1 for d in results if d.get("parsed")),
            "demos_unparsed": sum(1 for d in results if not d.get("parsed")),
        },
        "demos": results,
    }
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    for d in results:
        if not d.get("parsed"):
            print(f"UNPARSED {d['demo']}: {d['rejection'].get('code')}")
            continue
        flags = "".join(
            "" if (r["start_anchored"] and r["end_anchored"]) else " !TRUNCATED"
            for r in d["runs"])
        tgt = d.get("target") or {}
        print(f"{d['demo']:<40} "
              + " ".join(f"{r['travel_time_s']:7.3f}s"
                         f" min {r['min_acceptable_time_s']:7.3f}s"
                         for r in d["runs"])
              + f"  {tgt.get('status','-'):<10}"
              + (f" {tgt.get('item',''):<12} d={tgt.get('closest_distance'):<8}"
                 f" reach={tgt.get('reach_time_s')}s"
                 + ("" if tgt.get("ends_at_target") else "  <-- runs past target")
                 if tgt.get("closest_distance") is not None else "")
              + flags)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
