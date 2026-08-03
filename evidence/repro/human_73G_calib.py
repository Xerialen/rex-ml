"""Humankalibrering för 7.3G-reviewen (analyst).

A) RA-tagningen: alla detektor-attempts (jg._item_events, RA-linsen) i
   24-demoskohorten, instrumenterade: n simultana sampel, max grundad dz,
   max z, min d2, lyckat, duration.
B) Ring→quad-retreats (v7.2-gate): exponeringsprofil — n exponerade sampel
   (dPit<260), max konsekutiv run, min dPit, tidpunkt för min dPit relativt
   vändpunkten (max tax), radialhastighet mot gropen vid min, d(källa) vid min.
   Även lyckat/ramla NV som referens för exponeringsduration.
"""
import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg
from rl.jump_gates import (RA, PIT_2D, PIT_EXPOSURE_R, QUAD, RING,
                           APPROACH_MIN, CLIMB_GAIN, _d2, _grounded, _plat)

P = ("/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/"
     "*/*/*/*/*.parquet")
W = "format='mvd' and mode='4on4' and map='dm3'"
GAP_MS = 150
DT = 0.051
BASE = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_baseline.json"
AX = (QUAD - RING)[:2]

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

ra_events = []
retreat_events = []
xfer_ref = []
bounds = np.flatnonzero((np.diff(dk) != 0) | (np.diff(sl) != 0)) + 1
nseg = 0
for a, b in zip(np.r_[0, bounds], np.r_[bounds, len(dk)]):
    gaps = np.flatnonzero(np.diff(tt[a:b]) > GAP_MS) + 1
    for c, d in zip(np.r_[0, gaps], np.r_[gaps, b - a]):
        if d - c < 10:
            continue
        path = xyz[a + c:a + d]
        nseg += 1
        g = _grounded(path)
        # ---- A: RA-attempts ----
        att, suc, evs = jg._item_events(path, RA, 300.0,
                                        lambda p: p[2] < 150.0)
        for ev in evs:
            i0, i1 = ev["i0"], ev["i1"]
            z_entry = path[i0][2]
            n_sim = 0
            maxg = -1e9
            mind2 = 1e9
            maxz = -1e9
            for i in range(i0, i1 + 1):
                p = path[i]
                dd = _d2(p, RA)
                mind2 = min(mind2, dd)
                maxz = max(maxz, p[2])
                if g[i]:
                    maxg = max(maxg, p[2])
                if p[2] >= z_entry + CLIMB_GAIN and dd < APPROACH_MIN and g[i]:
                    n_sim += 1
            ra_events.append({
                "demo": int(dk[a]), "slot": int(sl[a]), "i0": int(i0),
                "n": i1 - i0 + 1, "dur_s": round((i1 - i0 + 1) * DT, 2),
                "z_entry": round(z_entry, 1), "n_simult": n_sim,
                "max_grounded_dz": round(maxg - z_entry, 1),
                "max_dz": round(maxz - z_entry, 1),
                "min_d2": round(mind2, 1), "lyckat": ev["lyckat"]})
        # ---- B: gate-retreats + NV-referens ----
        for ev in jg._ring_quad_events(path, dt=DT):
            if ev["hopp"].startswith("axial"):
                continue
            t0, j1 = ev["i0"], ev["i1"]
            seg = path[t0:j1 + 1]
            dpit = np.array([_d2(p, PIT_2D) for p in seg])
            expo = dpit < PIT_EXPOSURE_R
            tax = ((seg[:, :2] - RING[:2]) @ AX) / (AX @ AX)
            if ev["hopp"].startswith("quad"):
                tax = 1.0 - tax          # normera: 0=källa, 1=mål
            src_c = RING if ev["hopp"].startswith("ring") else QUAD
            imin = int(dpit.argmin())
            imax_tax = int(tax.argmax())
            runs, r = [], 0
            for e in expo:
                r = r + 1 if e else 0
                runs.append(r)
            rec = {
                "demo": int(dk[a]), "slot": int(sl[a]), "hopp": ev["hopp"],
                "utfall": ev["utfall"], "n": len(seg),
                "min_dpit": round(float(dpit.min()), 1),
                "n_expo": int(expo.sum()),
                "expo_s": round(float(expo.sum()) * DT, 2),
                "max_run": int(max(runs)) if runs else 0,
                "tax_at_min": round(float(tax[imin]), 3),
                "tax_max": round(float(tax.max()), 3),
                "min_after_turn_s": round((imin - imax_tax) * DT, 2),
                "d_src_at_min": round(_d2(seg[imin], src_c), 1),
            }
            if ev["utfall"] == "retreat":
                retreat_events.append(rec)
            elif "NV" in ev["hopp"]:
                xfer_ref.append(rec)

