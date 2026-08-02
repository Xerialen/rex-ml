#!/usr/bin/env python
"""v7-omkalibrering av humanbaslinjen (analyst, ÄGARBESLUT 2026-08-02 ~18:30).

Ägardefinitionen: ring↔quad-gaten = plattform→plattform PÅ ANGIVEN SIDA utan
att ramla i gropen; sidovägen omfattar HELA sidogolvet inkl. ytterkanten
(mask |perp| 100-460). v7 lägger dessutom landningsbekräftelse på lyckat
(>=1 grundat sampel på dst-plattformen inom 27 sampel, annars ramla/lämnade).

Dubbelspårning v6.1 (mask300, utan landningsbekräftelse) vs v7 (mask460 +
landningsbekräftelse) i SAMMA transitloop ⇒ exakta övergångar per transit.
v7-spåret assertas mot jg._ring_quad_events (dt=0.051) per segment.

Kör:  cd ~/rex-ml && .venv/bin/python evidence/repro/human_ledge_v7_baseline.py
Ut:   evidence/repro/human_ledge_v7_baseline.json
"""
import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg  # noqa: E402
from rl.jump_gates import (HEX_R, LEDGE_VOX, LEDGE_Z, LEDGE_Z_ABOVE,
                           LEDGE_Z_BELOW, MAX_TRANSIT_PTS, PIT_2D, PIT_Z,
                           PROGRESS_D_BAND, QUAD, RING, SIDE_MIN_MASS_US,
                           _d2, _grounded, _on_ledge, _plat, _side)

assert jg.SIDE_LEDGE_MAX == 460.0, "detta skript förutsätter v7-masken"

P = "/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/*/*/*/*/*.parquet"
W = "format='mvd' and mode='4on4' and map='dm3'"
GAP_MS = 150
DT = 0.051
CONFIRM_PTS = 27
BASE = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_baseline.json"

# --- mask300 (v6.1:s smala ledgeband) som delmängd av v7-centers ---
_G300 = None


