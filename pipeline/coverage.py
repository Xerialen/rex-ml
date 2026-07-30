"""How much of the problem a test actually covers — and a guard that makes it impossible to publish
a result that does not say.

The finding this exists for, measured 2026-07-29. Routes were planned to the rocket launcher from
665 open points scattered across the whole of dm3. 293 of them connected. **All 293 entered the RL
area through the same point**, (1606, 449, -88). The navmesh models exactly one approach to that
item, so every route we can plan to it shares its final stretch — and our single test start uses that
stretch too.

The human reference does not. Its recorded path is 1215 u where the mesh's is 2002 u for the same
journey, and 200 u out from the launcher the player is at z = -31 and falling while the mesh route is
already at z = -88 on the floor. The person drops in; the mesh walks around. That is a second way
into the room, and nothing in our route set can see it.

Why this is decisive rather than merely interesting:

  * **The route set cannot be diversified by adding routes.** Every route to an item converges on the
    same final approach, so a larger route table buys no new behaviour near the goal.
  * **64 attempts were 1 trajectory.** Greedy decoding from a fixed start is deterministic, and the
    replay recorder found exactly one distinct path among 64 episodes on every route. p90 equalled
    the median everywhere, which looked like consistency and was actually an absence of sampling.
  * **On a live server the bot arrives from wherever the fight left it**, not from our one start.
    Nothing we have measured speaks to that case, and every metric would keep improving while the
    capability did not.

So: a number without its coverage is not a result. `attach()` refuses to let one out the door.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def _cluster(points: np.ndarray, threshold: float) -> np.ndarray:
    """Single-link clustering. Two entry points further apart than a doorway is wide are two
    doorways; anything closer is the same one seen twice."""
    n = len(points)
    label = -np.ones(n, dtype=int)
    c = 0
    for i in range(n):
        if label[i] >= 0:
            continue
        stack, label[i] = [i], c
        while stack:
            j = stack.pop()
            d = np.linalg.norm(points - points[j], axis=1)
            for k in np.flatnonzero((d <= threshold) & (label < 0)):
                label[k] = c
                stack.append(k)
        c += 1
    return label


def mesh_approaches(map_path: str, target, n_probes: int = 3000, room_radius: float = 320.0,
                    doorway: float = 96.0, seed: int = 0) -> dict:
    """How many distinct ways into the target's neighbourhood the navmesh models.

    Probes are scattered over the map's open space, a route is planned from each to `target`, and the
    first path node inside `room_radius` is that route's entry point. Clustering those gives the
    number of approaches the mesh can actually express — which is the ceiling on how much variety any
    route table built on it can contain.
    """
    import rex_env
    rng = np.random.default_rng(seed)
    g = np.asarray(target, dtype=np.float32)
    lo = g - np.array([2600, 2600, 700], dtype=np.float32)
    hi = g + np.array([2600, 2600, 700], dtype=np.float32)
    P = (lo + (hi - lo) * rng.uniform(size=(n_probes, 3))).astype(np.float32)
    P = P[np.asarray(rex_env.PyVecEnv.points_open(map_path, P))]
    paths = rex_env.PyVecEnv.plan_many(map_path, [tuple(map(float, p)) for p in P],
                                       tuple(map(float, g)))
    entries = []
    for p in paths:
        if not p:
            continue
        A = np.asarray(p, dtype=np.float32)
        d = np.linalg.norm(A - g, axis=1)
        inside = np.flatnonzero(d <= room_radius)
        if len(inside):
            entries.append(A[inside[0]])
    if not entries:
        return {"probes": int(len(P)), "routes": 0, "approaches": 0, "centres": []}
    E = np.asarray(entries, dtype=np.float32)
    lab = _cluster(E, doorway)
    centres = []
    for c in range(lab.max() + 1):
        m = lab == c
        centres.append({"centre": [round(float(v), 1) for v in E[m].mean(0)],
                        "routes": int(m.sum()), "share": round(float(m.mean()), 3)})
    centres.sort(key=lambda x: -x["routes"])
    return {"probes": int(len(P)), "routes": int(len(E)), "approaches": len(centres),
            "room_radius_u": room_radius, "doorway_u": doorway, "centres": centres}


def which_approach(map_path: str, start, target, approaches: dict,
                   room_radius: float = 320.0) -> int | None:
    """Index into `approaches['centres']` of the approach a given start actually uses, or None."""
    import rex_env
    g = np.asarray(target, dtype=np.float32)
    p = rex_env.PyVecEnv.plan_many(map_path, [tuple(map(float, start))], tuple(map(float, g)))[0]
    if not p:
        return None
    A = np.asarray(p, dtype=np.float32)
    inside = np.flatnonzero(np.linalg.norm(A - g, axis=1) <= room_radius)
    if not len(inside):
        return None
    e = A[inside[0]]
    d = [np.linalg.norm(e - np.asarray(c["centre"], dtype=np.float32))
         for c in approaches["centres"]]
    return int(np.argmin(d))


def effective_n(trajectories: list[np.ndarray], quantise: float = 1.0) -> int:
    """Distinct trajectories among the attempts — the real sample size.

    Reported next to the attempt count everywhere, because 64 attempts that produce one path are one
    sample and every spread statistic computed over them is a statement about nothing.
    """
    seen = set()
    for t in trajectories:
        seen.add(np.round(np.asarray(t, dtype=np.float64) / quantise).astype(np.int64).tobytes())
    return len(seen)


def attach(result: dict, *, attempts: int, distinct: int, approaches_modelled: int,
           approaches_tested: int, note: str = "") -> dict:
    """Attach a coverage block to a result, with warnings that name the specific way it is thin.

    Every evidence writer in this project calls this. `require()` below refuses to serialise a result
    that has not, which is what makes the rule structural rather than a habit.
    """
    warnings = []
    if attempts > 1 and distinct <= 1:
        warnings.append(
            f"{attempts} attempts produced {distinct} distinct trajectory — the effective sample "
            f"size is {distinct}, and any spread statistic (p90, worst case, variance) over these "
            f"describes the decode rule, not the policy")
    if approaches_modelled and approaches_tested < approaches_modelled:
        warnings.append(
            f"{approaches_tested} of {approaches_modelled} modelled approaches to the target were "
            f"exercised")
    if approaches_modelled <= 1:
        warnings.append(
            "the navmesh models a single approach to this target, so no route table built on it can "
            "test more than one way in; the map itself has more")
    result["coverage"] = {
        "attempts": attempts,
        "distinct_trajectories": distinct,
        "effective_n": distinct,
        "approaches_modelled": approaches_modelled,
        "approaches_tested": approaches_tested,
        "note": note,
        "warnings": warnings,
    }
    return result


def require(results: list[dict], path: str | Path) -> None:
    """Write evidence only if every row declares its coverage.

    A hard failure, not a warning. The mistake this prevents is not "forgot to add a field" — it is
    publishing a table of medians and p90s that silently rests on one sample, which is exactly what
    happened before this module existed and which looked completely healthy at the time.
    """
    missing = [r.get("name", "?") for r in results if "coverage" not in r]
    if missing:
        raise ValueError(
            "refusing to write evidence: no coverage block on " + ", ".join(map(str, missing)) +
            " — call coverage.attach() on every row first")
    Path(path).write_text(json.dumps(results, indent=1, default=float))


def banner(results: list[dict]) -> str:
    """One block of text naming every coverage problem across a result set, for the run log."""
    lines = []
    for r in results:
        for w in r.get("coverage", {}).get("warnings", []):
            lines.append(f"  {r.get('name', '?')}: {w}")
    if not lines:
        return "coverage: no warnings"
    return "COVERAGE WARNINGS\n" + "\n".join(lines)
