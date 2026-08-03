#!/usr/bin/env python
"""OMLÅST v7.3-baslinje för humanledgekorsningar + item-gates (analyst, 2026-08-03).

v7.3 = v7.2 + (a) retreat-kvalifikationen skärpt: min dPit < RETREAT_PIT_R=192
(var PIT_EXPOSURE_R=260) — dörrtröskelklassen ur analyst_73G_review.md;
(b) item-gates strict=True (RA): dwell >= ITEM_DWELL_S=0.15 s (max konsekutiva
samtidighetssampel x dt) ELLER max grundad z >= entré + ITEM_HIGH_GAIN=130.

Tre uppgifter i samma kohortpass (24 demos, dt 0.051):
  1) DUBBELSPÅRNING v7.2/v7.3 av gate-eventen; v7.3-spåret assertas mot
     jg._ring_quad_events per segment. Prognos (analyst_73G_review):
     735 -> 726 (580/133/13); rq-NV 208/13/1; 9 fällda = dörrtröskel-NV,
     min dPit 208.0-250.4, samtliga -> axial retreat.
  2) RA-STRICT-VERIFIERING: jg._item_events körs strict=True och strict=False;
     retentionen (prognos 619/619 = 100 %) mäts, inte antas.
  3) MEGA-DWELL-KALIBRERING: alla mänskliga SNG-mega-attempts (v7.2-semantik)
     instrumenteras med max_run (dwell) och max grundad gain — underlag för
     beslut om strict=True kan driftsättas för megan.

Kör:  cd ~/rex-ml && PYTHONPATH=. .venv/bin/python \
          evidence/repro/human_ledge_v73_baseline.py
Ut:   evidence/repro/human_ledge_v73_baseline.json
"""
import json
import sys
from collections import Counter

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg  # noqa: E402
from rl.jump_gates import (APPROACH_MIN, CLIMB_GAIN, CONFIRM_STAY_S,
                           CONFIRM_WINDOW_S, HEX_R, ITEM_DWELL_S,
                           ITEM_HIGH_GAIN, LEDGE_Z, MAX_TRANSIT_PTS,
                           MEGA_SNG, PIT_2D, PIT_EXPOSURE_R, PIT_Z,
                           PROGRESS_D_BAND, QUAD, RA, RETREAT_PIT_R, RING,
                           SIDE_MIN_MASS_US, _d2, _grounded, _on_ledge,
                           _plat, _side)

assert RETREAT_PIT_R == 192.0 and PIT_EXPOSURE_R == 260.0
assert ITEM_DWELL_S == 0.15 and ITEM_HIGH_GAIN == 130.0

P = ("/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/"
     "*/*/*/*/*.parquet")
W = "format='mvd' and mode='4on4' and map='dm3'"
GAP_MS = 150
DT = 0.051
BASE = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_baseline.json"


def trace(path, dt):
    """Speglar jg._ring_quad_events; bokför v7.2- OCH v7.3-etikett per event
    (identisk transitloop — endast retreat-kvalifikationströskeln skiljer)."""
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

        prog72, prog73 = progressed, progressed
        if outcome == "retreat" and min_dpit >= PIT_EXPOSURE_R:
            prog72 = False
        if outcome == "retreat" and min_dpit >= RETREAT_PIT_R:
            prog73 = False
        l72, l73 = label(prog72), label(prog73)
        if l72 is not None or l73 is not None:
            out.append({"v72": l72, "v73": l73, "utfall": outcome,
                        "min_dpit": round(min_dpit, 1),
                        "min_d_all": round(min_d_all, 0)})
        cur = _plat(path[j]) if j < len(path) else None
        cur_grounded = bool(cur is not None and j < len(path) and grounded[j])
        t0 = j
        i = j + 1
    return out


