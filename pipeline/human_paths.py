"""Extract the humans' own trajectories for the eight cohort routes, to use as `Route.path`.

Why this exists, in one measurement. `evidence/f1_route_geometry.json` compares the navmesh's
planned path against the straight line between each route's endpoints:

    window_to_rl        2002 u planned    246 u straight    gate 3.75 s  =>  534 u/s required
    quad_to_ra          5064 u planned   1248 u straight    gate 8.96 s  =>  565 u/s required
    sngspawn_a_to_quad  6772 u planned   1908 u straight    gate 4.27 s  => 1586 u/s required

QuakeWorld's ceiling is around 550-600 u/s. On those routes the *mesh* is the gate, not the policy:
`build_navmesh` models walk/step/drop/jump-gap links and nothing else, so the window drop reads as a
2000 u detour and the SNG teleporter does not exist at all. Training harder against a path that
cannot be run in time is the expensive way to learn arithmetic.

A path a human actually ran is, by construction, runnable in the human's own time. The corpus holds
907,977,350 trajectory samples, and route-lab's certified cohort SQL
(`route_lab.dm3_route_defs.cohort_cte_chain`) already binds exactly the (demo, slot, start, pickup)
windows the medians were computed over — the same bindings, not a reimplementation of them. This
module joins those windows to the samples and writes each run out as a polyline.

**This is calibration geometry, not demonstration data.** The paths are used as the route the
lookahead slides along and as the arclength the progress reward is measured in. No usercmd, no
action and no trajectory is copied into the policy: the agent still has to drive itself down the
path with its own physics. That distinction is the standing rule in this project and it is preserved
here.

Selection: the fastest `n_paths` runs whose sampling is dense enough to be a path rather than a
sketch. Fastest rather than median because the owner's band is "the median, the best time, or
better" — the geometry we train against should be the geometry of a good run.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, "/home/benjamin-adm/route-lab-src")
from route_lab.dm3_route_defs import cohort_cte_chain, load_routes  # noqa: E402

STORE = Path("/home/benjamin-adm/dm3-extract/store-dm3")
ITEM_EVENTS = str(STORE / "item_events/**/*.parquet")
SPAWNS = str(STORE / "spawns/**/*.parquet")
TRAJ = str(STORE / "trajectory_samples/**/*.parquet")

OUT = Path("/home/benjamin-adm/rex-ml/pipeline/out/paths")

# route-lab registry name -> the cohort_routes.py name it feeds
REGISTRY_TO_COHORT = {
    "zip-window-to-rl": "window_to_rl",
    "sngspawn-to-quad": ("sngspawn_a_to_quad", "sngspawn_b_to_quad"),
    "zip-ralow-to-ratop": "ralow_to_ratop",
    "lifts-to-sng-mega": "lifts_to_sng_mega",
    "quad-to-ra": "quad_to_ra",
    "zip-ring-to-ratop": "ring_to_ratop",
    "sngspawn-to-mega": ("sngspawn_a_to_mega", "sngspawn_b_to_mega"),
    "tunnel-to-ra": "tunnel_to_ra",
    # sng/lifts side -> Quad, added 2026-07-30. Unlike sngspawn-to-quad this pair has clean
    # movement runs: 8 candidates, 4 pass vet unchanged, 4 are true teleports (~780 u in one
    # sample step) and are correctly rejected as `gap`.
    "zip-hex-sng-to-quad": "sng_to_quad",
}

# A run is only usable as a path if the demo sampled it densely enough. MVD sampling is not uniform;
# a run recorded at 4 samples/s traces a shape that cuts every corner it went round. 12 samples per
# second over the run is the floor, which at 300 u/s is a point every ~25 u.
MIN_SAMPLES_PER_S = 12.0

# Consecutive samples further apart than this in 3-D are a gap the demo did not record (a dropped
# stretch, or a teleport). A path with such a jump is not a path a player walked, so it is dropped —
# except that a jump landing exactly on a known teleport destination is *information*, reported
# separately rather than silently discarded.
MAX_SAMPLE_GAP_U = 220.0


def _con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    c.execute("SET threads TO 48")
    c.execute("SET memory_limit = '400GB'")
    return c


def cohort_runs(con, registry_name: str, limit: int = 400) -> list[dict]:
    """The (demo_key, slot, start_ms, pickup_ms, duration_s) windows for one registry route,
    fastest first — route-lab's own CTE chain, with only the final SELECT written here."""
    route = load_routes()[registry_name]
    cte = cohort_cte_chain(route, ITEM_EVENTS, SPAWNS, TRAJ)
    sql = f"""{cte}
SELECT demo_key, slot, source_spawn_t AS start_ms, pickup_t AS end_ms, duration_s
FROM same_life_routes
ORDER BY duration_s
LIMIT {limit}
"""
    cols = ["demo_key", "slot", "start_ms", "end_ms", "duration_s"]
    return [dict(zip(cols, r)) for r in con.execute(sql).fetchall()]


