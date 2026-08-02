#!/usr/bin/env python
"""OMLÅST v7.2-baslinje för humanledgekorsningar (analyst, 2026-08-02).

v7.2 = v7.1 + analystens retreat-kvalifikationskrav (evidence/
analyst_nv_retreat_review.md, implementerat i rl/jump_gates.py):
retreat bokförs som gate-försök endast om transitens min dPit <
PIT_EXPOSURE_R (260) — annars faller eventet till axialspåret.

DUBBELSPÅRNING v7.1 / v7.2 i samma instrumenterade transitloop (identiska
transitgränser och utfall — endast retreat-klassningen skiljer), v7.2-spåret
assertas mot jg._ring_quad_events (nu v7.2) per segment. Verifierar
prognosen ur granskningen: lyckat 580 + ramla 133 OFÖRÄNDRADE, retreat
37→22 (7/7 SO + 15/30 NV), de 15 fällda har min dPit 260–305 och blir
axial-retreat (raw-progression < 450 i samtliga).

Kör:  cd ~/rex-ml && PYTHONPATH=. .venv/bin/python \
          evidence/repro/human_ledge_v72_baseline.py
Ut:   evidence/repro/human_ledge_v72_baseline.json
"""
import json
import sys
from collections import Counter

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg  # noqa: E402
from rl.jump_gates import (CONFIRM_STAY_S, CONFIRM_WINDOW_S, HEX_R,
                           MAX_TRANSIT_PTS, PIT_2D, PIT_EXPOSURE_R, PIT_Z,
                           PROGRESS_D_BAND, QUAD, RING, SIDE_MIN_MASS_US,
                           LEDGE_Z, _d2, _grounded, _on_ledge, _plat, _side)

assert jg.SIDE_LEDGE_MAX == 460.0 and PIT_EXPOSURE_R == 260.0

P = ("/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/"
     "*/*/*/*/*.parquet")
W = "format='mvd' and mode='4on4' and map='dm3'"
GAP_MS = 150
DT = 0.051
BASE = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_baseline.json"


