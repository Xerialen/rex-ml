#!/usr/bin/env python
"""v6.1-slutvalidering mot humanbaslinjen (analyst 2026-08-02).

Driftvillkoret ur evidence/analyst_v6_validation.md: 662 gate-event /
42 av 43 golvförankrade genuina ramla / 0 grazers / ≤1 insläpp.

Dubbelspårning v4 vs v6.1 (EXAKT detektorreplikation inkl. att förankrat fall
ERSÄTTER in-mask-progressionen för ramla och att min_d_all räknas över ALLA
transitsampel); assert mot jg._ring_quad_events (dt=0.051) per segment.

Kör:  ~/rex-ml/.venv/bin/python ~/rex-ml/evidence/repro/human_ledge_v61_final.py
"""
import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg  # noqa: E402
from rl.jump_gates import (HEX_R, LEDGE_Z, MAX_TRANSIT_PTS, PIT_2D, PIT_Z,
                           PLAT_ZBAND, PROGRESS_D_BAND, QUAD, RING,
                           SIDE_DEADZONE, SIDE_LEDGE_MAX, SIDE_MIN_MASS_US,
                           _d2, _grounded, _on_ledge, _plat, _side)

P = "/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/*/*/*/*/*.parquet"
W = "format='mvd' and mode='4on4' and map='dm3'"
GAP_MS = 150
DT = 0.051
BASE = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_baseline.json"

con = duckdb.connect()
con.execute("SET threads TO 14; SET memory_limit='20GB'")