def item_metrics(path, g, item, i0, i1):
    """Replikerar _item_events-instrumenteringen exakt på ett besöksintervall
    (alla sampel i [i0,i1] ligger inom approach-radien per konstruktion)."""
    z_entry = path[i0][2]
    run = max_run = n_sim = 0
    gain = 0.0
    for i in range(i0, i1 + 1):
        p = path[i]
        d = _d2(p, item)
        if p[2] >= z_entry + CLIMB_GAIN and d < APPROACH_MIN and g[i]:
            n_sim += 1
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
        if g[i]:
            gain = max(gain, p[2] - z_entry)
    return n_sim, max_run, round(gain, 1)


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
    ra_v72, ra_v73, mega_ev = [], [], []
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
            mine = [{"hopp": e["v73"], "utfall": e["utfall"]}
                    for e in evs if e["v73"] is not None]
            assert mine == official, f"v7.3-trace != detektor demo {dk[a]}"
            n_assert += 1
            for e in evs:
                e["demo_key"] = int(dk[a])
                e["slot"] = int(sl[a])
                all_ev.append(e)
            g = _grounded(path)
            # RA: strict (v7.3, detektorns skarpa läge) vs v7.2-semantik
            _, _, evs_s = jg._item_events(path, RA, 300.0,
                                          lambda p: p[2] < 150.0,
                                          dt=DT, strict=True)
            _, _, evs_o = jg._item_events(path, RA, 300.0,
                                          lambda p: p[2] < 150.0,
                                          dt=DT, strict=False)
            for ev in evs_o:
                n_sim, max_run, gain = item_metrics(path, g, RA,
                                                    ev["i0"], ev["i1"])
                ra_v72.append({"demo": int(dk[a]), "slot": int(sl[a]),
                               "i0": ev["i0"], "lyckat": ev["lyckat"],
                               "n_sim": n_sim, "max_run": max_run,
                               "dwell_s": round(max_run * DT, 3),
                               "gain": gain})
            ra_v73.extend({"demo": int(dk[a]), "i0": ev["i0"],
                           "lyckat": ev["lyckat"]} for ev in evs_s)
            # MEGA: v7.2-attempts instrumenterade för dwell-beslutet
            _, _, evs_m = jg._item_events(path, MEGA_SNG, 300.0,
                                          lambda p: p[2] < 100.0,
                                          dt=DT, strict=False)
            for ev in evs_m:
                n_sim, max_run, gain = item_metrics(path, g, MEGA_SNG,
                                                    ev["i0"], ev["i1"])
                mega_ev.append({"demo": int(dk[a]), "slot": int(sl[a]),
                                "i0": ev["i0"], "i1": ev["i1"],
                                "n": ev["i1"] - ev["i0"] + 1,
                                "lyckat": ev["lyckat"],
                                "n_sim": n_sim, "max_run": max_run,
                                "dwell_s": round(max_run * DT, 3),
                                "gain": gain})
    fn = ("/home/benjamin-adm/rex-ml/evidence/repro/"
          "human_ledge_v73_baseline.json")
    json.dump({"n_demos": len(keys), "demo_keys": keys, "dt": DT,
               "n_asserted_segments": n_assert, "events": all_ev,
               "ra_v72_events": ra_v72, "ra_v73_n": len(ra_v73),
               "mega_events": mega_ev},
              open(fn, "w"), indent=1, ensure_ascii=False)
    print(f"assert-verifierade segment: {n_assert}, "
          f"gate-eventposter: {len(all_ev)}")

    def gate(v):
        return v is not None and not v.startswith("axial")

    g73 = [e for e in all_ev if gate(e["v73"])]
    print("\n== OMLÅST v7.3-BASLINJE (gate-event) ==")
    comp = Counter((e["v73"], e["utfall"]) for e in g73)
    for k in sorted(comp):
        print(f"  {k[0]:16s} {k[1]:8s} {comp[k]}")
    for u in ("lyckat", "ramla", "retreat"):
        n = sum(1 for e in g73 if e["utfall"] == u)
        nv = sum(1 for e in g73 if e["utfall"] == u and "NV" in e["v73"])
        print(f"  totalt {u}: {n} (NV {nv} / SO {n - nv})")
    ax = [e for e in all_ev if e["v73"] and e["v73"].startswith("axial")]
    print(f"  gate totalt: {len(g73)}; axial: {len(ax)} "
          f"({dict(Counter(e['utfall'] for e in ax))})")

    print("\n== VERIFIERING mot v7.2 (låst: 580/133/22) ==")
    g72 = [e for e in all_ev if gate(e["v72"])]
    for u in ("lyckat", "ramla"):
        a72 = [e for e in g72 if e["utfall"] == u]
        a73 = [e for e in g73 if e["utfall"] == u]
        same = all(e in g73 for e in a72)
        print(f"  {u}: v7.2 {len(a72)} -> v7.3 {len(a73)} "
              f"(identiska event: {same})")
    r72 = [e for e in g72 if e["utfall"] == "retreat"]
    r73 = [e for e in g73 if e["utfall"] == "retreat"]
    dropped = [e for e in r72 if not gate(e["v73"])]
    print(f"  retreat: v7.2 {len(r72)} -> v7.3 {len(r73)}; "
          f"fällda {len(dropped)}")
    print(f"  behållna per gate: {dict(Counter(e['v73'] for e in r73))}")
    print(f"  fällda per v7.2-gate: {dict(Counter(e['v72'] for e in dropped))}")
    if dropped:
        dp = np.array([e["min_dpit"] for e in dropped])
        print(f"  fällda min dPit: min {dp.min():.1f} max {dp.max():.1f} "
              f"(alla >= 192: {(dp >= 192).all()})")
        print(f"  fällda -> v7.3-klass: "
              f"{dict(Counter(str(e['v73']) for e in dropped))}")
    if r73:
        kp = np.array([e["min_dpit"] for e in r73])
        print(f"  behållna min dPit: max {kp.max():.1f} (alla < 192: "
              f"{(kp < 192).all()})")

    print("\n== RA: strict-retention (prognos 619/619) ==")
    print(f"  v7.2-attempts: {len(ra_v72)} "
          f"({sum(e['lyckat'] for e in ra_v72)} lyckade); "
          f"v7.3-strict-attempts: {len(ra_v73)} "
          f"({sum(e['lyckat'] for e in ra_v73)} lyckade)")
    lost = [e for e in ra_v72
            if not (e["dwell_s"] >= ITEM_DWELL_S or e["gain"] >= ITEM_HIGH_GAIN)]
    print(f"  fällda av dwell/gain-regeln: {len(lost)}")
    for e in lost:
        print("   ", e)

    print("\n== MEGA: dwell-kalibrering (v7.2-attempts, humandata) ==")
    for lab, sel in (("lyckade", [e for e in mega_ev if e["lyckat"]]),
                     ("missade", [e for e in mega_ev if not e["lyckat"]])):
        print(f"  {lab}: n={len(sel)}")
        if not sel:
            continue
        dw = np.array([e["dwell_s"] for e in sel])
        gn = np.array([e["gain"] for e in sel])
        ns = np.array([e["n_sim"] for e in sel])
        print(f"    dwell_s: min {dw.min():.3f} p5 {np.percentile(dw,5):.3f} "
              f"p25 {np.percentile(dw,25):.3f} p50 {np.percentile(dw,50):.3f} "
              f"max {dw.max():.3f}")
        print(f"    gain:    min {gn.min():.0f} p5 {np.percentile(gn,5):.0f} "
              f"p25 {np.percentile(gn,25):.0f} p50 {np.percentile(gn,50):.0f} "
              f"max {gn.max():.0f}")
        print(f"    n_sim==0: {(ns==0).sum()}, ==1: {(ns==1).sum()}, "
              f"==2: {(ns==2).sum()}")
        keep = (dw >= ITEM_DWELL_S) | (gn >= ITEM_HIGH_GAIN)
        print(f"    retention under (dwell>=0.15 | gain>=130): "
              f"{keep.sum()}/{len(sel)}")
        fail = [e for e in sel
                if not (e["dwell_s"] >= ITEM_DWELL_S
                        or e["gain"] >= ITEM_HIGH_GAIN)]
        for e in fail[:15]:
            print("     fälls:", e)


if __name__ == "__main__":
    main()
