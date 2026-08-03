#!/usr/bin/env python
"""Humanpass för review 12 (9.6G) + fas1-validering (analyst, 2026-08-03).

Ett pass över 24-demoskohorten (v7.3-detektorn). Per gate-event:

REVIEW-12-extramått (saknas i human_89G_calib.json):
  rev_tax      : största progressionsregress (normaliserad tax) efter bästa
                 framsteg inom transiten (i0+1..i1) — "vändsignatur".
  max_abs_perp : max |perp| i transiten (maskutflyktskontroll, SIDE_LEDGE_MAX=460).
  src_grounded : grundade sampel i källvistelsen [k..i0] (bakåt medan _plat konstant).

FAS1-reproduktion (ultracode-definitionerna, oberoende implementation):
  takeoff_idx  : sista grundade sampel före första LUFTBURNA samplet i eventet
                 [i0..i1], bakåtsökt i hela segmentet.
  anlopp_v     : medel av per-sampel-fart hypot(dxy)/dt över de sista 10
                 grundade samplen t.o.m. takeoff (dt = 0.051 fast, som ultracode,
                 PLUS per-segment median-dt för dt-känslighet).
  v_avstamp    : farten vid takeoff-samplet.
  i0-/grundad-avstampsmått: d_edge_open_2d, d_edge_side_2d, d_pit_2d
                 (1031 stödda OPEN-maskcentra via jg.ledge_centers()).

Kör:  cd ~/rex-ml && PYTHONPATH=. .venv/bin/python \
          evidence/repro/review_96G_human.py
Ut:   evidence/repro/review_96G_human.json
"""
import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg  # noqa: E402
from rl.jump_gates import (PIT_2D, QUAD, RING, _d2, _grounded, _plat,
                           _side)

P = ("/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/"
     "*/*/*/*/*.parquet")
W = "format='mvd' and mode='4on4' and map='dm3'"
GAP_MS = 150
DT = 0.051
BASE = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_baseline.json"
AX = (QUAD - RING)[:2]
LEDGE = None  # fylls i main


def d_edge(p, side=None):
    """min 2D-avstånd till OPEN-maskcentra; side='NV'/'SO' begränsar."""
    cs = LEDGE
    if side is not None:
        perp = np.array([_side(c) for c in cs])
        cs = cs[perp > 0] if side == "NV" else cs[perp < 0]
    return float(np.min(np.hypot(cs[:, 0] - p[0], cs[:, 1] - p[1])))


def measure(path, g, ev, seg_dt):
    i0, i1 = ev["i0"], ev["i1"]
    q2r = ev["hopp"].startswith("quad")
    side = "NV" if ev["hopp"].endswith("NV") else "SO"
    # --- review-12: reversal + max|perp| i transiten
    tax = ((path[i0 + 1:i1 + 1, :2] - RING[:2]) @ AX) / (AX @ AX)
    prog = (1.0 - tax) if q2r else tax
    run_max = np.maximum.accumulate(prog)
    rev_tax = float(np.max(run_max - prog)) if len(prog) else 0.0
    perp = np.array([_side(p) for p in path[i0 + 1:i1 + 1]])
    max_abs_perp = float(np.max(np.abs(perp))) if len(perp) else 0.0
    # --- källvistelse bakåt
    k = i0
    while k > 0 and _plat(path[k - 1]) == _plat(path[i0]):
        k -= 1
    src_g_idx = [i for i in range(k, i0 + 1) if g[i]]
    # --- fas1: takeoff
    first_air = next((i for i in range(i0, i1 + 1) if not g[i]), None)
    takeoff = None
    if first_air is not None:
        for i in range(first_air - 1, -1, -1):
            if g[i]:
                takeoff = i
                break
    rec = {"hopp": ev["hopp"], "utfall": ev["utfall"], "i0": i0, "i1": i1,
           "rev_tax": round(rev_tax, 3),
           "max_abs_perp": round(max_abs_perp, 1),
           "src_grounded": len(src_g_idx),
           "seg_dt": round(seg_dt, 4)}
    if takeoff is not None and takeoff >= 1:
        g_idx = [i for i in range(1, takeoff + 1) if g[i]][-10:]
        v = [float(np.hypot(*(path[i, :2] - path[i - 1, :2])) / DT)
             for i in g_idx]
        v_seg = [x * DT / seg_dt for x in v]
        rec.update(takeoff_idx=takeoff,
                   n_gr=len(g_idx),
                   anlopp_v=round(float(np.mean(v)), 1),
                   anlopp_v_segdt=round(float(np.mean(v_seg)), 1),
                   v_avstamp=round(v[-1], 1),
                   v_max_sample=round(max(v), 1),
                   takeoff_d_edge=round(d_edge(path[takeoff]), 1))
    # --- fas1: avstampspunkt
    p0 = path[i0]
    rec.update(i0_d_edge_open=round(d_edge(p0), 1),
               i0_d_edge_side=round(d_edge(p0, side), 1),
               i0_d_pit=round(float(_d2(p0, PIT_2D)), 1),
               i0_z=round(float(p0[2]), 1),
               i0_grounded=bool(g[i0]))
    if src_g_idx:
        pg = path[src_g_idx[-1]]
        rec.update(gr_d_edge_open=round(d_edge(pg), 1),
                   gr_d_edge_side=round(d_edge(pg, side), 1),
                   gr_d_pit=round(float(_d2(pg, PIT_2D)), 1))
    return rec


