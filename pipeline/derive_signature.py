"""Let the corpus say what separates a fast run from a slow one, instead of me deciding.

Every threshold in `manoeuvres.py` is mine: 45.5 u of rise, 0.675 s of hang, 25 u/s of air gain,
3 ticks of ground contact to call two hops a chain. The physics behind the first two is real, but
*which* of those quantities matters, and how much of it, is a claim about what makes a route fast —
and that claim belongs to the 28.4 M recorded ticks, not to me.

So this asks the data directly. For one route, take every human run route-lab's cohort SQL binds,
split them at the median time, and compute per-run movement features. Whatever separates the fast
half from the slow half *is* the critical capability on that route, ranked by how strongly it
separates them. Nothing is nominated in advance: the features are the obvious kinematic ones, and
the ranking decides which of them the route actually rewards.

Effect size is Cohen's d, which is the difference in means over the pooled spread — so a feature
that differs by 40 u/s means nothing if runs vary by 200, and a feature that differs by 2 hops means
a great deal if runs vary by 1.

Sampling rate is the one filter applied, and it is a measurement property rather than a judgement:
hop chains cannot be seen at 20 Hz, because a 0.35 s flight with a 3-tick ground contact between hops
falls between samples. Runs below `MIN_HZ` are excluded and counted, never quietly dropped.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/benjamin-adm/qw-demo-miner-fix-round/qwd/v2")

from . import cohort_routes as C
from . import human_paths as HP

OUT = Path("/home/benjamin-adm/rex-ml/evidence")

# A chain is invisible below this sample rate — see the module docstring.
MIN_HZ = 55.0


def features(samples: list[tuple], duration_s: float) -> dict | None:
    """Kinematics of one recorded run. `samples` are `(t_ms, x, y, z, vx, vy, vz, vel_present)`.

    Velocity is the position derivative where the demo did not record one (only 3.05 % of the corpus
    does), so `vz == 0` — the ground proxy — is computed from the same derivative and inherits its
    resolution. That is why the sample-rate filter exists.
    """
    n = len(samples)
    if n < 16:
        return None
    t = np.array([s[0] for s in samples], dtype=np.float64) / 1000.0
    P = np.array([[s[1], s[2], s[3]] for s in samples], dtype=np.float64)
    hz = n / max(t[-1] - t[0], 1e-6)
    if hz < MIN_HZ:
        return None

    dt = np.diff(t)
    good = dt > 1e-4
    V = np.zeros_like(P)
    V[1:][good] = np.diff(P, axis=0)[good] / dt[good, None]
    sp = np.linalg.norm(V[:, :2], axis=1)
    vz = V[:, 2]
    # On the ground the vertical derivative is ~0; airborne it is not. The cut is the resolution of a
    # 77 Hz sample of a 0.35 s flight, not a tuned number.
    air = np.abs(vz) > 20.0

    # airborne segments and the chains they form
    segs = []
    i = 0
    while i < n:
        if not air[i]:
            i += 1
            continue
        j = i
        while j < n and air[j]:
            j += 1
        if j - i >= 2:
            segs.append((max(i - 1, 0), min(j, n - 1)))
        i = j + 1
    chains, cur = [], []
    for s in segs:
        if cur and (s[0] - cur[-1][1]) <= 3:
            cur.append(s)
        else:
            if len(cur) >= 2:
                chains.append(cur)
            cur = [s]
    if len(cur) >= 2:
        chains.append(cur)

    moving = sp[sp > 1]
    gains = [float(sp[a:b + 1].max() - sp[a]) for a, b in segs] if segs else [0.0]
    return {
        "duration_s": duration_s,
        "hz": hz,
        "path_u": float(np.sum(np.linalg.norm(np.diff(P, axis=0), axis=1))),
        "median_speed": float(np.median(moving)) if moving.size else 0.0,
        "p90_speed": float(np.percentile(moving, 90)) if moving.size else 0.0,
        "frac_air": float(air.mean()),
        "n_jumps": float(len(segs)),
        "n_chains": float(len(chains)),
        "longest_chain": float(max((len(c) for c in chains), default=0)),
        "chained_jump_frac": float(sum(len(c) for c in chains) / max(len(segs), 1)),
        "median_air_gain": float(np.median(gains)),
        "speed_retained": float(sp[-1] / max(sp.max(), 1e-6)),
    }


def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2 or len(b) < 2:
        return 0.0
    s = math.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1))
                  / max(len(a) + len(b) - 2, 1))
    return 0.0 if s == 0 else float((a.mean() - b.mean()) / s)


def analyse(registry: str, route: str, candidates: int = 1500) -> dict:
    con = HP._con()
    runs = HP.cohort_runs(con, registry, limit=candidates)
    by = HP.fetch_paths(con, runs)
    rows, too_sparse = [], 0
    for r in runs:
        s = by.get((r["demo_key"], r["slot"], r["start_ms"]), [])
        f = features(s, r["duration_s"])
        if f is None:
            too_sparse += 1
            continue
        rows.append(f)
    if len(rows) < 20:
        return {"route": route, "n": len(rows), "excluded_low_rate": too_sparse,
                "error": "too few runs above the sample-rate floor"}

    d = np.array([r["duration_s"] for r in rows])
    med = float(np.median(d))
    fast, slow = d <= np.percentile(d, 25), d >= np.percentile(d, 75)
    keys = [k for k in rows[0] if k not in ("duration_s", "hz")]
    table = []
    for k in keys:
        v = np.array([r[k] for r in rows], dtype=np.float64)
        table.append({
            "feature": k,
            "fast_mean": round(float(v[fast].mean()), 3),
            "slow_mean": round(float(v[slow].mean()), 3),
            "cohens_d": round(cohens_d(v[fast], v[slow]), 3),
        })
    table.sort(key=lambda x: -abs(x["cohens_d"]))
    return {"route": route, "registry": registry, "n": len(rows),
            "excluded_low_rate": too_sparse, "median_s": round(med, 3),
            "fast_quartile_s": round(float(np.percentile(d, 25)), 3),
            "slow_quartile_s": round(float(np.percentile(d, 75)), 3),
            "features": table}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", nargs="*", default=["zip-ralow-to-ratop", "zip-ring-to-ratop",
                                                    "lifts-to-sng-mega", "zip-window-to-rl"])
    ap.add_argument("--candidates", type=int, default=1500)
    a = ap.parse_args()
    out = []
    for reg in a.routes:
        coh = HP.REGISTRY_TO_COHORT[reg]
        name = coh[0] if isinstance(coh, tuple) else coh
        res = analyse(reg, name, a.candidates)
        out.append(res)
        if "error" in res:
            print(f"{name}: {res['error']} ({res['excluded_low_rate']} under {MIN_HZ:.0f} Hz)")
            continue
        print(f"\n{name}  n={res['n']} körningar över {MIN_HZ:.0f} Hz "
              f"({res['excluded_low_rate']} uteslutna), snabb kvartil <= {res['fast_quartile_s']} s, "
              f"långsam >= {res['slow_quartile_s']} s")
        print(f"  {'egenskap':20s} {'snabba':>9} {'långsamma':>10} {'Cohens d':>9}")
        for f in res["features"][:8]:
            print(f"  {f['feature']:20s} {f['fast_mean']:9.2f} {f['slow_mean']:10.2f} "
                  f"{f['cohens_d']:9.2f}")
    OUT.mkdir(exist_ok=True)
    (OUT / "fast_vs_slow_signature.json").write_text(json.dumps(out, indent=1))
    print(f"\nskrev {OUT / 'fast_vs_slow_signature.json'}")


if __name__ == "__main__":
    main()
