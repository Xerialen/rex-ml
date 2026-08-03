#!/usr/bin/env python
"""Mega-revalidering av v7.3-dwellregeln mot HELA dm3-korpusen (analyst, 2026-08-03).

Fråga: kan item-gate-regeln strict=True (dwell >= 0.15 s ELLER max grundad
z >= entré+130) driftsättas för SNG-mega utan att fälla genuina mänskliga
låg-entré-försök? 24-demoskohorten har bara 1 mega-attempt genom detektor-
linsen (n=1 räcker inte) — därför skannas ALLA 4on4/dm3/mvd-demos i
store-dm3 (2146 demos, ~826 M sampel).

Metod:
  1) PARITETSVALIDERING: en vektoriserad replika av jg._item_events körs
     mot detektorns egen funktion på hela 24-demoskohorten (RA: 619
     v7.2-event + 618 strict-event; mega: 1) — intervallgränser, lyckat,
     v7.2-attempt och strict-kvalifikation assertas identiska.
  2) KORPUSPASS: replikan på alla demos (batchad duckdb-läsning, samma
     segmentregler som baslinjen: gap-split >150 ms, minst 10 sampel).
     dt per segment = median(diff t); dwell = max_run x dt.

Instrumentering per mega-attempt (v7.2-semantik = dagens driftläge):
n_sim, max_run, dwell_s, max grundad gain, lyckat, duration — beslutunderlag
för trösklar.

Kör:  cd ~/rex-ml && PYTHONPATH=. .venv/bin/python \
          evidence/repro/mega_dwell_corpus.py
Ut:   evidence/repro/mega_dwell_corpus.json
"""
import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg  # noqa: E402
from rl.jump_gates import (APPROACH_MIN, CLIMB_GAIN, ITEM_DWELL_S,
                           ITEM_HIGH_GAIN, MEGA_SNG, PICKUP_2D, PICKUP_DZ_HI,
                           PICKUP_DZ_LO, RA, _grounded)

P = ("/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/"
     "*/*/*/*/*.parquet")
W = "format='mvd' and mode='4on4' and map='dm3'"
GAP_MS = 150
BASE = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_baseline.json"
BATCH = 80


def replica_events(path, item, low_z, approach_r=300.0):
    """Vektoriserad replika av jg._item_events (v7.2-semantik) med
    v7.3-instrumentering. Returnerar lista av event-dicts."""
    g = _grounded(path)
    d = np.hypot(path[:, 0] - item[0], path[:, 1] - item[1])
    z = path[:, 2]
    inside = d < approach_r
    # intervallgränser: [start, end] med alla sampel inside
    pad = np.r_[False, inside, False]
    starts = np.flatnonzero(pad[1:] & ~pad[:-1])
    ends = np.flatnonzero(~pad[1:] & pad[:-1]) - 1
    out = []
    for i0, i1 in zip(starts, ends):
        z_entry = z[i0]
        if not (z_entry < low_z):
            continue
        zz, dd, gg = z[i0:i1 + 1], d[i0:i1 + 1], g[i0:i1 + 1]
        c = (zz >= z_entry + CLIMB_GAIN) & (dd < APPROACH_MIN) & gg
        if not c.any():
            continue                     # inget v7.2-attempt
        n_sim = int(c.sum())
        # max konsekutiv run i c
        cp = np.r_[0, c.astype(int), 0]
        db = np.diff(cp)
        max_run = int((np.flatnonzero(db == -1)
                       - np.flatnonzero(db == 1)).max())
        gain = 0.0
        if gg.any():
            gain = max(0.0, float((zz[gg] - z_entry).max()))
        suc = bool(((dd < PICKUP_2D) & (zz - item[2] > PICKUP_DZ_LO)
                    & (zz - item[2] < PICKUP_DZ_HI)).any())
        out.append({"i0": int(i0), "i1": int(i1), "n": int(i1 - i0 + 1),
                    "z_entry": round(float(z_entry), 1),
                    "n_sim": n_sim, "max_run": max_run,
                    "gain": round(gain, 1), "lyckat": suc})
    return out


def iter_segments(con, keys):
    rows = con.sql(f"""
      select demo_key, slot, t, x, y, z
      from read_parquet('{P}', hive_partitioning=1)
      where {W} and demo_key in ({','.join(map(str, keys))})
      order by demo_key, slot, t""").fetchnumpy()
    dk, sl = rows["demo_key"], rows["slot"]
    tt = rows["t"].astype(np.int64)
    xyz = np.stack([rows["x"], rows["y"], rows["z"]], axis=1).astype(float)
    bounds = np.flatnonzero((np.diff(dk) != 0) | (np.diff(sl) != 0)) + 1
    for a, b in zip(np.r_[0, bounds], np.r_[bounds, len(dk)]):
        gaps = np.flatnonzero(np.diff(tt[a:b]) > GAP_MS) + 1
        for c, d in zip(np.r_[0, gaps], np.r_[gaps, b - a]):
            if d - c < 10:
                continue
            seg_t = tt[a + c:a + d]
            dt = float(np.median(np.diff(seg_t))) / 1000.0
            yield int(dk[a]), int(sl[a]), xyz[a + c:a + d], dt


