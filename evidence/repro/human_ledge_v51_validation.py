#!/usr/bin/env python
"""v5.1-validering mot humanbaslinjen (analyst 2026-08-02, slutvillkoret i
evidence/analyst_v5_validation.md) + geometrimått för ep5/ep14-granskningen.

Samma 24-demoskohort. Dubbelspårning v4 vs v5.1 (exakt detektorreplikation,
assert-verifierad mot jg._ring_quad_events med dt=0.051 på varje segment).
Utöver retention mäts per event: in-ledge-sampel (100<|perp|<300 i z-bandet),
grundade sådana, min dPit bland dem (gropöverflygning?), max dPit i transiten
(meanderloop?), min_d in-band/in-ledge — diskriminatorerna för ep5- och
ep14-klasserna. Global kalibrering: dPit-fördelning för GRUNDADE mänskliga
in-ledge-sampel (var ligger fysiska ledgegolvet relativt gropcentrum).

Kör:  ~/rex-ml/.venv/bin/python ~/rex-ml/evidence/repro/human_ledge_v51_validation.py
"""
import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg  # noqa: E402
from rl.jump_gates import (HEX_R, LEDGE_Z, MAX_TRANSIT_PTS, PIT_2D, PIT_Z,
                           PLAT_ZBAND, PROGRESS_D, PROGRESS_D_BAND, QUAD,
                           RING, SIDE_DEADZONE, SIDE_LEDGE_MAX,
                           SIDE_MIN_MASS_US, _d2, _grounded, _plat, _side)

P = "/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/*/*/*/*/*.parquet"
W = "format='mvd' and mode='4on4' and map='dm3'"
GAP_MS = 150
DT_HUMAN = 0.051
BASE = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_baseline.json"

con = duckdb.connect()
con.execute("SET threads TO 14; SET memory_limit='20GB'")

ledge_floor_dpit = []   # global: dPit för grundade in-ledge-sampel


