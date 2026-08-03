#!/usr/bin/env python
"""Inspektion av de 21 mega-attempts som strict-regeln fäller (analyst).

Fråga: är de genuina megaförsök (klättring/positionering mot megan som
avbryts/missas) eller genomfartstrafik över platån under megan (den mänskliga
analogen till RA-trappspringklassen)?

Mått per event: min d2, min d3 (3D-avstånd till megan), max z, tid i d<120,
grundad tid på platån (z>=entré+80), medelfart 2D i intervallet, entré-/
utgångsriktning (genomfart = motsatta sidor), z vid min d2, samt om samma
spelare tar megan inom 10 s efter intervallet (pickupbox-touch senare i
segmentet).

Kör:  cd ~/rex-ml && PYTHONPATH=. .venv/bin/python \
          evidence/repro/mega_dropped_inspect.py
"""
import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
from rl.jump_gates import (ITEM_DWELL_S, ITEM_HIGH_GAIN, MEGA_SNG, PICKUP_2D,
                           PICKUP_DZ_HI, PICKUP_DZ_LO, _grounded)
sys.path.insert(0, "/home/benjamin-adm/rex-ml/evidence/repro")
from mega_dwell_corpus import iter_segments, replica_events  # noqa: E402

P = ("/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/"
     "*/*/*/*/*.parquet")

ev_all = json.load(open("/home/benjamin-adm/rex-ml/evidence/repro/"
                        "mega_dwell_corpus.json"))["mega_events"]
dropped = [e for e in ev_all if not e["lyckat"]
           and not (e["dwell_s"] >= ITEM_DWELL_S
                    or e["gain"] >= ITEM_HIGH_GAIN)]
retained_miss = [e for e in ev_all if not e["lyckat"]
                 and (e["dwell_s"] >= ITEM_DWELL_S
                      or e["gain"] >= ITEM_HIGH_GAIN)]
print(f"fällda: {len(dropped)}, behållna missar: {len(retained_miss)}")

con = duckdb.connect()
con.execute("SET threads TO 14; SET memory_limit='20GB'")
want = {}
for e in dropped + retained_miss:
    want.setdefault(e["demo"], []).append(e)

rows_out = []
for dk in sorted(want):
    for sdk, ssl, path, dt in iter_segments(con, [dk]):
        evs = [e for e in want[dk] if e["slot"] == ssl]
        if not evs:
            continue
        reps = replica_events(path, MEGA_SNG, 100.0)
        g = _grounded(path)
        d = np.hypot(path[:, 0] - MEGA_SNG[0], path[:, 1] - MEGA_SNG[1])
        z = path[:, 2]
        for e in evs:
            m = [r for r in reps if r["i0"] == e["i0"]]
            if not m:
                continue
            i0, i1 = m[0]["i0"], m[0]["i1"]
            zz, dd, gg = z[i0:i1 + 1], d[i0:i1 + 1], g[i0:i1 + 1]
            seg = path[i0:i1 + 1]
            d3 = np.sqrt(dd ** 2 + (zz - MEGA_SNG[2]) ** 2)
            v2 = np.hypot(np.diff(seg[:, 0]), np.diff(seg[:, 1])) / dt
            imind = int(dd.argmin())
            ent, ext = seg[0, :2] - MEGA_SNG[:2], seg[-1, :2] - MEGA_SNG[:2]
            cosang = float((ent @ ext)
                           / (np.hypot(*ent) * np.hypot(*ext) + 1e-9))
            plat_t = float((gg & (zz >= zz[0] + 80.0)).sum()) * dt
            # tar spelaren megan inom 10 s efter intervallet?
            j2 = min(len(path), i1 + int(round(10.0 / dt)))
            suc_after = bool(((d[i1:j2] < PICKUP_2D)
                              & (z[i1:j2] - MEGA_SNG[2] > PICKUP_DZ_LO)
                              & (z[i1:j2] - MEGA_SNG[2] < PICKUP_DZ_HI)).any())
            rows_out.append({
                "grupp": "FÄLLD" if e in dropped else "behållen",
                "demo": e["demo"], "slot": ssl, "i0": i0, "dt": dt,
                "dur_s": e["dur_s"], "gain": e["gain"],
                "dwell_s": e["dwell_s"], "n_sim": e["n_sim"],
                "min_d2": round(float(dd.min()), 1),
                "min_d3": round(float(d3.min()), 1),
                "z_at_mind2": round(float(zz[imind]), 1),
                "max_z": round(float(zz.max()), 1),
                "t_in120_s": round(float((dd < 120).sum()) * dt, 2),
                "plat_ground_s": round(plat_t, 2),
                "v2_mean": round(float(v2.mean()), 0),
                "inout_cos": round(cosang, 2),
                "mega_inom_10s": suc_after})

print(f"\n{'grupp':>9} {'demo':>6}/{'sl':<2} {'dur':>5} {'gain':>6} "
      f"{'dwell':>6} {'mind2':>6} {'mind3':>6} {'z@d2':>6} {'maxz':>6} "
      f"{'t<120':>5} {'platG':>5} {'v2':>4} {'cos':>5} {'mega10s'}")
for r in sorted(rows_out, key=lambda r: (r["grupp"] != "FÄLLD", r["min_d3"])):
    print(f"{r['grupp']:>9} {r['demo']:>6}/{r['slot']:<2} {r['dur_s']:>5} "
          f"{r['gain']:>6} {r['dwell_s']:>6} {r['min_d2']:>6} {r['min_d3']:>6}"
          f" {r['z_at_mind2']:>6} {r['max_z']:>6} {r['t_in120_s']:>5} "
          f"{r['plat_ground_s']:>5} {r['v2_mean']:>4.0f} {r['inout_cos']:>5} "
          f"{r['mega_inom_10s']}")

json.dump(rows_out, open("/home/benjamin-adm/rex-ml/evidence/repro/"
                         "mega_dropped_inspect.json", "w"), indent=1)
