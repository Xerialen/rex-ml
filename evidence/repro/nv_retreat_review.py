#!/usr/bin/env python
"""VETOGRANSKNING: NV-retreat-claims @6.6G (analyst, 2026-08-02).

Claims: probe_ledge_66G.json och probe_ra_66G.json ger vardera
"ring→quad NV" 1/0/0/1 (nivå 1) under v7.1.

Instrumenterad transitloop (identiska gränser/utfall som jg._ring_quad_events,
ASSERTAD per segment) som därtill bokför per gate-event:
  * källplattformsvistelse: antal sampel + grundade i vistelsen [t0-bak, i);
  * maskvistelse: n_mask, n_mask_grundade, |perp|-fördelning, massa (u·s);
  * progression: min d(dst) i mask resp. över alla transitsampel,
    max axialprojektion t (0=källa-plattformscentrum-linjens start, 1=mål);
  * gropexponering: min dPit över transitsampeln, min dPit i mask;
  * retreatpunkt: index, position, |perp|, dPit, samt transitlängd i s.

Del A: båda botdumparna (dt 0.026). Del B: humankohorten (24 demos, dt 0.051)
— samma instrumentering; alla 750 gate-event sparas (37 retreat förväntade).

Kör:  cd ~/rex-ml && PYTHONPATH=. sim/.venv-sf/bin/python \
          evidence/repro/nv_retreat_review.py [--human]
Ut:   evidence/repro/nv_retreat_review.json (+ _human.json med --human)
"""
import json
import sys

import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg  # noqa: E402
from rl.jump_gates import (CONFIRM_STAY_S, CONFIRM_WINDOW_S, HEX_R,
                           MAX_TRANSIT_PTS, PIT_2D, PIT_EXPOSURE_R, PIT_Z,
                           PROGRESS_D_BAND, QUAD, RING, SIDE_MIN_MASS_US,
                           LEDGE_Z, _d2, _grounded, _on_ledge, _plat, _side)

assert jg.SIDE_LEDGE_MAX == 460.0 and PIT_EXPOSURE_R == 260.0

_AXIS = (QUAD - RING)[:2]
_AXN = float(_AXIS @ _AXIS)


def _t_ax(p):
    return float(((np.array(p[:2]) - RING[:2]) @ _AXIS) / _AXN)


def trace(path, dt):
    """Speglar jg._ring_quad_events exakt; returnerar (events, details)."""
    events, details = [], []
    grounded = _grounded(path)
    cur = _plat(path[0])
    cur_grounded = bool(grounded[0]) if cur is not None else False
    t0 = 0
    dwell_start = 0
    i = 1
    while i < len(path):
        p = path[i]
        plat = _plat(p)
        if cur is None:
            cur, t0 = plat, i
            dwell_start = i
            cur_grounded = bool(plat is not None and grounded[i])
            i += 1
            continue
        if plat == cur:
            t0 = i
            cur_grounded = cur_grounded or bool(grounded[i])
            i += 1
            continue
        outcome = None
        onto_ledge = False
        progressed = False
        raw_progressed = False
        anchored = False
        min_d_all = float("inf")
        side_acc = 0.0
        # instrumentering
        n_mask = n_mask_g = 0
        perps = []
        min_d_mask = float("inf")
        min_dpit_all = float("inf")
        min_dpit_mask = float("inf")
        max_t_ax = -float("inf")
        n_air = 0
        dst_c = QUAD if cur == "ring" else RING
        j = i
        while j < len(path) and j - t0 <= MAX_TRANSIT_PTS:
            q = path[j]
            min_d_all = min(min_d_all, _d2(q, dst_c))
            dpit = _d2(q, PIT_2D)
            min_dpit_all = min(min_dpit_all, dpit)
            max_t_ax = max(max_t_ax, _t_ax(q))
            if not grounded[j]:
                n_air += 1
            if dpit > HEX_R:
                outcome = "lämnade"
                break
            if q[2] <= PIT_Z:
                outcome = "ramla" if dpit < PIT_EXPOSURE_R else "lämnade"
                break
            qp = _plat(q)
            if qp is None and q[2] > LEDGE_Z:
                if _d2(q, dst_c) < PROGRESS_D_BAND:
                    raw_progressed = True
                if _on_ledge(q):
                    onto_ledge = True
                    side_acc += _side(q)
                    n_mask += 1
                    perps.append(abs(_side(q)))
                    min_d_mask = min(min_d_mask, _d2(q, dst_c))
                    min_dpit_mask = min(min_dpit_mask, dpit)
                    if grounded[j]:
                        anchored = True
                        n_mask_g += 1
                    if _d2(q, dst_c) < PROGRESS_D_BAND:
                        progressed = True
            if qp == cur:
                outcome = "retreat"
                break
            if qp is not None and qp != cur:
                confirmed = False
                fell = False
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
                outcome = "lyckat" if confirmed else ("ramla" if fell else "lämnade")
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
        ev = None
        if onto_ledge and progressed and side_ok and cur_grounded \
                and outcome in ("lyckat", "ramla", "retreat"):
            dst = "quad" if cur == "ring" else "ring"
            side = "NV" if side_acc > 0 else "SO"
            ev = {"hopp": f"{cur}→{dst} {side}", "utfall": outcome,
                  "i0": int(t0), "i1": int(min(j, len(path) - 1))}
        elif (raw_progressed or progressed) and outcome in ("lyckat", "ramla", "retreat"):
            dst = "quad" if cur == "ring" else "ring"
            ev = {"hopp": f"axial {cur}→{dst}", "utfall": outcome,
                  "i0": int(t0), "i1": int(min(j, len(path) - 1))}
        if ev is not None:
            events.append(ev)
            dwell = list(range(dwell_start, i))
            jr = min(j, len(path) - 1)
            perr = np.array(perps) if perps else np.array([np.nan])
            details.append({
                **ev,
                "transit_s": round((jr - i + 1) * dt, 2),
                "dwell_n": len(dwell),
                "dwell_grundade": int(sum(bool(grounded[k]) for k in dwell)),
                "n_mask": n_mask, "n_mask_grundade": n_mask_g,
                "n_air_transit": n_air,
                "mass_us": round(abs(side_acc) * dt, 1),
                "perp_min": round(float(np.nanmin(perr)), 1),
                "perp_med": round(float(np.nanmedian(perr)), 1),
                "perp_max": round(float(np.nanmax(perr)), 1),
                "min_d_all": round(min_d_all, 0),
                "min_d_mask": (round(min_d_mask, 0)
                               if min_d_mask < float("inf") else None),
                "max_t_ax": round(max_t_ax, 3),
                "min_dpit_all": round(min_dpit_all, 0),
                "min_dpit_mask": (round(min_dpit_mask, 0)
                                  if min_dpit_mask < float("inf") else None),
                "retreat_pt": ([round(float(v), 1) for v in path[jr]]
                               if outcome == "retreat" else None),
                "retreat_perp": (round(_side(path[jr]), 1)
                                 if outcome == "retreat" else None),
                "retreat_dpit": (round(_d2(path[jr], PIT_2D), 1)
                                 if outcome == "retreat" else None),
            })
        cur = _plat(path[j]) if j < len(path) else None
        cur_grounded = bool(cur is not None and j < len(path) and grounded[j])
        t0 = j
        dwell_start = j
        i = j + 1
    return events, details


