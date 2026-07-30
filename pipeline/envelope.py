"""Does the run take the route's own line, or a line no human has ever taken?

Found 2026-07-30, on the owner's review of the replays: the "passing" `window_to_rl` runs never go
through the window. 23 of 24 human runs pass the window region and none of them ever goes beyond
x = 1678; the policy goes through the window in 0 of 30 recorded runs, detours to x ≈ 2030 and
enters the RL room from the east. The strict test graded arrival and time, so a run that avoids the
route's defining jump — and pays 1.74× the human path length for it — was called GODKÄND.

The fix has to be corpus-derived, not a hand-drawn region per route (that was already tried and
rightly rejected once). The corpus defines the route's *envelope*: the union of the human paths.
The statistic is the per-run maximum distance from the run's samples to the union of the other
runs' paths — leave-one-out, so a human run is never compared against itself — and the gate for a
policy run is the human p95 of that statistic, exactly the construction the wall band uses. A run
that stays inside where humans go passes wherever inside it likes; a 350 u excursion into geometry
no demonstration has ever crossed fails, whatever its arrival time.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import race

BAND = Path("/home/benjamin-adm/rex-ml/evidence/envelope_band.json")
DENSIFY_U = 16.0


def _densify(path: np.ndarray) -> np.ndarray:
    out = []
    for i in range(len(path) - 1):
        d = float(np.linalg.norm(path[i + 1] - path[i]))
        n = max(2, int(d / DENSIFY_U))
        out.append(path[i] + (path[i + 1] - path[i]) * np.linspace(0.0, 1.0, n, endpoint=False)[:, None])
    out.append(path[-1:])
    return np.concatenate(out).astype(np.float32)


def _run_max_dist(samples: np.ndarray, cloud: np.ndarray, chunk: int = 2048) -> float:
    """Max over the run's samples of the distance to the nearest point of `cloud`."""
    worst = 0.0
    for i in range(0, len(samples), chunk):
        s = samples[i:i + chunk]
        d = np.linalg.norm(s[:, None, :] - cloud[None, :, :], axis=2).min(1)
        worst = max(worst, float(d.max()))
    return worst


def derive() -> dict:
    """The per-route envelope band, leave-one-out over the human paths. Writes :data:`BAND`."""
    out = {}
    for r in race.training_routes():
        paths = [_densify(np.asarray(p["path"], np.float32))
                 for p in race.human_paths_for(r, 10_000)]
        if len(paths) < 3:
            continue
        loo = []
        for i, p in enumerate(paths):
            cloud = np.concatenate([q for j, q in enumerate(paths) if j != i])
            loo.append(_run_max_dist(p, cloud))
        out[r.name] = {
            "n_runs": len(paths),
            "loo_max_dist_p50": round(float(np.median(loo)), 1),
            "gate_p95_u": round(float(np.percentile(loo, 95)), 1),
        }
        print(f"  {r.name:22s} {len(paths):3d} körningar  LOO-max p50 "
              f"{out[r.name]['loo_max_dist_p50']:6.1f} u  grind p95 {out[r.name]['gate_p95_u']:6.1f} u",
              flush=True)
    BAND.parent.mkdir(parents=True, exist_ok=True)
    BAND.write_text(json.dumps({
        "derived": "human paths per route; per-run max distance to the union of the other runs",
        "gate": "a policy run's max distance to the corpus union must not exceed the human p95",
        "densify_u": DENSIFY_U,
        "routes": out}, indent=1))
    print(f"skrev {BAND}")
    return out


def load_band() -> dict[str, float]:
    if not BAND.exists():
        raise FileNotFoundError(
            f"{BAND} saknas — kör `python -m pipeline.envelope` som härleder höljet ur korpusen "
            "innan något betygsätts på ruttlinje")
    return {k: v["gate_p95_u"] for k, v in json.loads(BAND.read_text())["routes"].items()}


def route_cloud(route_name: str) -> np.ndarray | None:
    """The densified union of the route's human paths, for grading policy runs against."""
    r = next((x for x in race.training_routes() if x.name == route_name), None)
    if r is None:
        return None
    paths = [_densify(np.asarray(p["path"], np.float32))
             for p in race.human_paths_for(r, 10_000)]
    return np.concatenate(paths) if paths else None


def episode_max_dists(traces: list[np.ndarray], cloud: np.ndarray,
                      sample_every: int = 4, join_band_u: float | None = None) -> list[float]:
    """Per-episode max distance to the corpus union. Subsampled in time — an excursion hundreds of
    units off the line lasts far longer than four ticks.

    `join_band_u` handles episodes that start off the corpus: the strict protocol also starts runs
    at the navmesh's approach points, which are not on the human paths, so their first seconds are
    an "excursion" by construction. With a band given, the measurement starts at the first sample
    inside it — the run is judged from where it joins the route. A run that never joins gets `inf`:
    never having been on the route at all must not grade better than leaving it once.
    """
    out = []
    for t in traces:
        if not len(t):
            continue
        pts = np.ascontiguousarray(t[::sample_every, :3])
        d = np.linalg.norm(pts[:, None, :] - cloud[None, :, :], axis=2).min(1)
        if join_band_u is None:
            out.append(float(d.max()))
            continue
        joined = np.flatnonzero(d <= join_band_u)
        out.append(float(d[joined[0]:].max()) if joined.size else float("inf"))
    return out


if __name__ == "__main__":
    derive()