def main():
    global LEDGE
    LEDGE = jg.ledge_centers()
    # OBS: docstringen/ultracode säger 1031, men funktionen ger 410 (SIDE_LEDGE_MAX-
    # filtret); vi använder den FAKTISKA funktionen och flaggar citatet.
    assert len(LEDGE) == 410, len(LEDGE)
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
    out = []
    bounds = np.flatnonzero((np.diff(dk) != 0) | (np.diff(sl) != 0)) + 1
    for a, b in zip(np.r_[0, bounds], np.r_[bounds, len(dk)]):
        gaps = np.flatnonzero(np.diff(tt[a:b]) > GAP_MS) + 1
        for c, d in zip(np.r_[0, gaps], np.r_[gaps, b - a]):
            if d - c < 10:
                continue
            path = xyz[a + c:a + d]
            seg_dt = float(np.median(np.diff(tt[a + c:a + d]))) / 1000.0
            g = _grounded(path)
            for ev in jg._ring_quad_events(path, dt=DT):
                if ev["hopp"].startswith("axial"):
                    continue
                rec = measure(path, g, ev, seg_dt)
                rec["demo"] = int(dk[a])
                rec["slot"] = int(sl[a])
                out.append(rec)
    json.dump({"events": out},
              open("/home/benjamin-adm/rex-ml/evidence/repro/"
                   "review_96G_human.json", "w"), indent=1)
    # sammanfattning
    n_by = {}
    for e in out:
        n_by[e["utfall"]] = n_by.get(e["utfall"], 0) + 1
    print("gate-event:", len(out), n_by)
    dts = sorted(set(e["seg_dt"] for e in out))
    print("seg_dt-värden:", dts)

    def pct(vals, q):
        return float(np.percentile(np.asarray(vals, float), q))

    for utf in ("lyckat", "ramla"):
        sel = [e for e in out if e["utfall"] == utf]
        va = [e["anlopp_v"] for e in sel if "anlopp_v" in e]
        vs = [e["anlopp_v_segdt"] for e in sel if "anlopp_v_segdt" in e]
        print(f"\n== {utf}: n={len(sel)}, med anlopp={len(va)} ==")
        print(f"  anlopp_v      p10 {pct(va,10):.1f} p50 {pct(va,50):.1f} "
              f"p90 {pct(va,90):.1f} max {max(va):.1f} medel {np.mean(va):.1f} "
              f"min {min(va):.1f}")
        print(f"  anlopp_segdt  p50 {pct(vs,50):.1f} p90 {pct(vs,90):.1f} "
              f"max {max(vs):.1f}")
        spik = [e for e in sel if e.get("v_max_sample", 0) > 1000]
        print(f"  sampel-spikar >1000 u/s i anloppsfönstret: {len(spik)}")
        for e in spik[:6]:
            print("   demo", e["demo"], "slot", e["slot"], "i0", e["i0"],
                  "v_max_sample", e["v_max_sample"], "anlopp_v", e["anlopp_v"])
        for f in ("i0_d_edge_open", "i0_d_edge_side", "i0_d_pit",
                  "gr_d_edge_open", "gr_d_edge_side", "gr_d_pit"):
            v = [e[f] for e in sel if f in e]
            print(f"  {f:15s} n={len(v)} p50 {pct(v,50):.1f} "
                  f"p90 {pct(v,90):.1f} max {max(v):.1f}")
        rv = [e["rev_tax"] for e in sel]
        mp = [e["max_abs_perp"] for e in sel]
        sg = [e["src_grounded"] for e in sel]
        print(f"  rev_tax       p50 {pct(rv,50):.3f} p90 {pct(rv,90):.3f} "
              f"max {max(rv):.3f}")
        print(f"  max_abs_perp  p50 {pct(mp,50):.1f} p90 {pct(mp,90):.1f} "
              f"max {max(mp):.1f}")
        print(f"  src_grounded  min {min(sg)} p10 {pct(sg,10):.0f} "
              f"p50 {pct(sg,50):.0f}")
    # klassvis för review 12
    for hopp, utf in (("quad→ring SO", "ramla"), ("ring→quad SO", "ramla")):
        sel = [e for e in out if e["hopp"] == hopp and e["utfall"] == utf]
        rv = sorted(e["rev_tax"] for e in sel)
        mp = sorted(e["max_abs_perp"] for e in sel)
        sg = sorted(e["src_grounded"] for e in sel)
        print(f"\n== {hopp} {utf} (n={len(sel)}) ==")
        print(f"  rev_tax: min {rv[0]:.3f} p50 {rv[len(rv)//2]:.3f} "
              f"p90 {pct(rv,90):.3f} max {rv[-1]:.3f}; "
              f">=0.20: {sum(1 for x in rv if x >= 0.20)}, "
              f">=0.245: {sum(1 for x in rv if x >= 0.245)}")
        print(f"  max_abs_perp: p50 {mp[len(mp)//2]:.0f} p90 {pct(mp,90):.0f} "
              f"max {mp[-1]:.0f}; >460: {sum(1 for x in mp if x > 460)}, "
              f">=540: {sum(1 for x in mp if x >= 540)}")
        print(f"  src_grounded: min {sg[0]} p50 {sg[len(sg)//2]} "
              f"<=4: {sum(1 for x in sg if x <= 4)}, "
              f"<=6: {sum(1 for x in sg if x <= 6)}")