def fetch_paths(con, runs: list[dict]) -> dict[tuple[int, int, int], list[tuple]]:
    """All trajectory samples inside every run's window, in one scan of the sample table rather
    than one scan per run — the table is 7.8 GB and 908 M rows, and `len(runs)` separate passes over
    it is the difference between a minute and an afternoon."""
    if not runs:
        return {}
    con.execute("DROP TABLE IF EXISTS _runs")
    con.execute("CREATE TEMP TABLE _runs(demo_key UINTEGER, slot UTINYINT, start_ms INTEGER, end_ms INTEGER)")
    con.executemany("INSERT INTO _runs VALUES (?,?,?,?)",
                    [(r["demo_key"], r["slot"], r["start_ms"], r["end_ms"]) for r in runs])
    rows = con.execute(f"""
        SELECT r.demo_key, r.slot, r.start_ms, ts.t, ts.x, ts.y, ts.z,
               ts.vx, ts.vy, ts.vz, ts.velocity_present
        FROM _runs r
        JOIN read_parquet('{TRAJ}', hive_partitioning=true, union_by_name=true) ts
          ON ts.demo_key = r.demo_key AND ts.slot = r.slot
         AND ts.t >= r.start_ms AND ts.t <= r.end_ms
        WHERE ts.map = 'dm3' AND ts.format = 'mvd' AND ts.mode = '4on4'
        ORDER BY r.demo_key, r.slot, r.start_ms, ts.t
    """).fetchall()
    out: dict[tuple[int, int, int], list[tuple]] = {}
    for dk, slot, s_ms, t, x, y, z, vx, vy, vz, vp in rows:
        # Velocity is carried alongside position because episodes restart from these states, and a
        # recorded position without the speed the human carried through it is a different state
        # entirely — dropping a standing agent onto a bunny-hop line teaches it nothing about
        # bunny-hopping. Samples without a recorded velocity keep the position and report zero, and
        # `restart_states` filters them out rather than pretending they were stationary.
        out.setdefault((dk, slot, s_ms), []).append((
            t, float(x), float(y), float(z),
            float(vx or 0.0), float(vy or 0.0), float(vz or 0.0), bool(vp)))
    return out


# A plain QuakeWorld jump leaves the ground at vz = 270 against gravity 800, so it rises
# 270^2 / (2 * 800) = 45.5 u. Doubling that covers a jump taken off a rising surface, a ramp boost,
# or a lift-assisted hop. A run that gains more than this within half a second gained it from a
# rocket, and the movement policy has no rocket launcher — training its route geometry on a rocket
# jump asks it to reproduce a trajectory its own physics cannot produce.
MAX_RISE_PER_HALF_SECOND_U = 95.0

