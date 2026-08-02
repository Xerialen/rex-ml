#!/usr/bin/env python
"""Fördjupade v5-mått (analyst): in-band-progression och ruttprofil per
kandidattransit i humankohorten. Komplement till human_ledge_v5_validation.py.

Per v4-gate-event: min d(dst) över (a) alla transitsampel, (b) sampel på
plattformsnivån (z-band), (c) sampel i ledgebandet (dessutom 100<|perp|<300);
median |perp| och grundad andel bland z-bandsampel — för att avgöra om
demoterade event är genuina ledgekorsningar eller axelnära/yttre rutter.

Kör:  ~/rex-ml/.venv/bin/python ~/rex-ml/evidence/repro/human_ledge_v5_metrics.py
"""
import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
from rl.jump_gates import (HEX_R, LEDGE_Z, MAX_TRANSIT_PTS, PIT_2D, PIT_Z,
                           PLAT_ZBAND, PROGRESS_D, QUAD, RING, SIDE_DEADZONE,
                           SIDE_LEDGE_MAX, SIDE_MIN_ACC, _d2, _grounded,
                           _plat, _side)

P = "/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/*/*/*/*/*.parquet"
W = "format='mvd' and mode='4on4' and map='dm3'"
GAP_MS = 150
BASE = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_baseline.json"

con = duckdb.connect()
con.execute("SET threads TO 14; SET memory_limit='20GB'")


def trace_metrics(path):
    out = []
    g = _grounded(path)
    cur = _plat(path[0])
    t0 = 0
    i = 1
    while i < len(path):
        plat = _plat(path[i])
        if cur is None:
            cur, t0 = plat, i
            i += 1
            continue
        if plat == cur:
            t0 = i
            i += 1
            continue
        outcome = None
        v4_ledge = v4_prog = False
        v4_acc = v5_acc = 0.0
        v5_ledge = v5_prog = False
        band_perp, band_g = [], []
        d_all, d_band, d_ledge = [], [], []
        dst_c = QUAD if cur == "ring" else RING
        j = i
        while j < len(path) and j - t0 <= MAX_TRANSIT_PTS:
            q = path[j]
            if _d2(q, PIT_2D) > HEX_R:
                outcome = "lämnade"
                break
            if q[2] <= PIT_Z:
                outcome = "ramla"
                break
            qp = _plat(q)
            if qp is None and q[2] > LEDGE_Z:
                s = _side(q)
                dd = _d2(q, dst_c)
                d_all.append(dd)
                v4_ledge = True
                if abs(s) > SIDE_DEADZONE:
                    v4_acc += s
                if dd < PROGRESS_D:
                    v4_prog = True
                if PLAT_ZBAND[0] < q[2] < PLAT_ZBAND[1]:
                    band_perp.append(s)
                    band_g.append(bool(g[j]))
                    d_band.append(dd)
                    if SIDE_DEADZONE < abs(s) < SIDE_LEDGE_MAX:
                        v5_ledge = True
                        d_ledge.append(dd)
                    if abs(s) > SIDE_DEADZONE:
                        v5_acc += s
                    if dd < PROGRESS_D:
                        v5_prog = True
            if qp == cur:
                outcome = "retreat"
                break
            if qp is not None and qp != cur:
                outcome = "lyckat"
                break
            j += 1
        if outcome is None:
            outcome = "lämnade"
        if outcome == "lyckat":
            v4_prog = True
            v5_prog = v5_prog or v5_ledge
        dst = "quad" if cur == "ring" else "ring"
        v4 = None
        if v4_ledge and v4_prog and outcome in ("lyckat", "ramla", "retreat"):
            sd = "NV" if v4_acc > 0 else ("SO" if v4_acc < 0 else "obestämd")
            v4 = f"{cur}→{dst} {sd}"
        v5 = None
        if v5_ledge and v5_prog and abs(v5_acc) >= SIDE_MIN_ACC \
                and outcome in ("lyckat", "ramla", "retreat"):
            v5 = f"{cur}→{dst} {'NV' if v5_acc > 0 else 'SO'}"
        if v4 is not None:
            bp = np.abs(band_perp) if band_perp else np.array([np.nan])
            out.append({
                "riktning": f"{cur}→{dst}", "utfall": outcome, "v4": v4,
                "v5gate": v5 is not None,
                "v5_acc": round(float(v5_acc), 1),
                "n_band_ledge": len(d_ledge),
                "min_d_all": round(min(d_all), 0) if d_all else None,
                "min_d_band": round(min(d_band), 0) if d_band else None,
                "min_d_ledge": round(min(d_ledge), 0) if d_ledge else None,
                "median_absperp_band": round(float(np.nanmedian(bp)), 0),
                "grund_andel_band": round(float(np.mean(band_g)), 2)
                if band_g else None,
                "v5_ledge": v5_ledge, "v5_prog": v5_prog,
            })
        cur = _plat(path[j]) if j < len(path) else None
        t0 = j
        i = j + 1
    return out


