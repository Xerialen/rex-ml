#!/usr/bin/env python
"""SLUTLIG v7.1-baslinje för humanledgekorsningar (analyst, 2026-08-02).

v7.1 = ägardefinitionen (mask 460) + analystens två varningsåtgärder:
  (1) dt-robust landningsbekräftelse: grundat dst-sampel ELLER >=0.25 s
      konsekutiv dst-vistelse utan gropfall, fönster 1.4 s (tidsbaserat);
  (2) gropexponeringskrav: fall med dPit >= 260 vid fallpunkten = "lämnade".

TRIPPELSPÅRNING v6.1 / v7 / v7.1 i samma transitloop (transitgränserna är
identiska mellan versionerna — endast utfall/mask skiljer), v7.1-spåret
assertas mot jg._ring_quad_events (dt=0.051) per segment.

Kör:  cd ~/rex-ml && .venv/bin/python evidence/repro/human_ledge_v71_baseline.py
Ut:   evidence/repro/human_ledge_v71_baseline.json
"""
import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg  # noqa: E402
from rl.jump_gates import (CONFIRM_STAY_S, CONFIRM_WINDOW_S, HEX_R, LEDGE_VOX,
                           LEDGE_Z, LEDGE_Z_ABOVE, LEDGE_Z_BELOW,
                           MAX_TRANSIT_PTS, PIT_2D, PIT_EXPOSURE_R, PIT_Z,
                           PROGRESS_D_BAND, QUAD, RING, SIDE_MIN_MASS_US,
                           _d2, _grounded, _on_ledge, _plat, _side)

assert jg.SIDE_LEDGE_MAX == 460.0 and PIT_EXPOSURE_R == 260.0

P = "/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/*/*/*/*/*.parquet"
W = "format='mvd' and mode='4on4' and map='dm3'"
GAP_MS = 150
DT = 0.051
BASE = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_baseline.json"

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


def triple_trace(path, dt):
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
        raw = False
        min_d_all = float("inf")
        fall_d_pit = None
        m61 = dict(onto=False, prog=False, anch=False, acc=0.0, nm=0, nmg=0)
        m7 = dict(onto=False, prog=False, anch=False, acc=0.0, nm=0, nmg=0)
        dst_c = QUAD if cur == "ring" else RING
        o61 = o7 = o71 = None
        j = i
        while j < len(path) and j - t0 <= MAX_TRANSIT_PTS:
            q = path[j]
            min_d_all = min(min_d_all, _d2(q, dst_c))
            if _d2(q, PIT_2D) > HEX_R:
                o61 = o7 = o71 = "lämnade"
                break
            if q[2] <= PIT_Z:
                fall_d_pit = _d2(q, PIT_2D)
                o61 = o7 = "ramla"
                o71 = "ramla" if fall_d_pit < PIT_EXPOSURE_R else "lämnade"
                break
            qp = _plat(q)
            if qp is None and q[2] > LEDGE_Z:
                s = _side(q)
                dd = _d2(q, dst_c)
                if dd < PROGRESS_D_BAND:
                    raw = True
                in7 = _on_ledge(q)
                in61 = in7 and _on_ledge300(q)
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
                o61 = o7 = o71 = "retreat"
                break
            if qp is not None and qp != cur:
                o61 = "lyckat"
                # v7-bekräftelse (27 sampel, endast grundat, alla fall=ramla)
                c7 = f7 = False
                for j2 in range(j, min(len(path), j + 27)):
                    if path[j2][2] <= PIT_Z:
                        f7 = True
                        break
                    if _plat(path[j2]) == qp and g[j2]:
                        c7 = True
                        break
                o7 = "lyckat" if c7 else ("ramla" if f7 else "lämnade")
                # v7.1-bekräftelse (tidsbaserad, grundat ELLER konsekutiv
                # vistelse, endast gropexponerade fall = ramla)
                c71 = f71 = False
                consec = 0
                need = max(1, int(round(CONFIRM_STAY_S / dt)))
                for j2 in range(j, min(len(path),
                                       j + int(round(CONFIRM_WINDOW_S / dt)))):
                    q2 = path[j2]
                    if q2[2] <= PIT_Z:
                        f71 = _d2(q2, PIT_2D) < PIT_EXPOSURE_R
                        if fall_d_pit is None:
                            fall_d_pit = _d2(q2, PIT_2D)
                        break
                    if _plat(q2) == qp:
                        consec += 1
                        if g[j2] or consec >= need:
                            c71 = True
                            break
                    else:
                        consec = 0
                o71 = "lyckat" if c71 else ("ramla" if f71 else "lämnade")
                break
            j += 1
        if o61 is None:
            o61 = o7 = o71 = "lämnade"

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

        l61, l7, l71 = label(m61, o61), label(m7, o7), label(m7, o71)
        if l61 is not None or l7 is not None or l71 is not None:
            out.append({
                "v61": l61, "utfall61": o61,
                "v7": l7, "utfall7": o7,
                "v71": l71, "utfall71": o71,
                "mass_us": round(abs(m7["acc"]) * dt, 1),
                "n_mask": m7["nm"], "n_mask_grundade": m7["nmg"],
                "anchored": m7["anch"],
                "min_d_all": round(min_d_all, 0),
                "fall_d_pit": (round(fall_d_pit, 1)
                               if fall_d_pit is not None else None),
            })
        cur = _plat(path[j]) if j < len(path) else None
        curg = bool(cur is not None and j < len(path) and g[j])
        t0 = j
        i = j + 1
    return out