# The rise alone misfires on stairs (audited 2026-07-30, `evidence/rj_filter_audit.json`): QW
# stair-climbing steps *position* up to 16 u per tick with no velocity, so the RA stairs
# legitimately rise 96-119 u in half a second — 640 of the 888 ralow_to_ratop rejections were
# such climbs, with a floor within 40 u straight below every sample of the rise. A rocket jump is
# free flight: on every audited route its rise hangs 136-480 u above the nearest floor. So a
# >95 u rise is only a rocket jump when it is *airborne* — some sample after the window start
# hangs more than FLOOR_SUPPORT_U above the floor straight below it. 64 u = a plain jump's
# 45.5 u apex over the tread plus a 16 u stair step of slack. Implied per-interval vz cannot
# separate the two (grounded stair climbs show up to ~1140 u/s from the instant steps).
FLOOR_SUPPORT_U = 64.0
FLOOR_PROBE_U = 512.0  # past dm3's deepest pit, same reach as record_replay's void probe


def rise_is_floor_supported(samples: list[tuple], window_ms: int = 500) -> bool:
    """True when every >``MAX_RISE_PER_HALF_SECOND_U`` window's climb keeps a floor within
    ``FLOOR_SUPPORT_U`` below every sample after the window start — a stepped stair/ramp climb,
    not free flight. Probes the map only when called, i.e. only on runs the rise heuristic
    alone would already have rejected."""
    import numpy as np

    from .edge_signal import _floor_below

    t = np.array([s[0] for s in samples], float)
    p = np.array([[s[1], s[2], s[3]] for s in samples], np.float32)
    z = p[:, 2]
    depth = None
    for i in range(len(t)):
        for j in range(i - 1, -1, -1):
            if t[i] - t[j] > window_ms:
                break
            if z[i] - z[j] > MAX_RISE_PER_HALF_SECOND_U:
                if depth is None:
                    depth = _floor_below(p, depth=FLOOR_PROBE_U, step=8.0)
                if (depth[j + 1:i + 1] > FLOOR_SUPPORT_U).any():
                    return False
    return True


def max_rise(samples: list[tuple], window_ms: int = 500) -> float:
    """Largest z gain over any `window_ms` of the run."""
    best = 0.0
    j = 0
    for i in range(len(samples)):
        while samples[i][0] - samples[j][0] > window_ms:
            j += 1
        for k in range(j, i):
            best = max(best, samples[i][3] - samples[k][3])
    return best


# Longest sample spacing a finite difference is still a velocity over rather than an average over a
# manoeuvre. QuakeWorld's tick is 14 ms; 60 ms spans four of them, which resolves a bunny-hop cycle
# (500-900 ms) many times over while keeping the estimate local.
MAX_DIFF_SPACING_MS = 60

# Nothing in QuakeWorld moves faster than this on the horizontal plane without a rocket behind it.
# A finite difference that claims more is a sample pair straddling a gap or a teleport, not a speed.
MAX_PLAUSIBLE_UPS = 900.0


def restart_states(samples: list[tuple]) -> list[list[float]]:
    """Every sample that can be turned into a full `(x, y, z, vx, vy, vz)` state.

    Only 27,727,735 of the corpus's 907,977,350 trajectory samples carry a recorded velocity — 3.05 %
    — because an MVD holds the recording client's own velocity and not the other players'. Measured
    on the cohort runs, that leaves zero usable states on most of them.

    So velocity is taken as the position derivative, which is what it is. A central difference across
    the neighbouring samples is used where their spacing is short enough to be local
    (`MAX_DIFF_SPACING_MS`); a recorded velocity, where one exists, is preferred over the estimate.
    Pairs implying an impossible speed are dropped rather than clamped — they are a recording gap,
    and a clamped gap is a fabricated state that looks exactly like a real one.

    Kept un-simplified, unlike the polyline: the path is the route's *geometry*, but a restart state
    is a place the agent is dropped into, and thinning these would throw away precisely the mid-air
    and mid-hop states that make restarting from them worth doing.
    """
    out = []
    for i, s in enumerate(samples):
        t, x, y, z = s[0], s[1], s[2], s[3]
        if s[7]:  # recorded velocity present — always preferred over the estimate
            out.append([round(v, 2) for v in (x, y, z, s[4], s[5], s[6])])
            continue
        a = samples[i - 1] if i > 0 else None
        b = samples[i + 1] if i + 1 < len(samples) else None
        if a is not None and b is not None and (b[0] - a[0]) <= 2 * MAX_DIFF_SPACING_MS:
            lo, hi = a, b
        elif b is not None and (b[0] - t) <= MAX_DIFF_SPACING_MS:
            lo, hi = s, b
        elif a is not None and (t - a[0]) <= MAX_DIFF_SPACING_MS:
            lo, hi = a, s
        else:
            continue
        dt = (hi[0] - lo[0]) / 1000.0
        if dt <= 0:
            continue
        v = [(hi[k] - lo[k]) / dt for k in (1, 2, 3)]
        if math.hypot(v[0], v[1]) > MAX_PLAUSIBLE_UPS:
            continue
        out.append([round(q, 2) for q in (x, y, z, v[0], v[1], v[2])])
    return out


