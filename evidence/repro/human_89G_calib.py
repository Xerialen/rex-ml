#!/usr/bin/env python
"""Humankalibrering för 8.9G-reviewen (analyst-review 11, 2026-08-03).

Instrumenterar ALLA gate-event (v7.3-detektorn, 24-demoskohorten) med
transitprofil för ramla-jämförelsen mot bot-eventen A och B:
  min dPit, expo-tid (dPit<260), masksampel, grundade masksampel (ankare),
  ankarpositioner (tax min/max), sidomassa (u·s), min d(dst),
  fallpunkt (dPit, perp, tax) — i transiten eller bekräftelsefönstret,
  transittid, gate, utfall.

Kör:  cd ~/rex-ml && PYTHONPATH=. .venv/bin/python \
          evidence/repro/human_89G_calib.py
Ut:   evidence/repro/human_89G_calib.json
"""
import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg  # noqa: E402
from rl.jump_gates import (CONFIRM_WINDOW_S, PIT_2D, PIT_EXPOSURE_R, PIT_Z,
                           QUAD, RING, _d2, _grounded, _on_ledge, _plat,
                           _side)

P = ("/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/"
     "*/*/*/*/*.parquet")
W = "format='mvd' and mode='4on4' and map='dm3'"
GAP_MS = 150
DT = 0.051
BASE = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_baseline.json"
AX = (QUAD - RING)[:2]


def instrument(path, g, ev):
    i0, i1 = ev["i0"], ev["i1"]
    dst = QUAD if ev["hopp"].startswith("ring") else RING
    side_acc = 0.0
    n_mask = n_anch = expo = 0
    min_dpit = min_ddst = 1e9
    anch_tax = []
    fall = None
    for i in range(i0 + 1, i1 + 1):
        p = path[i]
        dpit = _d2(p, PIT_2D)
        min_dpit = min(min_dpit, dpit)
        min_ddst = min(min_ddst, _d2(p, dst))
        expo += int(dpit < PIT_EXPOSURE_R)
        tax = float(((p[:2] - RING[:2]) @ AX) / (AX @ AX))
        if ev["hopp"].startswith("quad"):
            tax = 1.0 - tax
        if _plat(p) is None and p[2] > jg.LEDGE_Z and _on_ledge(p):
            side_acc += _side(p)
            n_mask += 1
            if g[i]:
                n_anch += 1
                anch_tax.append(round(tax, 3))
        if p[2] <= PIT_Z and fall is None:
            fall = (dpit, _side(p), tax)
    if fall is None:
        for j in range(i1, min(len(path), i1 + int(round(CONFIRM_WINDOW_S / DT)))):
            p = path[j]
            if p[2] <= PIT_Z:
                tax = float(((p[:2] - RING[:2]) @ AX) / (AX @ AX))
                if ev["hopp"].startswith("quad"):
                    tax = 1.0 - tax
                fall = (_d2(p, PIT_2D), _side(p), tax)
                break
    return {"hopp": ev["hopp"], "utfall": ev["utfall"],
            "n": i1 - i0, "dur_s": round((i1 - i0) * DT, 2),
            "min_dpit": round(min_dpit, 1), "expo_s": round(expo * DT, 2),
            "n_mask": n_mask, "n_anch": n_anch,
            "anch_tax": [min(anch_tax), max(anch_tax)] if anch_tax else None,
            "side_mass_us": round(abs(side_acc) * DT, 1),
            "min_ddst": round(min_ddst, 1),
            "fall_dpit": round(fall[0], 1) if fall else None,
            "fall_perp": round(fall[1], 1) if fall else None,
            "fall_tax": round(fall[2], 3) if fall else None}


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
    out = []
    bounds = np.flatnonzero((np.diff(dk) != 0) | (np.diff(sl) != 0)) + 1
    for a, b in zip(np.r_[0, bounds], np.r_[bounds, len(dk)]):
        gaps = np.flatnonzero(np.diff(tt[a:b]) > GAP_MS) + 1
        for c, d in zip(np.r_[0, gaps], np.r_[gaps, b - a]):
            if d - c < 10:
                continue
            path = xyz[a + c:a + d]
            g = _grounded(path)
            for ev in jg._ring_quad_events(path, dt=DT):
                if ev["hopp"].startswith("axial"):
                    continue
                rec = instrument(path, g, ev)
                rec["demo"] = int(dk[a])
                rec["slot"] = int(sl[a])
                out.append(rec)
    json.dump({"events": out},
              open("/home/benjamin-adm/rex-ml/evidence/repro/"
                   "human_89G_calib.json", "w"), indent=1)
    print(f"gate-event: {len(out)}")
    for hopp in ("ring→quad NV", "quad→ring SO"):
        for utf in ("ramla", "lyckat"):
            sel = [e for e in out if e["hopp"] == hopp and e["utfall"] == utf]
            print(f"\n== {hopp} {utf}: n={len(sel)} ==")
            if not sel:
                continue
            for key in ("min_dpit", "expo_s", "n_anch", "side_mass_us",
                        "min_ddst", "dur_s"):
                v = np.array([e[key] for e in sel], dtype=float)
                print(f"  {key:12s} min {v.min():.2f} p25 "
                      f"{np.percentile(v, 25):.2f} p50 "
                      f"{np.percentile(v, 50):.2f} p75 "
                      f"{np.percentile(v, 75):.2f} max {v.max():.2f}")
            if utf == "ramla":
                fd = np.array([e["fall_dpit"] for e in sel
                               if e["fall_dpit"] is not None], dtype=float)
                fp = [e["fall_perp"] for e in sel if e["fall_perp"] is not None]
                ft = [e["fall_tax"] for e in sel if e["fall_tax"] is not None]
                print(f"  fall_dpit ({len(fd)}): min {fd.min():.0f} p50 "
                      f"{np.percentile(fd, 50):.0f} max {fd.max():.0f}")
                print(f"  fall_perp: {sorted(round(x) for x in fp)}")
                print(f"  fall_tax:  {sorted(round(x, 2) for x in ft)}")
                at = [e["anch_tax"] for e in sel if e["anch_tax"]]
                print(f"  anch_tax max per event: "
                      f"{sorted(round(x[1], 2) for x in at)}")
                n0 = sum(1 for e in sel if e["n_anch"] == 0)
                print(f"  event utan ankare i mask: {n0}")


if __name__ == "__main__":
    main()