def main():
    keys = json.load(open(BASE))["demo_keys"]
    con = duckdb.connect()
    con.execute("SET threads TO 14; SET memory_limit='20GB'")
    rows = con.sql(f"""
      select demo_key, slot, t, x, y, z
      from read_parquet('{P}', hive_partitioning=1)
      where {W} and demo_key in ({','.join(map(str, keys))})
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
            evs = triple_trace(path, DT)
            official = [{"hopp": e["hopp"], "utfall": e["utfall"]}
                        for e in jg._ring_quad_events(path, dt=DT)]
            mine = [{"hopp": e["v71"], "utfall": e["utfall71"]}
                    for e in evs if e["v71"] is not None]
            assert mine == official, f"v7.1-trace != detektor demo {dk[a]}"
            n_assert += 1
            for e in evs:
                e["demo_key"] = int(dk[a])
                e["slot"] = int(sl[a])
                all_ev.append(e)
    fn = ("/home/benjamin-adm/rex-ml/evidence/repro/"
          "human_ledge_v71_baseline.json")
    json.dump({"n_demos": len(keys), "demo_keys": keys, "dt": DT,
               "n_asserted_segments": n_assert, "events": all_ev},
              open(fn, "w"), indent=1, ensure_ascii=False)
    print(f"assert-verifierade segment: {n_assert}, eventposter: {len(all_ev)}")

    def gate(v):
        return v is not None and not v.startswith("axial")

    from collections import Counter
    g71 = [e for e in all_ev if gate(e["v71"])]
    print(f"\n== SLUTLIG v7.1-BASLINJE ==")
    comp = Counter((e["v71"], e["utfall71"]) for e in g71)
    for k in sorted(comp):
        print(f"  {k[0]:16s} {k[1]:8s} {comp[k]}")
    for u in ("lyckat", "ramla", "retreat"):
        n = sum(1 for e in g71 if e["utfall71"] == u)
        nv = sum(1 for e in g71 if e["utfall71"] == u and "NV" in e["v71"])
        print(f"  totalt {u}: {n} (NV {nv} / SO {n - nv})")
    print(f"  grazers: "
          f"{sum(1 for e in g71 if e['mass_us'] < SIDE_MIN_MASS_US)}")
    print(f"  oförankrade gate-ramla: "
          f"{sum(1 for e in g71 if e['utfall71'] == 'ramla' and not e['anchored'])}")
    ax71 = [e for e in all_ev if e["v71"] and e["v71"].startswith("axial")]
    print(f"  axial: {len(ax71)} "
          f"({Counter(e['utfall71'] for e in ax71)})")

    print("\n== VERIFIERING (a): lyckat-retention ==")
    l61 = [e for e in all_ev if gate(e["v61"]) and e["utfall61"] == "lyckat"]
    kept = [e for e in l61 if gate(e["v71"]) and e["utfall71"] == "lyckat"]
    lost7 = [e for e in l61 if not (gate(e["v7"]) and e["utfall7"] == "lyckat")]
    rescued = [e for e in lost7 if gate(e["v71"]) and e["utfall71"] == "lyckat"]
    print(f"  v6.1 gate-lyckade: {len(l61)}; kvar i v7.1: {len(kept)} "
          f"({100 * len(kept) / len(l61):.1f} %)")
    print(f"  v7-felfällda: {len(lost7)}; räddade av v7.1: {len(rescued)} "
          f"({100 * len(rescued) / max(1, len(lost7)):.1f} %)")
    still = Counter((str(e['v71']), e['utfall71']) for e in lost7
                    if e not in rescued)
    print(f"  kvarvarande fällda: {dict(still)}")
    v7ram = [e for e in all_ev if gate(e["v61"]) and e["utfall61"] == "lyckat"
             and gate(e["v7"]) and e["utfall7"] == "ramla"]
    print(f"  v7:s grop-inom-fönstret-ramla (12 förv.): {len(v7ram)} -> v7.1: "
          f"{Counter((str(e['v71']), e['utfall71']) for e in v7ram)}")

    print("\n== VERIFIERING (b): ytterkantsfall ==")
    edge = [e for e in all_ev if gate(e["v7"]) and e["utfall7"] == "ramla"
            and e["fall_d_pit"] is not None
            and e["fall_d_pit"] >= PIT_EXPOSURE_R]
    print(f"  v7-gate-ramla med fallpunkt dPit>=260: {len(edge)} -> v7.1: "
          f"{Counter((str(e['v71']), e['utfall71']) for e in edge)}")
    genuine = [e for e in all_ev if gate(e["v7"]) and e["utfall7"] == "ramla"
               and e["fall_d_pit"] is not None
               and e["fall_d_pit"] < PIT_EXPOSURE_R]
    kept_g = [e for e in genuine if gate(e["v71"]) and e["utfall71"] == "ramla"]
    print(f"  v7-gate-ramla med gropfall (dPit<260): {len(genuine)}; "
          f"kvar som v7.1-gate-ramla: {len(kept_g)} "
          f"(tappade: {len(genuine) - len(kept_g)})")
    fdp = np.array([e["fall_d_pit"] for e in g71
                    if e["utfall71"] == "ramla" and e["fall_d_pit"] is not None])
    print(f"  v7.1-ramla fallpunkt dPit p10/p50/p90: "
          f"{np.percentile(fdp, [10, 50, 90]).round(0)} max {fdp.max():.0f}")

    print("\n== ÖVERGÅNGAR v7 -> v7.1 ==")
    tr = Counter()
    for e in all_ev:
        k7 = ("gate " + e["utfall7"]) if gate(e["v7"]) else \
            (("axial " + e["utfall7"]) if e["v7"] else "inget")
        k71 = ("gate " + e["utfall71"]) if gate(e["v71"]) else \
            (("axial " + e["utfall71"]) if e["v71"] else "inget")
        tr[(k7, k71)] += 1
    for k in sorted(tr):
        if k[0] != k[1]:
            print(f"  {k[0]:16s} -> {k[1]:16s} {tr[k]}")
    print(f"  oförändrade: {sum(v for k, v in tr.items() if k[0] == k[1])}")


if __name__ == "__main__":
    main()