def vet(samples: list[tuple], duration_s: float) -> tuple[bool, str, dict]:
    """Is this run's sample sequence a usable path? Returns (ok, reason, stats)."""
    n = len(samples)
    if n < 8:
        return False, "too_few_samples", {"n": n}
    rate = n / max(duration_s, 1e-6)
    gaps = [math.dist(samples[i][1:4], samples[i + 1][1:4]) for i in range(n - 1)]
    biggest = max(gaps) if gaps else 0.0
    length = sum(gaps)
    rise = max_rise(samples)
    stats = {"n": n, "samples_per_s": round(rate, 1), "max_gap_u": round(biggest, 1),
             "path_len_u": round(length, 1), "max_rise_u": round(rise, 1),
             "avg_ups": round(length / max(duration_s, 1e-6), 1)}
    if rate < MIN_SAMPLES_PER_S:
        return False, "sparse", stats
    if biggest > MAX_SAMPLE_GAP_U:
        return False, "gap", stats
    if rise > MAX_RISE_PER_HALF_SECOND_U and not rise_is_floor_supported(samples):
        return False, "rocket_jump", stats
    return True, "ok", stats


def simplify(points: list[tuple[float, float, float]], tol: float = 8.0) -> list[list[float]]:
    """Ramer-Douglas-Peucker, so a 500-point recorded track becomes a path of the size the
    lookahead machinery walks cheaply without losing a corner. 8 u is well under the 64 u minimum
    lookahead, so no corner the policy can steer to is smoothed away."""
    if len(points) < 3:
        return [list(p) for p in points]

    def rdp(a: int, b: int) -> list[int]:
        if b <= a + 1:
            return [a]
        pa, pb = points[a], points[b]
        ab = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
        ab2 = sum(c * c for c in ab)
        worst, wi = -1.0, a
        for i in range(a + 1, b):
            p = points[i]
            ap = (p[0] - pa[0], p[1] - pa[1], p[2] - pa[2])
            if ab2 <= 1e-9:
                d = math.dist(p, pa)
            else:
                t = max(0.0, min(1.0, sum(ap[k] * ab[k] for k in range(3)) / ab2))
                proj = tuple(pa[k] + t * ab[k] for k in range(3))
                d = math.dist(p, proj)
            if d > worst:
                worst, wi = d, i
        if worst <= tol:
            return [a]
        return rdp(a, wi) + rdp(wi, b)

    sys.setrecursionlimit(10000)
    idx = rdp(0, len(points) - 1) + [len(points) - 1]
    return [list(points[i]) for i in idx]


