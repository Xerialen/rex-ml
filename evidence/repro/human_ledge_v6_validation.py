#!/usr/bin/env python
"""v6-validering mot humanbaslinjen (analyst 2026-08-02) + SO-gapsanalys.

Samma 24-demoskohort som human_ledge_baseline.json. Dubbelspårning per
kandidattransit: v4-kvalificering (referens), v6-kvalificering (exakt
detektorreplikation, assert-verifierad mot jg._ring_quad_events, dt=0.051),
plus v5.1-erans perp-bandmått n_inledge (för kontinuitet med 67/646-kohorterna).

SO-gapsfrågan: den stödda SO-ledgen har lucka d_ring 330-555 (226 u). Mäter
per genuint event varifrån v6-progressionen kommer (grundade masksampel,
luftburna masksampel över landningskantens kolumner) och vad SO-misslyckanden
får för öde genom v6.

Kör:  ~/rex-ml/.venv/bin/python ~/rex-ml/evidence/repro/human_ledge_v6_validation.py
"""
import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg  # noqa: E402
from rl.jump_gates import (HEX_R, LEDGE_Z, MAX_TRANSIT_PTS, PIT_2D,
                           PIT_Z, PLAT_ZBAND, PROGRESS_D_BAND, QUAD, RING,
                           SIDE_DEADZONE, SIDE_LEDGE_MAX, SIDE_MIN_MASS_US,
                           _d2, _grounded, _on_ledge, _plat, _side)

P = "/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/*/*/*/*/*.parquet"
W = "format='mvd' and mode='4on4' and map='dm3'"
GAP_MS = 150
DT = 0.051
V4_PROGRESS = 350.0
BASE = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_baseline.json"

con = duckdb.connect()
con.execute("SET threads TO 14; SET memory_limit='20GB'")