def trace(path, dt):
    """Speglar jg._ring_quad_events (v7.2) exakt; bokför även v7.1-etiketten
    (identisk loop utan retreat-kvalifikationen) + min dPit per event."""
    out = []
    grounded = _grounded(path)
    cur = _plat(path[0])
    cur_grounded = bool(grounded[0]) if cur is not None else False
    t0 = 0
    i = 1
    while i < len(path):
        plat = _plat(path[i])
        if cur is None:
            cur, t0 = plat, i
            cur_grounded = bool(plat is not None and grounded[i])
            i += 1
            continue
        if plat == cur:
            t0 = i
            cur_grounded = cur_grounded or bool(grounded[i])
            i += 1
            continue
        outcome = None
        onto_ledge = progressed = raw_progressed = anchored = False
        min_d_all = float("inf")
        min_dpit = float("inf")
        side_acc = 0.0
        dst_c = QUAD if cur == "ring" else RING
        j = i
        while j < len(path) and j - t0 <= MAX_TRANSIT_PTS:
            q = path[j]
            min_d_all = min(min_d_all, _d2(q, dst_c))
            min_dpit = min(min_dpit, _d2(q, PIT_2D))
            if _d2(q, PIT_2D) > HEX_R:
                outcome = "lämnade"
                break
            if q[2] <= PIT_Z:
                outcome = ("ramla" if _d2(q, PIT_2D) < PIT_EXPOSURE_R
                           else "lämnade")
                break
            qp = _plat(q)
            if qp is None and q[2] > LEDGE_Z:
                if _d2(q, dst_c) < PROGRESS_D_BAND:
                    raw_progressed = True
                if _on_ledge(q):
                    onto_ledge = True
                    side_acc += _side(q)
                    if grounded[j]:
                        anchored = True
                    if _d2(q, dst_c) < PROGRESS_D_BAND:
                        progressed = True
            if qp == cur:
                outcome = "retreat"
                break
            if qp is not None and qp != cur:
                confirmed = fell = False
                consec = 0
                need = max(1, int(round(CONFIRM_STAY_S / dt)))
                for j2 in range(j, min(len(path),
                                       j + int(round(CONFIRM_WINDOW_S / dt)))):
                    q2 = path[j2]
                    if q2[2] <= PIT_Z:
                        fell = _d2(q2, PIT_2D) < PIT_EXPOSURE_R
                        break
                    if _plat(q2) == qp:
                        consec += 1
                        if grounded[j2] or consec >= need:
                            confirmed = True
                            break
                    else:
                        consec = 0
                outcome = ("lyckat" if confirmed
                           else ("ramla" if fell else "lämnade"))
                break
            j += 1
        if outcome is None:
            outcome = "lämnade"
        if outcome == "lyckat":
            progressed = progressed or onto_ledge
            raw_progressed = True
        if outcome == "ramla":
            progressed = (min_d_all < PROGRESS_D_BAND) and anchored
        side_ok = abs(side_acc) * dt >= SIDE_MIN_MASS_US
        dst = "quad" if cur == "ring" else "ring"
        side = "NV" if side_acc > 0 else "SO"

        def label(prog):
            if onto_ledge and prog and side_ok and cur_grounded \
                    and outcome in ("lyckat", "ramla", "retreat"):
                return f"{cur}→{dst} {side}"
            if (raw_progressed or prog) and outcome in ("lyckat", "ramla",
                                                        "retreat"):
                return f"axial {cur}→{dst}"
            return None

        l71 = label(progressed)
        prog72 = progressed
        if outcome == "retreat" and min_dpit >= PIT_EXPOSURE_R:
            prog72 = False               # v7.2-kvalifikationen
        l72 = label(prog72)
        if l71 is not None or l72 is not None:
            out.append({"v71": l71, "v72": l72, "utfall": outcome,
                        "min_dpit": round(min_dpit, 0),
                        "min_d_all": round(min_d_all, 0)})
        cur = _plat(path[j]) if j < len(path) else None
        cur_grounded = bool(cur is not None and j < len(path) and grounded[j])
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
            evs = trace(path, DT)
            official = [{"hopp": e["hopp"], "utfall": e["utfall"]}
                        for e in jg._ring_quad_events(path, dt=DT)]
            mine = [{"hopp": e["v72"], "utfall": e["utfall"]}
                    for e in evs if e["v72"] is not None]
            assert mine == official, f"v7.2-trace != detektor demo {dk[a]}"
            n_assert += 1
            for e in evs:
                e["demo_key"] = int(dk[a])
                e["slot"] = int(sl[a])
                all_ev.append(e)
    fn = ("/home/benjamin-adm/rex-ml/evidence/repro/"
          "human_ledge_v72_baseline.json")
    json.dump({"n_demos": len(keys), "demo_keys": keys, "dt": DT,
               "n_asserted_segments": n_assert, "events": all_ev},
              open(fn, "w"), indent=1, ensure_ascii=False)
    print(f"assert-verifierade segment: {n_assert}, eventposter: {len(all_ev)}")

    def gate(v):
        return v is not None and not v.startswith("axial")

    g72 = [e for e in all_ev if gate(e["v72"])]
    print("\n== OMLÅST v7.2-BASLINJE (gate-event) ==")
    comp = Counter((e["v72"], e["utfall"]) for e in g72)
    for k in sorted(comp):
        print(f"  {k[0]:16s} {k[1]:8s} {comp[k]}")
    for u in ("lyckat", "ramla", "retreat"):
        n = sum(1 for e in g72 if e["utfall"] == u)
        nv = sum(1 for e in g72 if e["utfall"] == u and "NV" in e["v72"])
        print(f"  totalt {u}: {n} (NV {nv} / SO {n - nv})")
    ax = [e for e in all_ev if e["v72"] and e["v72"].startswith("axial")]
    print(f"  gate totalt: {len(g72)}; axial: {len(ax)} "
          f"({dict(Counter(e['utfall'] for e in ax))})")

    print("\n== VERIFIERING mot v7.1 (låst: 580/133/37) ==")
    g71 = [e for e in all_ev if gate(e["v71"])]
    for u in ("lyckat", "ramla"):
        a71 = [e for e in g71 if e["utfall"] == u]
        a72 = [e for e in g72 if e["utfall"] == u]
        same = all(e in g72 for e in a71)
        print(f"  {u}: v7.1 {len(a71)} -> v7.2 {len(a72)} "
              f"(identiska event: {same})")
    r71 = [e for e in g71 if e["utfall"] == "retreat"]
    r72 = [e for e in g72 if e["utfall"] == "retreat"]
    dropped = [e for e in r71 if not gate(e["v72"])]
    print(f"  retreat: v7.1 {len(r71)} -> v7.2 {len(r72)}; fällda {len(dropped)}")
    print(f"  behållna per gate: {dict(Counter(e['v72'] for e in r72))}")
    print(f"  fällda per v7.1-gate: {dict(Counter(e['v71'] for e in dropped))}")
    dp = np.array([e["min_dpit"] for e in dropped])
    print(f"  fällda min dPit: min {dp.min():.0f} max {dp.max():.0f} "
          f"(alla >= 260: {(dp >= 260).all()})")
    kp = np.array([e["min_dpit"] for e in r72])
    print(f"  behållna min dPit: max {kp.max():.0f} (alla < 260: "
          f"{(kp < 260).all()})")
    print(f"  fällda -> v7.2-klass: {dict(Counter(str(e['v72']) for e in dropped))}")


if __name__ == "__main__":
    main()