def _grid300():
    global _G300
    if _G300 is None:
        cs = jg.ledge_centers()
        cs = cs[np.abs(np.array([_side(c) for c in cs])) < 300.0]
        g = {}
        for c in cs:
            g.setdefault((int(c[0] // LEDGE_VOX), int(c[1] // LEDGE_VOX)),
                         []).append(float(c[2]))
        _G300 = g
    return _G300


def _on_ledge300(p):
    zs = _grid300().get((int(p[0] // LEDGE_VOX), int(p[1] // LEDGE_VOX)))
    if not zs:
        return False
    return any(-LEDGE_Z_BELOW <= p[2] - cz <= LEDGE_Z_ABOVE for cz in zs)


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
        outcome61 = outcome7 = None
        raw = False
        min_d_all = float("inf")
        min_d_pit = float("inf")
        # per mask: [onto, prog, anchored, acc, n_mask, n_mask_g]
        m61 = dict(onto=False, prog=False, anch=False, acc=0.0, nm=0, nmg=0)
        m7 = dict(onto=False, prog=False, anch=False, acc=0.0, nm=0, nmg=0)
        wide_only_mask = 0                 # v7-masksampel som INTE är i mask300
        dst_c = QUAD if cur == "ring" else RING
        j = i
        while j < len(path) and j - t0 <= MAX_TRANSIT_PTS:
            q = path[j]
            min_d_all = min(min_d_all, _d2(q, dst_c))
            min_d_pit = min(min_d_pit, _d2(q, PIT_2D))
            if _d2(q, PIT_2D) > HEX_R:
                outcome61 = outcome7 = "lämnade"
                break
            if q[2] <= PIT_Z:
                outcome61 = outcome7 = "ramla"
                break
            qp = _plat(q)
            if qp is None and q[2] > LEDGE_Z:
                s = _side(q)
                dd = _d2(q, dst_c)
                if dd < PROGRESS_D_BAND:
                    raw = True
                in7 = _on_ledge(q)
                in61 = in7 and _on_ledge300(q)
                if in7 and not in61:
                    wide_only_mask += 1
                for m, hit in ((m61, in61), (m7, in7)):
                    if hit:
                        m["onto"] = True
                        m["acc"] += s
                        m["nm"] += 1
                        if g[j]:
                            m["anch"] = True
                            m["nmg"] += 1
                        if dd < PROGRESS_D_BAND:
                            m["prog"] = True
            if qp == cur:
                outcome61 = outcome7 = "retreat"
                break
            if qp is not None and qp != cur:
                outcome61 = "lyckat"
                # v7-landningsbekräftelse
                confirmed = fell = False
                for j2 in range(j, min(len(path), j + CONFIRM_PTS)):
                    if path[j2][2] <= PIT_Z:
                        fell = True
                        break
                    if _plat(path[j2]) == qp and g[j2]:
                        confirmed = True
                        break
                outcome7 = "lyckat" if confirmed else \
                    ("ramla" if fell else "lämnade")
                break
            j += 1
        if outcome61 is None:
            outcome61 = outcome7 = "lämnade"

        def label(m, outcome):
            prog, raw2 = m["prog"], raw
            if outcome == "lyckat":
                prog = prog or m["onto"]
                raw2 = True
            if outcome == "ramla":
                prog = (min_d_all < PROGRESS_D_BAND) and m["anch"]
            side_ok = abs(m["acc"]) * dt >= SIDE_MIN_MASS_US
            dst = "quad" if cur == "ring" else "ring"
            if m["onto"] and prog and side_ok and curg \
                    and outcome in ("lyckat", "ramla", "retreat"):
                return f"{cur}→{dst} {'NV' if m['acc'] > 0 else 'SO'}"
            if (raw2 or prog) and outcome in ("lyckat", "ramla", "retreat"):
                return f"axial {cur}→{dst}"
            return None

        l61 = label(m61, outcome61)
        l7 = label(m7, outcome7)
        if l61 is not None or l7 is not None:
            out.append({
                "v61": l61, "utfall61": outcome61,
                "v7": l7, "utfall7": outcome7,
                "mass7_us": round(abs(m7["acc"]) * dt, 1),
                "mass61_us": round(abs(m61["acc"]) * dt, 1),
                "n_mask7": m7["nm"], "n_mask7_grundade": m7["nmg"],
                "anchored7": m7["anch"],
                "wide_only_mask": wide_only_mask,
                "min_d_all": round(min_d_all, 0),
                "min_d_pit": round(min_d_pit, 0),
            })
        cur = _plat(path[j]) if j < len(path) else None
        curg = bool(cur is not None and j < len(path) and g[j])
        t0 = j
        i = j + 1
    return out


def main():
    keys = json.load(open(BASE))["demo_keys"]
    kl = ",".join(map(str, keys))
    con = duckdb.connect()
    con.execute("SET threads TO 14; SET memory_limit='20GB'")
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
            official = [{"hopp": e["hopp"], "utfall": e["utfall"]}
                        for e in jg._ring_quad_events(path, dt=DT)]
            mine = [{"hopp": e["v7"], "utfall": e["utfall7"]}
                    for e in evs if e["v7"] is not None]
            assert mine == official, f"v7-trace != detektor demo {dk[a]}"
            n_assert += 1
            for e in evs:
                e["demo_key"] = int(dk[a])
                e["slot"] = int(sl[a])
                all_ev.append(e)
    fn = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_v7_baseline.json"
    json.dump({"n_demos": len(keys), "demo_keys": keys, "dt": DT,
               "n_asserted_segments": n_assert, "events": all_ev},
              open(fn, "w"), indent=1, ensure_ascii=False)
    print(f"assert-verifierade segment: {n_assert}, event: {len(all_ev)}")

    def gate7(e):
        return e["v7"] is not None and not e["v7"].startswith("axial")

    def gate61(e):
        return e["v61"] is not None and not e["v61"].startswith("axial")

    g7 = [e for e in all_ev if gate7(e)]
    print(f"\n== v7-GATEBASLINJE (24-demoskohorten, dt {DT}) ==")
    from collections import Counter
    comp = Counter((e["v7"], e["utfall7"]) for e in g7)
    for k in sorted(comp):
        print(f"  {k[0]:16s} {k[1]:8s} {comp[k]}")
    for u in ("lyckat", "ramla", "retreat"):
        n = sum(1 for e in g7 if e["utfall7"] == u)
        nv = sum(1 for e in g7 if e["utfall7"] == u and "NV" in e["v7"])
        print(f"  totalt {u}: {n} (NV {nv} / SO {n - nv})")
    graz = [e for e in g7 if e["mass7_us"] < SIDE_MIN_MASS_US]
    print(f"  grazers (massa<14): {len(graz)}")
    unanch_ram = [e for e in g7 if e["utfall7"] == "ramla"
                  and not e["anchored7"]]
    print(f"  oförankrade gate-ramla: {len(unanch_ram)}")

    print("\n== ÖVERGÅNGAR v6.1 → v7 (samma transiter) ==")
    tr = Counter()
    for e in all_ev:
        k61 = ("gate " + e["utfall61"]) if gate61(e) else \
            (("axial " + e["utfall61"]) if e["v61"] else "inget")
        k7 = ("gate " + e["utfall7"]) if gate7(e) else \
            (("axial " + e["utfall7"]) if e["v7"] else "inget")
        tr[(k61, k7)] += 1
    for k in sorted(tr):
        if k[0] != k[1]:
            print(f"  {k[0]:16s} -> {k[1]:16s} {tr[k]}")
    stable = sum(v for k, v in tr.items() if k[0] == k[1])
    print(f"  oförändrade: {stable}")
    reenter = [e for e in all_ev if gate7(e) and not gate61(e)]
    print(f"  återinträden (ej v6.1-gate -> v7-gate): {len(reenter)}")
    wide_only = [e for e in g7 if e["n_mask7"] > 0
                 and e["wide_only_mask"] == e["n_mask7"]]
    print(f"  v7-gate med ENBART ytterkantsmask (0 sampel i gamla bandet): "
          f"{len(wide_only)}")

    print("\n== GROP-EXPONERING (FP-sondering, v7-gate) ==")
    mdp = np.array([e["min_d_pit"] for e in g7])
    print(f"  min_d_pit p10/p50/p90: {np.percentile(mdp, [10, 50, 90]).round(0)}")
    for thr in (200.0, 260.0, 300.0):
        far = [e for e in g7 if e["min_d_pit"] > thr]
        print(f"  gate-event som aldrig kom närmare gropcentrum än {thr:.0f}: "
              f"{len(far)} ({sum(e['utfall7'] == 'lyckat' for e in far)} lyckat)")


if __name__ == "__main__":
    main()
