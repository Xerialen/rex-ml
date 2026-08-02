#!/usr/bin/env python
"""Mänsklig baslinje för ledgeprobe-granskningen (analyst 2026-08-02).

Kör NUVARANDE detektor (rl.jump_gates v4, orörd) på mänskliga 4on4-dm3-
trajektorier ur store-dm3 och karakteriserar quad→ring-transitevents i samma
mått som bot-eventet i probe_ledge_60G.json ep 8:

  * grundade sampel under transiten (via jg._grounded),
  * grundade LEDGE-sampel (|perp| 100–300, z-band 40–130, utanför plattform),
  * |side_acc| (sidoklassningens styrka),
  * z vid första progressionssamplet (d(dst) < 350).

Mänsklig MVD-dt ≈ 51 ms (detektorns MAX_TRANSIT_PTS blir ~8 s — samma
tolkning som i tidigare reviews som körde detektorn på humandata).

Kör:  ~/rex-ml/.venv/bin/python ~/rex-ml/evidence/repro/human_ledge_baseline.py
"""
import json
import sys

import duckdb
import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
from rl.jump_gates import (HEX_R, LEDGE_Z, MAX_TRANSIT_PTS, PIT_2D, PIT_Z,
                           PROGRESS_D, QUAD, RING, SIDE_DEADZONE, _d2,
                           _grounded, _plat, _side)

P = "/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/*/*/*/*/*.parquet"
W = "format='mvd' and mode='4on4' and map='dm3'"
N_DEMOS = 24
GAP_MS = 150

con = duckdb.connect()
con.execute("SET threads TO 14; SET memory_limit='20GB'")


def trace(path):
    """Identisk tillståndsmaskin som jg._ring_quad_events (assert-verifierad i
    vet_ledgeprobe.py), med per-event-mätvärden tillagda."""
    events = []
    cur = _plat(path[0])
    t0 = 0
    i = 1
    g = _grounded(path)
    while i < len(path):
        plat = _plat(path[i])
        if cur is None:
            cur, t0 = plat, i
            i += 1
            continue
        if plat == cur:
            t0 = i
            i += 1
            continue
        outcome = None
        onto_ledge = False
        progressed = False
        prog_z = None
        side_acc = 0.0
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
                onto_ledge = True
                s = _side(q)
                if abs(s) > SIDE_DEADZONE:
                    side_acc += s
                if _d2(q, dst_c) < PROGRESS_D:
                    progressed = True
                    if prog_z is None:
                        prog_z = float(q[2])
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
            progressed = True
        if onto_ledge and progressed and outcome in ("lyckat", "ramla", "retreat"):
            dst = "quad" if cur == "ring" else "ring"
            side = "NV" if side_acc > 0 else ("SO" if side_acc < 0 else "obestämd")
            tr = path[t0:j + 1]
            gtr = g[t0:j + 1]
            perp = np.array([_side(p) for p in tr])
            on_plat = np.array([_plat(p) is not None for p in tr])
            zb = (tr[:, 2] > 40.0) & (tr[:, 2] < 130.0)
            ledge_g = gtr & ~on_plat & zb & (np.abs(perp) > 100) & \
                (np.abs(perp) < 300)
            events.append({
                "hopp": f"{cur}→{dst} {side}", "utfall": outcome,
                "n_transit": int(j - t0), "n_grundade": int(gtr.sum()),
                "n_ledge_grundade": int(ledge_g.sum()),
                "side_acc": round(float(side_acc), 1),
                "prog_z": None if prog_z is None else round(prog_z, 1),
            })
        cur = _plat(path[j]) if j < len(path) else None
        t0 = j
        i = j + 1
    return events


def main():
    keys = [r[0] for r in con.sql(f"""
      select distinct demo_key from read_parquet('{P}', hive_partitioning=1)
      where {W} order by hash(demo_key) limit {N_DEMOS}""").fetchall()]
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
    bounds = np.flatnonzero((np.diff(dk) != 0) | (np.diff(sl) != 0)) + 1
    for a, b in zip(np.r_[0, bounds], np.r_[bounds, len(dk)]):
        gaps = np.flatnonzero(np.diff(t[a:b]) > GAP_MS) + 1
        for c, d in zip(np.r_[0, gaps], np.r_[gaps, b - a]):
            if d - c < 10:
                continue
            for ev in trace(xyz[a + c:a + d]):
                ev["demo_key"] = int(dk[a])
                ev["slot"] = int(sl[a])
                all_ev.append(ev)
    out = {"n_demos": len(keys), "demo_keys": keys, "events": all_ev}
    fn = "/home/benjamin-adm/rex-ml/evidence/repro/human_ledge_baseline.json"
    json.dump(out, open(fn, "w"), indent=1, ensure_ascii=False)

    def summ(sel, tag):
        if not sel:
            print(f"{tag}: 0 events")
            return
        ng = np.array([e["n_ledge_grundade"] for e in sel])
        sa = np.array([abs(e["side_acc"]) for e in sel])
        pz = np.array([e["prog_z"] for e in sel if e["prog_z"] is not None],
                      dtype=float)
        print(f"{tag}: n={len(sel)}  ledge-grundade sampel p10/p50/p90 = "
              f"{np.percentile(ng, 10):.0f}/{np.percentile(ng, 50):.0f}/"
              f"{np.percentile(ng, 90):.0f}  andel med 0 ledge-grundade = "
              f"{(ng == 0).mean():.2f}  |side_acc| p50 = {np.median(sa):.0f}"
              + (f"  prog_z p10/p50 = {np.percentile(pz, 10):.0f}/"
                 f"{np.percentile(pz, 50):.0f}" if len(pz) else ""))

    qr = [e for e in all_ev if e["hopp"].startswith("quad→ring")]
    summ(qr, "quad→ring ALLA")
    summ([e for e in qr if "SO" in e["hopp"]], "quad→ring SO")
    summ([e for e in qr if "SO" in e["hopp"] and e["utfall"] == "ramla"],
         "quad→ring SO ramla")
    summ([e for e in qr if "SO" in e["hopp"] and e["utfall"] == "lyckat"],
         "quad→ring SO lyckat")
    print("skrivet:", fn)


if __name__ == "__main__":
    main()