print(f"segments: {nseg}")
out = {"ra_events": ra_events, "retreat_events": retreat_events,
       "nv_ref": xfer_ref}
json.dump(out, open("/home/benjamin-adm/rex-ml/evidence/repro/"
                    "human_73G_calib.json", "w"), indent=1)

# ---- Sammanfattning A ----
ras = ra_events
print(f"\n== RA-attempts (detektorlins) i kohorten: {len(ras)} "
      f"({sum(e['lyckat'] for e in ras)} lyckade) ==")
for lab, sel in (("lyckade", [e for e in ras if e["lyckat"]]),
                 ("missade", [e for e in ras if not e["lyckat"]])):
    if not sel:
        print(f"{lab}: 0")
        continue
    ns = np.array([e["n_simult"] for e in sel])
    gd = np.array([e["max_grounded_dz"] for e in sel])
    mz = np.array([e["max_dz"] for e in sel])
    d2 = np.array([e["min_d2"] for e in sel])
    print(f"{lab}: n={len(sel)}")
    print(f"  n_simult:   min {ns.min()} p25 {np.percentile(ns,25):.0f} "
          f"p50 {np.percentile(ns,50):.0f} p95 {np.percentile(ns,95):.0f} "
          f"max {ns.max()}; dvs dwell-tid s: p50 {np.percentile(ns,50)*DT:.2f}")
    print(f"  n_simult==1: {(ns==1).sum()}; ==2: {(ns==2).sum()}")
    print(f"  max_grounded_dz: min {gd.min():.0f} p25 {np.percentile(gd,25):.0f} "
          f"p50 {np.percentile(gd,50):.0f} max {gd.max():.0f}")
    print(f"  max_dz: min {mz.min():.0f} p50 {np.percentile(mz,50):.0f} "
          f"max {mz.max():.0f}")
    print(f"  min_d2: p50 {np.percentile(d2,50):.0f} p95 {np.percentile(d2,95):.0f} "
          f"max {d2.max():.0f}")
# de missade med lägst n_simult — kandidater att stickprova
missade = sorted([e for e in ras if not e["lyckat"]], key=lambda e: e["n_simult"])
print("\nmissade, sorterade på n_simult (första 10):")
for e in missade[:10]:
    print(" ", e)

# ---- Sammanfattning B ----
print(f"\n== gate-retreats (v7.2): {len(retreat_events)} ==")
for e in sorted(retreat_events, key=lambda e: e["min_dpit"]):
    print(" ", e)
nv = [e for e in xfer_ref]
print(f"\n== NV lyckat/ramla referens: {len(nv)} ==")
for lab in ("lyckat", "ramla"):
    sel = [e for e in nv if e["utfall"] == lab]
    if not sel:
        continue
    ne = np.array([e["n_expo"] for e in sel])
    es = np.array([e["expo_s"] for e in sel])
    mr = np.array([e["max_run"] for e in sel])
    at = np.array([e["min_after_turn_s"] for e in sel])
    print(f"{lab}: n={len(sel)}; expo_s p5 {np.percentile(es,5):.2f} "
          f"p50 {np.percentile(es,50):.2f} max {es.max():.2f}; "
          f"max_run p5 {np.percentile(mr,5):.0f} p50 {np.percentile(mr,50):.0f}; "
          f"min_after_turn_s p5 {np.percentile(at,5):.2f} "
          f"p50 {np.percentile(at,50):.2f} p95 {np.percentile(at,95):.2f}")