def main():
    keys = json.load(open(BASE))["demo_keys"]
    kl = ",".join(map(str, keys))
    rows = con.sql(f"""
      select demo_key, slot, t, x, y, z
      from read_parquet('{P}', hive_partitioning=1)
      where {W} and demo_key in ({kl})
      order by demo_key, slot, t""").fetchnumpy()
    dk, sl = rows["demo_key"], rows["slot"]
    t = rows["t"].astype(np.int64)
    xyz = np.stack([rows["x"], rows["y"], rows["z"]], axis=1).astype(float)
    allev = []
    bounds = np.flatnonzero((np.diff(dk) != 0) | (np.diff(sl) != 0)) + 1
    for a, b in zip(np.r_[0, bounds], np.r_[bounds, len(dk)]):
        gaps = np.flatnonzero(np.diff(t[a:b]) > GAP_MS) + 1
        for c, d in zip(np.r_[0, gaps], np.r_[gaps, b - a]):
            if d - c < 10:
                continue
            for e in trace_metrics(xyz[a + c:a + d]):
                e["demo_key"] = int(dk[a])
                e["slot"] = int(sl[a])
                allev.append(e)
    fn = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_v5_metrics.json"
    json.dump(allev, open(fn, "w"), indent=1, ensure_ascii=False)

    # 1) De band-starka men bandprogressionslösa ramla-eventen
    strong = [e for e in allev if e["v5_ledge"] and not e["v5_prog"]
              and e["utfall"] == "ramla"]
    md = np.array([e["min_d_ledge"] for e in strong], dtype=float)
    print(f"bandnärvaro utan bandprogression (ramla, n={len(strong)}):")
    print("  min_d_ledge p10/p50/p90:", np.percentile(md, [10, 50, 90]).round(0),
          " min:", md.min())
    # 2) In-band min_d för GENUINT starka ledgekorsningar (n_band_ledge>=5)
    for tag, sel in (
        ("lyckade ledgekorsningar (n_band_ledge>=5)",
         [e for e in allev if e["n_band_ledge"] >= 5
          and e["utfall"] == "lyckat"]),
        ("misslyckade (ramla) med n_band_ledge>=5",
         [e for e in allev if e["n_band_ledge"] >= 5
          and e["utfall"] == "ramla"]),
    ):
        md = np.array([e["min_d_ledge"] for e in sel], dtype=float)
        print(f"{tag} n={len(sel)}: min_d_ledge p10/p50/p90 =",
              np.percentile(md, [10, 50, 90]).round(0))
        # hur många klarar in-band-progression vid olika PROGRESS-trösklar?
        for th in (350, 450, 500, 550):
            print(f"   andel med min_d_band < {th}: "
                  f"{np.mean([e['min_d_band'] < th for e in sel]):.2f}")
    # 3) Ruttprofil för demoterade LYCKADE utan bandnärvaro
    noband = [e for e in allev if not e["v5_ledge"] and e["utfall"] == "lyckat"]
    mp = np.array([e["median_absperp_band"] for e in noband], dtype=float)
    print(f"\ndemoterade lyckade utan ledgebandnärvaro (n={len(noband)}):")
    print("  median|perp| i z-band p10/p50/p90:",
          np.nanpercentile(mp, [10, 50, 90]).round(0))
    print("  andel med median|perp| < 100 (axelnära rutt):",
          float(np.nanmean(mp < 100)).__round__(2))
    print("  andel med median|perp| > 300 (yttre rutt):",
          float(np.nanmean(mp > 300)).__round__(2))
    print("\nskrivet:", fn)


if __name__ == "__main__":
    main()
