"""Find the jumps a route's fast line depends on, and check whether the bot performs them.

This replaces counting entrances to a room, which was the wrong unit. Not every target sits in a
room, not every room has more than one way in, and a trick jump is not usually a doorway — it is a
gap crossed, a ledge reached, or a drop taken that turns a long way round into a short way through.
The thing worth measuring is whether the bot *executes the manoeuvre*, because arrival time is a
lagging aggregate that says a route was slow without saying which move was missed.

**How a manoeuvre is identified, from data rather than by hand.** Take a human reference demo. Cut it
into airborne segments — runs of consecutive ticks off the ground. For each, record where the player
left the ground and where they landed. Then ask the navmesh how far it is to *walk* between those two
points. A hop along a corridor walks about as far as it flies and is ordinary movement. A jump whose
landing is 900 units of walking away, or has no walking route at all, is the route's shortcut, and it
is the move the fast line is built on.

    shortcut = walk_distance(takeoff, landing) - straight_distance(takeoff, landing)

That definition needs no notion of rooms, works on a flat gap and a vertical drop alike, and is
computed from the same map the bot runs on.

**How execution is checked.** A bot has performed the manoeuvre when it leaves the ground within
`takeoff_tol` of the human's takeoff and next touches down within `landing_tol` of the human's
landing. Not "passed near the landing" — *landed there off the same jump*, so walking round and
arriving at the same spot does not count as having made it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

# A segment shorter than this is a step off a kerb, not a manoeuvre.
MIN_AIR_TICKS = 4

# --- what a plain jump can do, from QuakeWorld's own numbers ---------------------------------
# A jump leaves the ground at vz = 270 against gravity 800. It therefore rises 270^2/(2*800) = 45.5 u
# and hangs 2*270/800 = 0.675 s, which at the takeoff speed sets how far forward it can carry.
#
# This replaced a mesh-based definition of "shortcut" that was circular: the navmesh already contains
# jump, drop and speed-jump links, so asking it how far it is to *walk* between a takeoff and its
# landing returns the length of the jump the mesh models there. Every real manoeuvre scored as saving
# nothing. Physics has no such conflict of interest.
JUMP_VZ = 270.0
GRAVITY = 800.0
PLAIN_JUMP_RISE_U = JUMP_VZ * JUMP_VZ / (2.0 * GRAVITY)     # 45.5
PLAIN_JUMP_HANG_S = 2.0 * JUMP_VZ / GRAVITY                 # 0.675

# Margins on the two plain-jump bounds. 8 u of rise and 10 % of reach absorb slope, stair steps and
# the tick quantisation of a takeoff, without absorbing a real gap.
RISE_MARGIN_U = 8.0
REACH_MARGIN = 1.10

# Speed gained *while airborne* is the signature of strafe/air control — the technique itself, not a
# consequence of it. 25 u/s is comfortably above the noise in a 77 Hz sampling of a steady flight.
AIR_GAIN_UPS = 25.0

# A jump the mesh cannot walk around at all is always critical, whatever the numbers say.
NO_WALK_ROUTE = float("inf")

# Above this implied speed the segment is not a jump. A "jump" of 832 units in 0.13 s is 6400 u/s;
# QuakeWorld tops out near 600 with a rocket behind you. Those segments are teleporter transits and
# recording gaps, and counting them as manoeuvres put a 1300-unit shortcut in the table that no
# player ever performed. Rejected rather than clamped: a clamped teleport is a fabricated jump.
MAX_JUMP_UPS = 900.0


@dataclass
class Manoeuvre:
    route: str
    index: int
    takeoff: tuple[float, float, float]
    landing: tuple[float, float, float]
    air_ticks: int
    air_s: float
    gap_u: float              # straight-line distance takeoff -> landing
    rise_u: float             # landing z minus takeoff z
    takeoff_speed_ups: float
    peak_speed_ups: float
    walk_u: float             # navmesh walking distance between the same two points
    shortcut_u: float         # walk_u - gap_u; how much the jump saves
    critical: bool
    kind: str                 # 'jump' | 'teleport_or_gap'
    # Why this move is beyond a plain jump — empty for ordinary hops.
    demands: tuple[str, ...]
    air_gain_ups: float
    plain_reach_u: float

    def to_json(self) -> dict:
        d = asdict(self)
        d["walk_u"] = None if d["walk_u"] == NO_WALK_ROUTE else round(d["walk_u"], 1)
        d["shortcut_u"] = None if d["shortcut_u"] == NO_WALK_ROUTE else round(d["shortcut_u"], 1)
        return d


def airborne_segments(frames: np.ndarray, ground: np.ndarray, speed: np.ndarray,
                      tick_dt: float) -> list[dict]:
    """Contiguous runs of off-the-ground ticks, with the ground contact each side of them."""
    out = []
    n = len(frames)
    i = 0
    while i < n:
        if ground[i]:
            i += 1
            continue
        j = i
        while j < n and not ground[j]:
            j += 1
        if j - i >= MIN_AIR_TICKS:
            # The takeoff is the last grounded tick before the segment, the landing the first after;
            # using the airborne endpoints instead would place both a tick's travel out of position.
            a = max(i - 1, 0)
            b = min(j, n - 1)
            out.append({
                "a": a, "b": b, "air_ticks": j - i, "air_s": (j - i) * tick_dt,
                "takeoff": tuple(float(v) for v in frames[a]),
                "landing": tuple(float(v) for v in frames[b]),
                "takeoff_speed": float(speed[a]),
                "peak_speed": float(speed[i:j].max()) if j > i else float(speed[a]),
            })
        i = j + 1
    return out


def walk_distances(map_path: str, pairs: list[tuple]) -> list[tuple[float, bool]]:
    """For each (takeoff, landing) pair: the navmesh walking distance, and whether both endpoints
    are on the mesh at all.

    The second value is what separates "you cannot walk between these" from "one of these is not
    somewhere the mesh knows about", and without it every jump that starts or lands off-mesh reads as
    an impossible shortcut."""
    import rex_env
    pts = np.asarray([p for pair in pairs for p in pair], dtype=np.float32)
    snapped = np.asarray(rex_env.PyVecEnv.snap_many(map_path, pts)).reshape(-1, 2)
    out = []
    for k, (a, b) in enumerate(pairs):
        on_mesh = bool(snapped[k].all())
        if not on_mesh:
            out.append((NO_WALK_ROUTE, False))
            continue
        p = rex_env.PyVecEnv.plan_many(map_path, [tuple(map(float, a))], tuple(map(float, b)))[0]
        if not p:
            out.append((NO_WALK_ROUTE, True))
            continue
        A = np.asarray(p, dtype=np.float64)
        out.append((float(np.sum(np.linalg.norm(np.diff(A, axis=0), axis=1))), True))
    return out


def find(map_path: str, route: str, pos: np.ndarray, ground: np.ndarray, speed: np.ndarray,
         tick_dt: float) -> list[Manoeuvre]:
    """Every airborne segment in a trajectory, scored, with the critical ones flagged."""
    segs = airborne_segments(pos, ground, speed, tick_dt)
    if not segs:
        return []
    walks = walk_distances(map_path, [(s["takeoff"], s["landing"]) for s in segs])
    out = []
    for k, (s, (w, on_mesh)) in enumerate(zip(segs, walks)):
        t = np.asarray(s["takeoff"]); l = np.asarray(s["landing"])
        gap = float(np.linalg.norm(l - t))
        gap_xy = float(np.linalg.norm(l[:2] - t[:2]))
        rise = float(l[2] - t[2])
        implied = gap / max(s["air_s"], 1e-6)
        kind = "teleport_or_gap" if implied > MAX_JUMP_UPS else "jump"

        reach = s["takeoff_speed"] * PLAIN_JUMP_HANG_S
        gain = s["peak_speed"] - s["takeoff_speed"]
        demands = []
        if rise > PLAIN_JUMP_RISE_U + RISE_MARGIN_U:
            demands.append(f"stiger {rise:.0f} u, ett vanligt hopp klarar {PLAIN_JUMP_RISE_U:.0f}")
        if gap_xy > reach * REACH_MARGIN:
            demands.append(f"når {gap_xy:.0f} u, ett vanligt hopp från {s['takeoff_speed']:.0f} u/s "
                           f"klarar {reach:.0f}")
        if gain > AIR_GAIN_UPS:
            demands.append(f"vinner {gain:.0f} u/s i luften (luftstyrning)")
        short = NO_WALK_ROUTE if w == NO_WALK_ROUTE else w - gap
        out.append(Manoeuvre(
            route=route, index=k,
            takeoff=tuple(round(v, 1) for v in s["takeoff"]),
            landing=tuple(round(v, 1) for v in s["landing"]),
            air_ticks=s["air_ticks"], air_s=round(s["air_s"], 3),
            gap_u=round(gap, 1), rise_u=round(s["landing"][2] - s["takeoff"][2], 1),
            takeoff_speed_ups=round(s["takeoff_speed"], 1),
            peak_speed_ups=round(s["peak_speed"], 1),
            walk_u=w, shortcut_u=short,
            kind=kind, demands=tuple(demands),
            air_gain_ups=round(gain, 1), plain_reach_u=round(reach, 1),
            # A trick jump is one a plain jump cannot produce. Nothing about rooms, nothing about the
            # navmesh — just whether the move exceeds what pressing jump once buys you.
            critical=(kind == "jump" and bool(demands)),
        ))
    return out


def executed(pos: np.ndarray, ground: np.ndarray, m: Manoeuvre,
             takeoff_tol: float = 96.0, landing_tol: float = 96.0) -> dict:
    """Did this trajectory perform the manoeuvre — left the ground near the takeoff and next touched
    down near the landing?

    The two halves are checked as one event, not separately. A bot that walks the long way round and
    ends up standing on the landing spot has not performed the jump, and scoring the halves apart
    would call that a pass.
    """
    n = len(pos)
    t = np.asarray(m.takeoff, dtype=np.float64)
    l = np.asarray(m.landing, dtype=np.float64)
    best = None
    i = 0
    while i < n:
        if ground[i]:
            i += 1
            continue
        j = i
        while j < n and not ground[j]:
            j += 1
        a, b = max(i - 1, 0), min(j, n - 1)
        d_t = float(np.linalg.norm(pos[a] - t))
        d_l = float(np.linalg.norm(pos[b] - l))
        score = max(d_t, d_l)
        if best is None or score < best["worst_u"]:
            best = {"takeoff_err_u": round(d_t, 1), "landing_err_u": round(d_l, 1),
                    "worst_u": round(score, 1), "at_tick": a, "air_ticks": j - i}
        i = j + 1
    if best is None:
        return {"executed": False, "reason": "never left the ground", "best": None}
    ok = best["takeoff_err_u"] <= takeoff_tol and best["landing_err_u"] <= landing_tol
    return {"executed": bool(ok),
            "reason": "" if ok else "closest airborne segment starts or ends too far away",
            "best": best}


def report(manoeuvres: list[Manoeuvre]) -> str:
    """The distributions the classification rests on, printed so the cut is inspectable."""
    if not manoeuvres:
        return "inga luftsegment"
    j = [m for m in manoeuvres if m.kind == "jump"]
    rise = np.array([m.rise_u for m in j]); gain = np.array([m.air_gain_ups for m in j])
    over = np.array([m.gap_u / max(m.plain_reach_u, 1e-6) for m in j])
    return (f"{len(manoeuvres)} luftsegment, {len(j)} riktiga hopp; "
            f"stigning p50 {np.percentile(rise, 50):.0f} p90 {np.percentile(rise, 90):.0f} u "
            f"(vanligt hopp {PLAIN_JUMP_RISE_U:.0f}); "
            f"luftvinst p50 {np.percentile(gain, 50):.0f} p90 {np.percentile(gain, 90):.0f} u/s; "
            f"räckvidd/plain p90 {np.percentile(over, 90):.2f}; "
            f"{sum(1 for m in j if m.critical)} trickhopp")


def save(manoeuvres: list[Manoeuvre], path: str | Path) -> None:
    Path(path).write_text(json.dumps([m.to_json() for m in manoeuvres], indent=1))