def validate_parity(con):
    """Replikan mot jg._item_events på 24-demoskohorten (RA + mega)."""
    keys = json.load(open(BASE))["demo_keys"]
    DT = 0.051
    n_ev = {"RA": 0, "mega": 0}
    n_seg = 0
    for dk, sl, path, _dt in iter_segments(con, keys):
        n_seg += 1
        for name, item, low_z in (("RA", RA, 150.0), ("mega", MEGA_SNG, 100.0)):
            _, _, off72 = jg._item_events(
                path, item, 300.0, lambda p, L=low_z: p[2] < L,
                dt=DT, strict=False)
            _, _, off73 = jg._item_events(
                path, item, 300.0, lambda p, L=low_z: p[2] < L,
                dt=DT, strict=True)
            rep = replica_events(path, item, low_z)
            assert [(e["i0"], e["i1"], e["lyckat"]) for e in rep] \
                == [(e["i0"], e["i1"], e["lyckat"]) for e in off72], \
                f"v7.2-paritet demo {dk} slot {sl} {name}"
            rep73 = [e for e in rep
                     if e["max_run"] * DT >= ITEM_DWELL_S
                     or e["gain"] >= ITEM_HIGH_GAIN]
            assert [(e["i0"], e["i1"], e["lyckat"]) for e in rep73] \
                == [(e["i0"], e["i1"], e["lyckat"]) for e in off73], \
                f"strict-paritet demo {dk} slot {sl} {name}"
            n_ev[name] += len(rep)
    print(f"PARITET OK: {n_seg} segment; event RA {n_ev['RA']} "
          f"(619 förväntade), mega {n_ev['mega']} (1 förväntat)")
    assert n_ev["RA"] == 619 and n_ev["mega"] == 1


def main():
    con = duckdb.connect()
    con.execute("SET threads TO 14; SET memory_limit='20GB'")
    validate_parity(con)

    all_keys = [r[0] for r in con.sql(
        f"select distinct demo_key from read_parquet('{P}', "
        f"hive_partitioning=1) where {W} order by demo_key").fetchall()]
    print(f"korpus: {len(all_keys)} demos")
    mega_ev = []
    n_seg = 0
    for bi in range(0, len(all_keys), BATCH):
        batch = all_keys[bi:bi + BATCH]
        for dk, sl, path, dt in iter_segments(con, batch):
            n_seg += 1
            for e in replica_events(path, MEGA_SNG, 100.0):
                e.update({"demo": dk, "slot": sl, "dt": round(dt, 4),
                          "dwell_s": round(e["max_run"] * dt, 3),
                          "dur_s": round(e["n"] * dt, 2)})
                mega_ev.append(e)
        print(f"  batch {bi // BATCH + 1}/{(len(all_keys) + BATCH - 1) // BATCH}"
              f": segment {n_seg}, mega-event {len(mega_ev)}", flush=True)
    json.dump({"n_demos": len(all_keys), "n_segments": n_seg,
               "mega_events": mega_ev},
              open("/home/benjamin-adm/rex-ml/evidence/repro/"
                   "mega_dwell_corpus.json", "w"), indent=1)

    print(f"\n== KORPUS: {len(mega_ev)} mega-attempts (v7.2-lins), "
          f"{sum(e['lyckat'] for e in mega_ev)} lyckade ==")
    for lab, sel in (("lyckade", [e for e in mega_ev if e["lyckat"]]),
                     ("missade", [e for e in mega_ev if not e["lyckat"]])):
        print(f"{lab}: n={len(sel)}")
        if not sel:
            continue
        dw = np.array([e["dwell_s"] for e in sel])
        gn = np.array([e["gain"] for e in sel])
        keep = (dw >= ITEM_DWELL_S) | (gn >= ITEM_HIGH_GAIN)
        print(f"  dwell_s: min {dw.min():.3f} p5 {np.percentile(dw, 5):.3f} "
              f"p25 {np.percentile(dw, 25):.3f} p50 {np.percentile(dw, 50):.3f}"
              f" max {dw.max():.3f}")
        print(f"  gain: min {gn.min():.0f} p5 {np.percentile(gn, 5):.0f} "
              f"p25 {np.percentile(gn, 25):.0f} p50 {np.percentile(gn, 50):.0f}"
              f" max {gn.max():.0f}")
        print(f"  retention (dwell>=0.15 | gain>=130): {keep.sum()}/{len(sel)}"
              f" = {100.0 * keep.sum() / len(sel):.1f} %")
        lost = [e for e in sel if not (e["dwell_s"] >= ITEM_DWELL_S
                                       or e["gain"] >= ITEM_HIGH_GAIN)]
        for e in sorted(lost, key=lambda e: -e["dwell_s"])[:20]:
            print("   fälls:", e)
        # känslighet: retention för alternativa dwell-trösklar
        for th in (0.10, 0.15, 0.20, 0.25):
            k = ((dw >= th) | (gn >= ITEM_HIGH_GAIN)).sum()
            print(f"  dwell>={th:.2f}: {k}/{len(sel)}")
        for gh in (104, 130, 150):
            k = ((dw >= ITEM_DWELL_S) | (gn >= gh)).sum()
            print(f"  gain>={gh}: {k}/{len(sel)}")


if __name__ == "__main__":
    main()