def extract(registry_name: str, n_paths: int, con=None, candidate_limit: int = 400,
            max_duration_s: float | None = None) -> dict:
    """`n_paths` usable paths for one registry route, fastest first.

    `max_duration_s` (the route's gate) discards runs slower than the time we are trying to beat —
    the geometry of a run that missed the gate is not the geometry we want to learn. Combined with
    the rocket-jump filter in `vet`, what survives is *a route a human ran inside the gate using
    only movement*, which is exactly the existence proof the training needs. Measured 2026-07-29,
    the supply is not tight on any route except `tunnel_to_ra`:

        ralow_to_ratop      gate  7.71 s   373 RJ-free runs inside it, fastest 5.35 s
        ring_to_ratop       gate  9.26 s    96                          fastest 5.68 s
        lifts_to_sng_mega   gate  7.93 s  1149                          fastest 4.96 s
        sngspawn_a_to_mega  gate  9.98 s   143                          fastest 6.54 s
        quad_to_ra          gate  8.96 s   136                          fastest 6.71 s
        tunnel_to_ra        gate 12.13 s     8                          fastest 10.00 s

    `sngspawn_*_to_quad` yields nothing: all 128 candidates are rejected as `gap`, a position jump
    larger than any player movement — which is the teleporter, seen in the data.
    """
    con = con or _con()
    runs = cohort_runs(con, registry_name, limit=candidate_limit)
    if max_duration_s is not None:
        runs = [r for r in runs if r["duration_s"] <= max_duration_s]
    if not runs:
        return {"registry": registry_name, "paths": [], "rejected": [], "n_candidates": 0}
    by_run = fetch_paths(con, runs)

    kept, rejected = [], []
    for r in runs:
        key = (r["demo_key"], r["slot"], r["start_ms"])
        samples = by_run.get(key, [])
        ok, reason, stats = vet(samples, r["duration_s"])
        if not ok:
            rejected.append({"demo_key": r["demo_key"], "duration_s": r["duration_s"],
                             "reason": reason, **stats})
            continue
        pts = [(s[1], s[2], s[3]) for s in samples]
        poly = simplify(pts)
        starts = restart_states(samples)
        kept.append({"demo_key": r["demo_key"], "slot": r["slot"],
                     "duration_s": round(r["duration_s"], 3),
                     "raw_samples": stats["n"], "samples_per_s": stats["samples_per_s"],
                     "raw_len_u": stats["path_len_u"], "nodes": len(poly),
                     "n_restart_states": len(starts),
                     "path": [[round(v, 2) for v in p] for p in poly],
                     "restart_states": starts})
        if len(kept) >= n_paths:
            break

    return {"registry": registry_name, "n_candidates": len(runs), "n_paths": len(kept),
            "paths": kept, "rejected": rejected[:40],
            "reject_reasons": {k: sum(1 for x in rejected if x["reason"] == k)
                               for k in {x["reason"] for x in rejected}}}


def gate_of(registry_name: str) -> float | None:
    """The cohort gate for a registry route, via `cohort_routes` — one table of gates, not two."""
    from . import cohort_routes as C
    coh = REGISTRY_TO_COHORT.get(registry_name)
    if coh is None:
        return None
    name = coh[0] if isinstance(coh, tuple) else coh
    r = C.BY_NAME.get(name)
    return r.gate_s if r else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-paths", type=int, default=16)
    ap.add_argument("--candidates", type=int, default=2000)
    ap.add_argument("--routes", nargs="*", default=None)
    ap.add_argument("--no-gate-filter", action="store_true",
                    help="keep runs slower than the gate too (diagnostic only)")
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    con = _con()
    names = a.routes or list(REGISTRY_TO_COHORT)
    summary = []
    for name in names:
        gate = None if a.no_gate_filter else gate_of(name)
        res = extract(name, a.n_paths, con=con, candidate_limit=a.candidates, max_duration_s=gate)
        res["gate_s"] = gate
        (OUT / f"{name}.json").write_text(json.dumps(res, indent=1))
        best = res["paths"][0] if res["paths"] else None
        line = {"registry": name, "gate_s": gate, "kept": res["n_paths"],
                "candidates_inside_gate": res["n_candidates"],
                "fastest_s": best["duration_s"] if best else None,
                "fastest_path_len_u": best["raw_len_u"] if best else None,
                "reject_reasons": res.get("reject_reasons", {})}
        summary.append(line)
        print(json.dumps(line), flush=True)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