def dual_trace(path, dt):
    out = []
    g = _grounded(path)
    cur = _plat(path[0])
    curg = bool(g[0]) if cur is not None else False
    t0, i = 0, 1
    while i < len(path):
        plat = _plat(path[i])
        if cur is None:
            cur, t0 = plat, i
            curg = bool(plat is not None and g[i])
            i += 1
            continue
        if plat == cur:
            t0 = i
            curg = curg or bool(g[i])
            i += 1
            continue
        outcome = None
        v4l = v4p = False
        v4a = 0.0
        onto = prog = raw = anchored = False
        acc = 0.0
        min_d_all = float("inf")
        n_inledge = n_mask = n_mask_g = 0
        dst_c = QUAD if cur == "ring" else RING
        j = i
        while j < len(path) and j - t0 <= MAX_TRANSIT_PTS:
            q = path[j]
            min_d_all = min(min_d_all, _d2(q, dst_c))
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
                v4l = True
                if abs(s) > SIDE_DEADZONE:
                    v4a += s
                if dd < 350.0:
                    v4p = True
                if PLAT_ZBAND[0] < q[2] < PLAT_ZBAND[1] \
                        and SIDE_DEADZONE < abs(s) < SIDE_LEDGE_MAX:
                    n_inledge += 1
                if dd < PROGRESS_D_BAND:
                    raw = True
                if _on_ledge(q):
                    onto = True
                    acc += s
                    n_mask += 1
                    if g[j]:
                        anchored = True
                        n_mask_g += 1
                    if dd < PROGRESS_D_BAND:
                        prog = True
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
            v4p = True
            prog = prog or onto
            raw = True
        if outcome == "ramla":
            prog = (min_d_all < PROGRESS_D_BAND) and anchored
        side_ok = abs(acc) * dt >= SIDE_MIN_MASS_US
        dst = "quad" if cur == "ring" else "ring"
        v4 = None
        if v4l and v4p and outcome in ("lyckat", "ramla", "retreat"):
            sd = "NV" if v4a > 0 else ("SO" if v4a < 0 else "obestämd")
            v4 = f"{cur}→{dst} {sd}"
        v61 = None
        if onto and prog and side_ok and curg \
                and outcome in ("lyckat", "ramla", "retreat"):
            v61 = f"{cur}→{dst} {'NV' if acc > 0 else 'SO'}"
        elif (raw or prog) and outcome in ("lyckat", "ramla", "retreat"):
            v61 = f"axial {cur}→{dst}"
        if v4 is not None or v61 is not None:
            out.append({"utfall": outcome, "v4": v4, "v61": v61,
                        "sida": "NV" if acc > 0 else "SO",
                        "mass_us": round(abs(acc) * dt, 1),
                        "n_inledge": n_inledge, "n_mask": n_mask,
                        "n_mask_grundade": n_mask_g, "anchored": anchored,
                        "min_d_all": round(min_d_all, 0)})
        cur = _plat(path[j]) if j < len(path) else None
        curg = bool(cur is not None and j < len(path) and g[j])
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
    tt = rows["t"].astype(np.int64)
    xyz = np.stack([rows["x"], rows["y"], rows["z"]], axis=1).astype(float)
    all_ev = []
    n_assert = 0
    bounds = np.flatnonzero((np.diff(dk) != 0) | (np.diff(sl) != 0)) + 1
    for a, b in zip(np.r_[0, bounds], np.r_[bounds, len(dk)]):
        gaps = np.flatnonzero(np.diff(tt[a:b]) > GAP_MS) + 1
        for c, d in zip(np.r_[0, gaps], np.r_[gaps, b - a]):
            if d - c < 10:
                continue
            path = xyz[a + c:a + d]
            evs = dual_trace(path, DT)
            official = jg._ring_quad_events(path, dt=DT)
            mine = [{"hopp": e["v61"], "utfall": e["utfall"]}
                    for e in evs if e["v61"] is not None]
            assert mine == official, f"v6.1-trace != detektor demo {dk[a]}"
            n_assert += 1
            for e in evs:
                e["demo_key"] = int(dk[a])
                e["slot"] = int(sl[a])
                all_ev.append(e)
    fn = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_v61_final.json"
    json.dump({"n_demos": len(keys), "demo_keys": keys, "dt": DT,
               "n_asserted_segments": n_assert, "events": all_ev},
              open(fn, "w"), indent=1, ensure_ascii=False)
    print(f"assert-verifierade segment: {n_assert}")

    def gate(e):
        return e["v61"] is not None and not e["v61"].startswith("axial")

    tot = sum(gate(e) for e in all_ev)
    graz = sum(1 for e in all_ev if gate(e) and e["mass_us"] < SIDE_MIN_MASS_US)
    # golvförankrade genuina ramla: bandgenuina (n_inledge>=5, v4) med anchored
    genr = [e for e in all_ev if e["v4"] is not None and e["n_inledge"] >= 5
            and e["utfall"] == "ramla"]
    anch = [e for e in genr if e["anchored"]]
    kept = sum(gate(e) for e in anch)
    # insläpp: gate-ramla som varken är v6-klass (in-mask-prog fanns inte kvar
    # att mäta här) eller bandgenuina — dvs n_inledge<5
    junk = [e for e in all_ev if gate(e) and e["utfall"] == "ramla"
            and e["n_inledge"] < 5]
    print(f"\nDRIFTVILLKORET: 662 gate / 42 av 43 förankrade ramla / "
          f"0 grazers / <=1 insläpp")
    print(f"UTFALL:        {tot} gate / {kept} av {len(anch)} förankrade "
          f"ramla / {graz} grazers / {len(junk)} insläpp")
    for e in junk:
        print("  insläpp:", {k: e[k] for k in
                             ("demo_key", "slot", "v61", "utfall", "n_mask",
                              "n_mask_grundade", "mass_us", "min_d_all")})
    ram = [e for e in all_ev if gate(e) and e["utfall"] == "ramla"]
    lyck = [e for e in all_ev if gate(e) and e["utfall"] == "lyckat"]
    ret = [e for e in all_ev if gate(e) and e["utfall"] == "retreat"]
    print(f"\ngate-sammansättning: lyckat {len(lyck)}, ramla {len(ram)} "
          f"(NV {sum('NV' in e['v61'] for e in ram)}, "
          f"SO {sum('SO' in e['v61'] for e in ram)}), retreat {len(ret)}")
    print(f"genuina ramla totalt (67-kohorten): "
          f"{sum(gate(e) for e in genr)}/{len(genr)}")


if __name__ == "__main__":
    main()
