#!/usr/bin/env python
"""v5-validering mot humanbaslinjen (analyst 2026-08-02).

Samma kohort som human_ledge_baseline.json (24 demos, hash-ordnade). Kör en
DUBBELSPÅRNING per kandidattransit: v4-beslutet (gamla kvalificeringen, som i
vet_ledgeprobe.py, assert-verifierad mot v4-detektorn innan den skrevs om) och
v5-beslutet (nuvarande rl.jump_gates). Transitgränserna (t0, j, utfall) är
identiska mellan versionerna — endast kvalificering/etikettering ändrades —
så event-för-event-matchning är exakt.

v5-spåret assert-verifieras mot jg._ring_quad_events på VARJE segment.

Ut: övergångsmatris v4→v5 (behållen samma sida / sidoflipp / demoterad till
axial / tappad), in-band |side_acc|-fördelningar för kalibrering av
SIDE_MIN_ACC, samt ödet för de 4 "bot-lika" marginalevent som utgjorde v4:s
falsk-SO-rat.

Kör:  ~/rex-ml/.venv/bin/python ~/rex-ml/evidence/repro/human_ledge_v5_validation.py
"""
import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg  # noqa: E402
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


def dual_trace(path):
    """Kandidattransiter med BÅDA versionernas kvalificering + mätvärden."""
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
        v5_ledge = v5_prog = raw_prog = False
        v5_acc = 0.0
        n_band = n_band_g = 0
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
                # v4-kvalificering
                v4_ledge = True
                if abs(s) > SIDE_DEADZONE:
                    v4_acc += s
                if _d2(q, dst_c) < PROGRESS_D:
                    v4_prog = True
                    raw_prog = True
                # v5-kvalificering (enbart plattformsnivån)
                if PLAT_ZBAND[0] < q[2] < PLAT_ZBAND[1]:
                    if SIDE_DEADZONE < abs(s) < SIDE_LEDGE_MAX:
                        v5_ledge = True
                        n_band += 1
                        n_band_g += int(g[j])
                    if abs(s) > SIDE_DEADZONE:
                        v5_acc += s
                    if _d2(q, dst_c) < PROGRESS_D:
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
            raw_prog = True
        dst = "quad" if cur == "ring" else "ring"
        v4 = None
        if v4_ledge and v4_prog and outcome in ("lyckat", "ramla", "retreat"):
            sd = "NV" if v4_acc > 0 else ("SO" if v4_acc < 0 else "obestämd")
            v4 = f"{cur}→{dst} {sd}"
        v5 = None
        if v5_ledge and v5_prog and abs(v5_acc) >= SIDE_MIN_ACC \
                and outcome in ("lyckat", "ramla", "retreat"):
            v5 = f"{cur}→{dst} {'NV' if v5_acc > 0 else 'SO'}"
        elif raw_prog and outcome in ("lyckat", "ramla", "retreat"):
            v5 = f"axial {cur}→{dst}"
        if v4 is not None or v5 is not None:
            out.append({"riktning": f"{cur}→{dst}", "utfall": outcome,
                        "v4": v4, "v5": v5,
                        "v4_acc": round(float(v4_acc), 1),
                        "v5_acc": round(float(v5_acc), 1),
                        "n_band": n_band, "n_band_grundade": n_band_g,
                        "t0": int(t0), "j": int(j),
                        "v5_ledge": v5_ledge, "v5_prog": v5_prog})
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
    bounds = np.flatnonzero((np.diff(dk) != 0) | (np.diff(sl) != 0)) + 1
    n_assert = 0
    for a, b in zip(np.r_[0, bounds], np.r_[bounds, len(dk)]):
        gaps = np.flatnonzero(np.diff(t[a:b]) > GAP_MS) + 1
        for c, d in zip(np.r_[0, gaps], np.r_[gaps, b - a]):
            if d - c < 10:
                continue
            path = xyz[a + c:a + d]
            evs = dual_trace(path)
            # assert: v5-kolumnen == den faktiska detektorns eventlista
            official = jg._ring_quad_events(path)
            mine = [{"hopp": e["v5"], "utfall": e["utfall"]}
                    for e in evs if e["v5"] is not None]
            assert mine == official, \
                f"v5-trace != detektor (demo {dk[a]}, slot {sl[a]})"
            n_assert += 1
            for e in evs:
                e["demo_key"] = int(dk[a])
                e["slot"] = int(sl[a])
                all_ev.append(e)
    fn = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_v5_validation.json"
    json.dump({"n_demos": len(keys), "demo_keys": keys,
               "n_asserted_segments": n_assert, "events": all_ev},
              open(fn, "w"), indent=1, ensure_ascii=False)
    print(f"assert-verifierade segment: {n_assert}")

    def fate(e):
        if e["v5"] is None:
            return "tappad"
        if e["v5"].startswith("axial"):
            return "axial"
        if e["v4"] is None:
            return "NY-gate"
        return "samma-sida" if e["v5"] == e["v4"] else "sidoflipp"

    for rikt in ("quad→ring", "ring→quad"):
        v4ev = [e for e in all_ev if e["v4"] is not None
                and e["riktning"] == rikt]
        print(f"\n== {rikt}: v4-gate-event n={len(v4ev)} ==")
        for f in ("samma-sida", "sidoflipp", "axial", "tappad"):
            sel = [e for e in v4ev if fate(e) == f]
            print(f"  {f}: {len(sel)}"
                  + (f"  (utfall: " + ", ".join(
                      f"{u}={sum(e['utfall'] == u for e in sel)}"
                      for u in ('lyckat', 'ramla', 'retreat')) + ")"
                     if sel else ""))
        nya = [e for e in all_ev if e["v4"] is None and e["v5"] is not None
               and not e["v5"].startswith("axial") and e["riktning"] == rikt]
        print(f"  v5-gate-event utan v4-motsvarighet: {len(nya)}")

    # Kalibrering: in-band |side_acc| för v4-gate-event, per öde
    v4ev = [e for e in all_ev if e["v4"] is not None]
    kept = np.array([abs(e["v5_acc"]) for e in v4ev
                     if fate(e) in ("samma-sida", "sidoflipp")])
    demoted = np.array([abs(e["v5_acc"]) for e in v4ev
                        if fate(e) in ("axial", "tappad")])
    print("\n== SIDE_MIN_ACC-kalibrering (in-band |side_acc|) ==")
    if len(kept):
        print("behållna gate-event  p1/p5/p10/p50:",
              np.percentile(kept, [1, 5, 10, 50]).round(0))
        print("  min:", kept.min())
    if len(demoted):
        print("demoterade/tappade   p50/p90/p95/p99/max:",
              np.percentile(demoted, [50, 90, 95, 99]).round(0),
              demoted.max())
    # events som demoterades ENBART pga side_ok (ledge+prog ok, massa < 300)
    only_mass = [e for e in v4ev if fate(e) in ("axial", "tappad")
                 and e["v5_ledge"] and e["v5_prog"]
                 and abs(e["v5_acc"]) < SIDE_MIN_ACC]
    print(f"demoterade ENBART av massvillkoret (<{SIDE_MIN_ACC:.0f}): "
          f"{len(only_mass)}")
    for e in sorted(only_mass, key=lambda e: -abs(e["v5_acc"]))[:10]:
        print("  ", {k: e[k] for k in ("demo_key", "slot", "v4", "utfall",
                                       "v5_acc", "n_band")})

    # De 4 "bot-lika" marginaleventen ur review 5 — deras v5-öde
    base_ev = json.load(open(BASE))["events"]
    botlike = [(e["demo_key"], e["slot"]) for e in base_ev
               if e["hopp"] == "quad→ring SO" and e["utfall"] == "ramla"
               and e["n_ledge_grundade"] == 0 and abs(e["side_acc"]) < 500]
    print("\n== v5-öde för review 5:s 4 bot-lika marginalevent ==")
    for dkk, ss in botlike:
        m = [e for e in all_ev if e["demo_key"] == dkk and e["slot"] == ss
             and e["v4"] == "quad→ring SO" and e["utfall"] == "ramla"]
        for e in m:
            print(f"  demo {dkk} slot {ss}: v5={e['v5']} "
                  f"(v5_acc={e['v5_acc']}, n_band={e['n_band']})")
    print("\nskrivet:", fn)


if __name__ == "__main__":
    main()