def dual_trace(path, dt):
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
        v4_acc = 0.0
        onto_ledge = progressed = raw_prog = False
        side_acc = 0.0
        n_band = n_inledge = n_inledge_g = 0
        dpit_inledge, dpit_all = [], []
        d_band, d_inledge = [], []
        dst_c = QUAD if cur == "ring" else RING
        j = i
        while j < len(path) and j - t0 <= MAX_TRANSIT_PTS:
            q = path[j]
            dpit = _d2(q, PIT_2D)
            if dpit > HEX_R:
                outcome = "lämnade"
                break
            if q[2] <= PIT_Z:
                outcome = "ramla"
                break
            qp = _plat(q)
            if qp is None and q[2] > LEDGE_Z:
                dpit_all.append(dpit)
                s = _side(q)
                dd = _d2(q, dst_c)
                v4_ledge = True
                if abs(s) > SIDE_DEADZONE:
                    v4_acc += s
                if dd < PROGRESS_D:
                    v4_prog = True
                    raw_prog = True
                if PLAT_ZBAND[0] < q[2] < PLAT_ZBAND[1]:
                    n_band += 1
                    d_band.append(dd)
                    if SIDE_DEADZONE < abs(s) < SIDE_LEDGE_MAX:
                        onto_ledge = True
                        n_inledge += 1
                        n_inledge_g += int(g[j])
                        dpit_inledge.append(dpit)
                        d_inledge.append(dd)
                        if g[j]:
                            ledge_floor_dpit.append(dpit)
                    if abs(s) > SIDE_DEADZONE:
                        side_acc += s
                    if dd < PROGRESS_D_BAND:
                        progressed = True
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
            progressed = progressed or onto_ledge
            raw_prog = True
        side_ok = abs(side_acc) * dt >= SIDE_MIN_MASS_US
        dst = "quad" if cur == "ring" else "ring"
        v4 = None
        if v4_ledge and v4_prog and outcome in ("lyckat", "ramla", "retreat"):
            sd = "NV" if v4_acc > 0 else ("SO" if v4_acc < 0 else "obestämd")
            v4 = f"{cur}→{dst} {sd}"
        v51 = None
        if onto_ledge and progressed and side_ok \
                and outcome in ("lyckat", "ramla", "retreat"):
            v51 = f"{cur}→{dst} {'NV' if side_acc > 0 else 'SO'}"
        elif (raw_prog or progressed) and outcome in ("lyckat", "ramla",
                                                      "retreat"):
            v51 = f"axial {cur}→{dst}"
        if v4 is not None or v51 is not None:
            out.append({
                "riktning": f"{cur}→{dst}", "utfall": outcome,
                "v4": v4, "v51": v51,
                "mass_us": round(abs(side_acc) * dt, 1),
                "n_band": n_band, "n_inledge": n_inledge,
                "n_inledge_grundade": n_inledge_g,
                "min_dpit_inledge": round(min(dpit_inledge), 0)
                if dpit_inledge else None,
                "max_dpit": round(max(dpit_all), 0) if dpit_all else None,
                "min_d_band": round(min(d_band), 0) if d_band else None,
                "min_d_inledge": round(min(d_inledge), 0)
                if d_inledge else None,
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
    all_ev = []
    n_assert = 0
    bounds = np.flatnonzero((np.diff(dk) != 0) | (np.diff(sl) != 0)) + 1
    for a, b in zip(np.r_[0, bounds], np.r_[bounds, len(dk)]):
        gaps = np.flatnonzero(np.diff(t[a:b]) > GAP_MS) + 1
        for c, d in zip(np.r_[0, gaps], np.r_[gaps, b - a]):
            if d - c < 10:
                continue
            path = xyz[a + c:a + d]
            evs = dual_trace(path, DT_HUMAN)
            official = jg._ring_quad_events(path, dt=DT_HUMAN)
            mine = [{"hopp": e["v51"], "utfall": e["utfall"]}
                    for e in evs if e["v51"] is not None]
            assert mine == official, f"v5.1-trace != detektor demo {dk[a]}"
            n_assert += 1
            for e in evs:
                e["demo_key"] = int(dk[a])
                e["slot"] = int(sl[a])
                all_ev.append(e)
    fn = ("/home/benjamin-adm/rex-ml/evidence/repro/"
          "human_ledge_v51_validation.json")
    json.dump({"n_demos": len(keys), "demo_keys": keys,
               "n_asserted_segments": n_assert, "dt": DT_HUMAN,
               "events": all_ev,
               "ledge_floor_dpit_grundade": [round(x, 0) for x in
                                             ledge_floor_dpit]},
              open(fn, "w"), indent=1, ensure_ascii=False)
    print(f"assert-verifierade segment: {n_assert}")

    def fate(e):
        if e["v51"] is None:
            return "tappad"
        if e["v51"].startswith("axial"):
            return "axial"
        return "gate"

    v4ev = [e for e in all_ev if e["v4"] is not None]
    kept = [e for e in v4ev if fate(e) == "gate"]
    flips = [e for e in kept if e["v51"] != e["v4"]]
    nya = [e for e in all_ev if e["v4"] is None and fate(e) == "gate"]
    graz = [e for e in v4ev if fate(e) == "gate" and e["mass_us"] < 14.0]
    print(f"v4-gate-event: {len(v4ev)}; v5.1 behåller som gate: {len(kept)} "
          f"(sidoflippar {len(flips)}, grazers insläppta {len(graz)})")
    genF = [e for e in v4ev if e["n_inledge"] >= 5 and e["utfall"] == "ramla"]
    genS = [e for e in v4ev if e["n_inledge"] >= 5 and e["utfall"] == "lyckat"]
    print(f"genuina band-ramla (n_inledge>=5, n={len(genF)}): behållna "
          f"{sum(fate(e) == 'gate' for e in genF)}")
    print(f"genuina band-lyckade (n={len(genS)}): behållna "
          f"{sum(fate(e) == 'gate' for e in genS)}")
    print(f"\nNYA gate-event utan v4-motsvarighet (ep14-klassen?): {len(nya)}")
    for e in sorted(nya, key=lambda e: -e["mass_us"])[:12]:
        print("  ", {k: e[k] for k in ("demo_key", "slot", "v51", "utfall",
                                       "mass_us", "n_inledge",
                                       "n_inledge_grundade", "min_d_band",
                                       "max_dpit")})
    # ep5/ep14-diskriminatorer på humanreferensen (genuina band-ramla)
    for tag, sel in (("genuina band-ramla", genF),
                     ("genuina band-lyckade", genS)):
        if not sel:
            continue
        ig = np.array([e["n_inledge_grundade"] for e in sel])
        mp = np.array([e["min_dpit_inledge"] for e in sel], dtype=float)
        xp = np.array([e["max_dpit"] for e in sel], dtype=float)
        print(f"\n{tag} (n={len(sel)}): inledge-grundade p10/p50/p90 = "
              f"{np.percentile(ig, [10, 50, 90]).round(0)}, andel med 0: "
              f"{(ig == 0).mean():.2f}")
        print(f"  min_dpit_inledge p5/p50: {np.nanpercentile(mp, [5, 50]).round(0)}"
              f"   max_dpit p50/p95: {np.nanpercentile(xp, [50, 95]).round(0)}")
    lf = np.array(ledge_floor_dpit)
    if len(lf):
        print(f"\nGRUNDADE in-ledge-sampel (globalt, n={len(lf)}): dPit "
              f"p1/p5/p50/p95 = {np.percentile(lf, [1, 5, 50, 95]).round(0)}")
    print("\nskrivet:", fn)


if __name__ == "__main__":
    main()