def run_bot(fn, dt=0.026):
    dump = json.load(open(fn))
    out = []
    for ei, ep in enumerate(dump["episodes"]):
        path = np.asarray(ep["path"], dtype=float)
        evs, dets = trace(path, dt)
        official = jg._ring_quad_events(path, dt=dt)
        assert evs == official, f"trace != detektor: {fn} ep{ei}"
        for d in dets:
            d["ep"] = ei
            d["spawn_zone"] = ep.get("spawn_zone")
            out.append(d)
    return out


def run_human():
    import duckdb
    P = ("/home/benjamin-adm/dm3-extract/store-dm3/trajectory_samples/"
         "*/*/*/*/*.parquet")
    W = "format='mvd' and mode='4on4' and map='dm3'"
    keys = json.load(open("/home/benjamin-adm/rex-ml/evidence/repro/"
                          "human_ledge_baseline.json"))["demo_keys"]
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
    all_det = []
    bounds = np.flatnonzero((np.diff(dk) != 0) | (np.diff(sl) != 0)) + 1
    for a, b in zip(np.r_[0, bounds], np.r_[bounds, len(dk)]):
        gaps = np.flatnonzero(np.diff(tt[a:b]) > 150) + 1
        for c, d in zip(np.r_[0, gaps], np.r_[gaps, b - a]):
            if d - c < 10:
                continue
            path = xyz[a + c:a + d]
            evs, dets = trace(path, 0.051)
            official = jg._ring_quad_events(path, dt=0.051)
            assert evs == official, f"trace != detektor demo {dk[a]}"
            for e in dets:
                e["demo_key"] = int(dk[a])
                e["slot"] = int(sl[a])
                all_det.append(e)
    return all_det


def main():
    base = "/home/benjamin-adm/rex-ml/evidence/repro/nv_retreat_review"
    if "--human" in sys.argv:
        dets = run_human()
        gates = [e for e in dets if not e["hopp"].startswith("axial")]
        rets = [e for e in gates if e["utfall"] == "retreat"]
        json.dump({"n_gate": len(gates), "n_retreat": len(rets),
                   "retreats": rets,
                   "gate_events": [{k: e[k] for k in
                                    ("hopp", "utfall", "min_dpit_all",
                                     "min_dpit_mask", "min_d_all", "max_t_ax",
                                     "mass_us", "transit_s", "n_mask",
                                     "n_mask_grundade", "demo_key", "slot")}
                                   for e in gates]},
                  open(base + "_human.json", "w"), indent=1,
                  ensure_ascii=False)
        print(f"gate-event: {len(gates)}, retreat: {len(rets)}")
        for k in ("min_dpit_all", "min_dpit_mask", "min_d_all", "max_t_ax",
                  "mass_us", "n_mask", "transit_s"):
            v = np.array([e[k] for e in rets if e[k] is not None], dtype=float)
            print(f"  human retreat {k}: p10/p50/p90 = "
                  f"{np.percentile(v, [10, 50, 90]).round(1)} "
                  f"min {v.min():.1f} max {v.max():.1f}")
        return
    res = {}
    for name, fn in (("probe_ledge_66G",
                      "/home/benjamin-adm/dumps/probe_ledge_66G.json"),
                     ("probe_ra_66G",
                      "/home/benjamin-adm/dumps/probe_ra_66G.json")):
        dets = run_bot(fn)
        res[name] = dets
        print(f"\n== {name}: {len(dets)} event ==")
        for d in dets:
            print(json.dumps(d, ensure_ascii=False))
    json.dump(res, open(base + ".json", "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