def dual_trace(path, dt):
    out = []
    g = _grounded(path)
    cur = _plat(path[0])
    cur_grounded = bool(g[0]) if cur is not None else False
    t0 = 0
    i = 1
    while i < len(path):
        plat = _plat(path[i])
        if cur is None:
            cur, t0 = plat, i
            cur_grounded = bool(plat is not None and g[i])
            i += 1
            continue
        if plat == cur:
            t0 = i
            cur_grounded = cur_grounded or bool(g[i])
            i += 1
            continue
        outcome = None
        v4_ledge = v4_prog = False
        v4_acc = 0.0
        onto_ledge = progressed = raw_prog = False
        side_acc = 0.0
        n_inledge = 0                      # v5.1-erans perp-band (kontinuitet)
        n_mask = n_mask_g = 0
        dmask_g, dmask_air = [], []
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
                v4_ledge = True
                if abs(s) > SIDE_DEADZONE:
                    v4_acc += s
                if dd < V4_PROGRESS:
                    v4_prog = True
                if PLAT_ZBAND[0] < q[2] < PLAT_ZBAND[1] \
                        and SIDE_DEADZONE < abs(s) < SIDE_LEDGE_MAX:
                    n_inledge += 1
                if dd < PROGRESS_D_BAND:
                    raw_prog = True
                if _on_ledge(q):
                    onto_ledge = True
                    side_acc += s
                    n_mask += 1
                    n_mask_g += int(g[j])
                    (dmask_g if g[j] else dmask_air).append(dd)
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
        v6 = None
        if onto_ledge and progressed and side_ok and cur_grounded \
                and outcome in ("lyckat", "ramla", "retreat"):
            v6 = f"{cur}→{dst} {'NV' if side_acc > 0 else 'SO'}"
        elif (raw_prog or progressed) and outcome in ("lyckat", "ramla",
                                                      "retreat"):
            v6 = f"axial {cur}→{dst}"
        if v4 is not None or v6 is not None:
            out.append({
                "riktning": f"{cur}→{dst}", "utfall": outcome,
                "v4": v4, "v6": v6,
                "sida": ("NV" if side_acc > 0 else "SO") if n_mask else None,
                "mass_us": round(abs(side_acc) * dt, 1),
                "n_inledge": n_inledge, "n_mask": n_mask,
                "n_mask_grundade": n_mask_g,
                "min_d_mask_grundade": round(min(dmask_g), 0)
                if dmask_g else None,
                "min_d_mask_luft": round(min(dmask_air), 0)
                if dmask_air else None,
                "cur_grounded": cur_grounded,
                "progressed": progressed, "onto_ledge": onto_ledge,
                "side_ok": side_ok,
            })
        cur = _plat(path[j]) if j < len(path) else None
        cur_grounded = bool(cur is not None and j < len(path) and g[j])
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
            evs = dual_trace(path, DT)
            official = jg._ring_quad_events(path, dt=DT)
            mine = [{"hopp": e["v6"], "utfall": e["utfall"]}
                    for e in evs if e["v6"] is not None]
            assert mine == official, f"v6-trace != detektor demo {dk[a]}"
            n_assert += 1
            for e in evs:
                e["demo_key"] = int(dk[a])
                e["slot"] = int(sl[a])
                all_ev.append(e)
    fn = ("/home/benjamin-adm/rex-ml/evidence/repro/"
          "human_ledge_v6_validation.json")
    json.dump({"n_demos": len(keys), "demo_keys": keys, "dt": DT,
               "n_asserted_segments": n_assert, "events": all_ev},
              open(fn, "w"), indent=1, ensure_ascii=False)
    print(f"assert-verifierade segment: {n_assert}")

    def fate(e):
        if e["v6"] is None:
            return "tappad"
        return "axial" if e["v6"].startswith("axial") else "gate"

    v4ev = [e for e in all_ev if e["v4"] is not None]
    kept = [e for e in v4ev if fate(e) == "gate"]
    nya = [e for e in all_ev if e["v4"] is None and fate(e) == "gate"]
    graz = [e for e in kept if e["mass_us"] < SIDE_MIN_MASS_US]
    flip = [e for e in kept if e["v6"] != e["v4"]]
    print(f"v4-gate-event: {len(v4ev)}; v6 gate: {len(kept)} "
          f"(flippar {len(flip)}, grazers {len(graz)}); NYA (ej v4): {len(nya)}")
    curg = [e for e in v4ev if fate(e) != "gate" and e["onto_ledge"]
            and e["progressed"] and e["side_ok"] and not e["cur_grounded"]]
    print(f"förlorade ENBART på källplattformskravet: {len(curg)}")

    # Genuina kohorter (v5.1-def för kontinuitet) per sida
    for utf, tot in (("ramla", 67), ("lyckat", 646)):
        gen = [e for e in v4ev if e["n_inledge"] >= 5 and e["utfall"] == utf]
        print(f"\ngenuina band-{utf} (n_inledge>=5): n={len(gen)} "
              f"(v5.1-referens {tot})")
        for sida in ("NV", "SO"):
            sel = [e for e in gen if (e["sida"] or
                                      ("NV" if "NV" in (e["v4"] or "") else "SO"))
                   == sida]
            keptn = sum(fate(e) == "gate" for e in sel)
            print(f"  {sida}: {keptn}/{len(sel)} behållna som gate "
                  f"({100 * keptn / max(1, len(sel)):.0f}%)")
            lost = [e for e in sel if fate(e) != "gate"]
            reasons = {"ej_mask": 0, "ej_prog": 0, "ej_massa": 0,
                       "ej_källgrund": 0}
            for e in lost:
                if not e["onto_ledge"]:
                    reasons["ej_mask"] += 1
                elif not e["progressed"]:
                    reasons["ej_prog"] += 1
                elif not e["side_ok"]:
                    reasons["ej_massa"] += 1
                elif not e["cur_grounded"]:
                    reasons["ej_källgrund"] += 1
            print(f"     förlustorsak: {reasons}")
    # SO-gapsanalys: varifrån kommer progressionen i behållna SO-event?
    for utf in ("ramla", "lyckat", "retreat"):
        so = [e for e in all_ev if fate(e) == "gate" and "SO" in e["v6"]
              and e["utfall"] == utf]
        if not so:
            print(f"\nSO-{utf} behållna: 0")
            continue
        g_only = sum(1 for e in so if (e["min_d_mask_grundade"] or 9e9) < 450)
        a_only = sum(1 for e in so if (e["min_d_mask_grundade"] or 9e9) >= 450
                     and (e["min_d_mask_luft"] or 9e9) < 450)
        print(f"\nSO-{utf} behållna: {len(so)}; progression via GRUNDAT "
              f"masksampel d<450: {g_only}, enbart via LUFTBURET (över "
              f"landningskantens kolumner): {a_only}")
        dg = [e["min_d_mask_grundade"] for e in so
              if e["min_d_mask_grundade"] is not None]
        if dg:
            print(f"  min_d_mask_grundade p10/p50/p90: "
                  f"{np.percentile(dg, [10, 50, 90]).round(0)}")
    print("\nskrivet:", fn)


if __name__ == "__main__":
    main()