if __name__ == "__main__":
    main()


# --- fas1-tillägg (körs separat): tidsnormerade anloppsfönster ---
def main_windows():
    """Fönsterkänslighet: anloppsfart med seg-dt-korrekta farter över
    (a) sista 10 grundade, (b) grundade inom 0.50 s, (c) inom 0.15 s,
    samt fart vid själva avstampssamplet."""
    global LEDGE
    LEDGE = jg.ledge_centers()
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
    out = []
    bounds = np.flatnonzero((np.diff(dk) != 0) | (np.diff(sl) != 0)) + 1
    for a, b in zip(np.r_[0, bounds], np.r_[bounds, len(dk)]):
        gaps = np.flatnonzero(np.diff(tt[a:b]) > GAP_MS) + 1
        for c, d in zip(np.r_[0, gaps], np.r_[gaps, b - a]):
            if d - c < 10:
                continue
            path = xyz[a + c:a + d]
            seg_dt = float(np.median(np.diff(tt[a + c:a + d]))) / 1000.0
            g = _grounded(path)
            for ev in jg._ring_quad_events(path, dt=DT):
                if ev["hopp"].startswith("axial"):
                    continue
                i0, i1 = ev["i0"], ev["i1"]
                first_air = next((i for i in range(i0, i1 + 1) if not g[i]),
                                 None)
                takeoff = None
                if first_air is not None:
                    for i in range(first_air - 1, -1, -1):
                        if g[i]:
                            takeoff = i
                            break
                if takeoff is None or takeoff < 1:
                    continue
                gi = [i for i in range(1, takeoff + 1) if g[i]]
                vv = {i: float(np.hypot(*(path[i, :2] - path[i - 1, :2]))
                               / seg_dt) for i in gi}
                w10 = gi[-10:]
                w050 = [i for i in gi if (takeoff - i) * seg_dt <= 0.50]
                w015 = [i for i in gi if (takeoff - i) * seg_dt <= 0.15]
                out.append({
                    "utfall": ev["utfall"], "hopp": ev["hopp"],
                    "demo": int(dk[a]), "slot": int(sl[a]),
                    "seg_dt": round(seg_dt, 4),
                    "v10": round(float(np.mean([vv[i] for i in w10])), 1),
                    "vw050": round(float(np.mean([vv[i] for i in w050])), 1),
                    "vw015": round(float(np.mean([vv[i] for i in w015])), 1),
                    "v_to": round(vv[takeoff], 1)})
    json.dump({"events": out},
              open("/home/benjamin-adm/rex-ml/evidence/repro/"
                   "review_96G_human_windows.json", "w"), indent=1)

    def pct(vals, q):
        return float(np.percentile(np.asarray(vals, float), q))

    for utf in ("lyckat", "ramla"):
        for lab, lo, hi in (("alla", 0.0, 1.0), ("dt51", 0.045, 1.0),
                            ("dt34", 0.02, 0.045), ("dt13-16", 0.0, 0.02)):
            sel = [e for e in out if e["utfall"] == utf
                   and lo < e["seg_dt"] <= hi]
            if not sel:
                continue
            line = f"{utf:7s} {lab:8s} n={len(sel):3d}"
            for f in ("v10", "vw050", "vw015", "v_to"):
                v = [e[f] for e in sel]
                line += (f" | {f} p50 {pct(v, 50):5.1f} p90 {pct(v, 90):5.1f}"
                         f" max {max(v):5.1f}")
            print(line)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "windows":
    main_windows()
