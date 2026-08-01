"""Analyst-instrumentering av rl/jump_gates.py-detektorn mot rex_trajectories.json.

Reproducerar detektorlogiken EXAKT men loggar fulla segment + regionsdiagnostik.
"""
import json
import sys

import numpy as np

SP = "/tmp/claude-1001/-home-benjamin-adm-rex-ml/003dd697-8855-417d-9d80-53960851ebcf/scratchpad"

RING = np.array([240.0, -32.0, 56.0])
QUAD = np.array([952.0, 296.0, 56.0])
PIT_2D = np.array([564.0, -48.0])
PIT_Z = -100.0
PLAT_R = 260.0
LEDGE_Z = -20.0
HEX_R = 800.0
DT = 0.026
MAX_TRANSIT_PTS = int(4.0 / DT)

RA = np.array([256.0, -704.0, 304.0])
MEGA_SNG = np.array([-720.0, 80.0, 160.0])
PICKUP_2D = 60.0
PICKUP_DZ = 56.0

_AXIS = (QUAD - RING)[:2]


def d2(p, c):
    return float(np.hypot(p[0] - c[0], p[1] - c[1]))


def side(p):
    v = np.array([p[0], p[1]]) - RING[:2]
    return float(_AXIS[0] * v[1] - _AXIS[1] * v[0])


def plat(p):
    if d2(p, RING) < PLAT_R:
        return "ring"
    if d2(p, QUAD) < PLAT_R:
        return "quad"
    return None


def ring_quad_events(path, ep):
    """Identisk styrlogik med jump_gates._ring_quad_events, men loggar allt."""
    events = []
    cur = plat(path[0])
    t0 = 0
    i = 1
    while i < len(path):
        p = path[i]
        pl = plat(p)
        if cur is None:
            cur, t0 = pl, i
            i += 1
            continue
        if pl == cur:
            t0 = i
            i += 1
            continue
        seg_idx = [t0]
        outcome = None
        onto_ledge = False
        side_acc = 0.0
        ledge_pts = []
        j = i
        while j < len(path) and j - t0 <= MAX_TRANSIT_PTS:
            q = path[j]
            seg_idx.append(j)
            if d2(q, PIT_2D) > HEX_R:
                outcome = "lämnade"
                break
            if q[2] <= PIT_Z:
                outcome = "ramla"
                break
            qp = plat(q)
            if qp is None and q[2] > LEDGE_Z:
                onto_ledge = True
                side_acc += side(q)
                ledge_pts.append(j)
            if qp == cur:
                outcome = "retreat"
                break
            if qp is not None and qp != cur:
                outcome = "lyckat"
                break
            j += 1
        if outcome is None:
            outcome = "lämnade"
        rec = onto_ledge and outcome in ("lyckat", "ramla", "retreat")
        seg = path[seg_idx]
        dst = "quad" if cur == "ring" else "ring"
        ev = {
            "ep": ep,
            "recorded": bool(rec),
            "hopp": f"{cur}→{dst} {'NV' if side_acc > 0 else 'SO'}",
            "utfall": outcome,
            "i0": int(seg_idx[0]),
            "i1": int(seg_idx[-1]),
            "dur_s": round((seg_idx[-1] - seg_idx[0]) * DT, 2),
            "start": [round(float(v), 1) for v in seg[0]],
            "slut": [round(float(v), 1) for v in seg[-1]],
            "z_min": round(float(seg[:, 2].min()), 1),
            "z_max": round(float(seg[:, 2].max()), 1),
            "z_start": round(float(seg[0, 2]), 1),
            "n_ledge_pts": len(ledge_pts),
            "ledge_z": ([round(float(path[k][2]), 1) for k in ledge_pts[:6]]
                        if ledge_pts else []),
            "ledge_first": ([round(float(v), 1) for v in path[ledge_pts[0]][:3]]
                            if ledge_pts else None),
            "min_d_dst": round(min(d2(q, RING if dst == "ring" else QUAD)
                                   for q in seg), 1),
            "max_d_src": round(max(d2(q, RING if cur == "ring" else QUAD)
                                   for q in seg), 1),
            "side_acc": round(side_acc, 0),
        }
        events.append(ev)
        cur = plat(path[j]) if j < len(path) else None
        t0 = j
        i = j + 1
    return events


def item_events_detail(path, item, approach_r, attempt_pred, ep):
    out = []
    inside = False
    att = suc = False
    i0 = None
    zmax = -1e9
    zmin = 1e9
    z_ent = None
    dmin = 1e9
    for k, p in enumerate(path):
        if d2(p, item) < approach_r:
            if not inside:
                i0, zmax, zmin, dmin = k, -1e9, 1e9, 1e9
                z_ent = float(p[2])
            inside = True
            if attempt_pred(p):
                att = True
            zmax = max(zmax, float(p[2]))
            zmin = min(zmin, float(p[2]))
            dmin = min(dmin, d2(p, item))
            if d2(p, item) < PICKUP_2D and abs(p[2] - item[2]) < PICKUP_DZ:
                suc = True
        elif inside:
            out.append({"ep": ep, "i0": int(i0), "i1": int(k - 1),
                        "attempt": bool(att), "success": bool(suc),
                        "dur_s": round((k - 1 - i0) * DT, 2),
                        "z_entry": round(z_ent, 1),
                        "z_max": round(zmax, 1), "z_min": round(zmin, 1),
                        "d2_min": round(dmin, 1)})
            inside, att, suc = False, False, False
    if inside and att:
        out.append({"ep": ep, "i0": int(i0), "i1": int(len(path) - 1),
                    "attempt": True, "success": bool(suc),
                    "dur_s": round((len(path) - 1 - i0) * DT, 2),
                    "z_entry": round(z_ent, 1),
                    "z_max": round(zmax, 1), "z_min": round(zmin, 1),
                    "d2_min": round(dmin, 1)})
    return out


def main():
    d = json.load(open(f"{SP}/rex_trajectories.json"))
    all_rq = []
    ra_int = []
    mega_int = []
    occ = []
    for ep, e in enumerate(d["episodes"]):
        path = np.asarray(e["path"], dtype=float)[:, :3]
        all_rq += ring_quad_events(path, ep)
        ra_int += item_events_detail(path, RA, 300.0, lambda p: p[2] < 150.0, ep)
        mega_int += item_events_detail(path, MEGA_SNG, 300.0,
                                       lambda p: p[2] > 100.0, ep)
        # plattformsbelaggning per z-band
        dr = np.hypot(path[:, 0] - RING[0], path[:, 1] - RING[1])
        dq = np.hypot(path[:, 0] - QUAD[0], path[:, 1] - QUAD[1])
        z = path[:, 2]
        occ.append({
            "ep": ep, "spawn": e["spawn_zone"],
            "ring_hi": int(((dr < PLAT_R) & (z > -20)).sum()),
            "ring_mid": int(((dr < PLAT_R) & (z <= -20) & (z > -100)).sum()),
            "ring_pit": int(((dr < PLAT_R) & (z <= -100)).sum()),
            "quad_hi": int(((dq < PLAT_R) & (z > -20)).sum()),
            "quad_mid": int(((dq < PLAT_R) & (z <= -20) & (z > -100)).sum()),
            "quad_pit": int(((dq < PLAT_R) & (z <= -100)).sum()),
        })
    rec = [e for e in all_rq if e["recorded"]]
    print(f"kandidattransiter totalt: {len(all_rq)}, registrerade: {len(rec)}")
    from collections import Counter
    print("registrerade per hopp/utfall:",
          Counter((e['hopp'], e['utfall']) for e in rec))
    print("oregistrerade per (cur->utfall):",
          Counter((e['hopp'].split(' ')[0], e['utfall'])
                  for e in all_rq if not e["recorded"]))
    tot = {k: sum(o[k] for o in occ)
           for k in ("ring_hi", "ring_mid", "ring_pit",
                     "quad_hi", "quad_mid", "quad_pit")}
    print("belaggning (samples à 26 ms):", tot,
          "=> s:", {k: round(v * DT, 1) for k, v in tot.items()})
    n_att = sum(1 for r in ra_int if r["attempt"])
    print(f"RA-intervall: {len(ra_int)}, attempts: {n_att}, "
          f"succ: {sum(r['success'] for r in ra_int)}")
    zmx = sorted(r["z_max"] for r in ra_int if r["attempt"])
    a = np.array(zmx)
    print("RA attempt z_max kvantiler:",
          {q: round(float(np.percentile(a, q)), 1)
           for q in (0, 10, 25, 50, 75, 90, 100)})
    print("RA attempt d2_min kvantiler:",
          {q: round(float(np.percentile(
              np.array([r['d2_min'] for r in ra_int if r['attempt']]), q)), 1)
           for q in (0, 25, 50, 75, 100)})
    print(f"mega-intervall: {len(mega_int)}, "
          f"attempts: {sum(r['attempt'] for r in mega_int)}, "
          f"succ: {sum(r['success'] for r in mega_int)}")
    json.dump({"rq": all_rq, "ra": ra_int, "mega": mega_int, "occ": occ},
              open(f"{SP}/vet_jumpgates_out.json", "w"), indent=1,
              ensure_ascii=False)
    print("\n== registrerade quad→ring-segment ==")
    for e in rec:
        print(json.dumps(e, ensure_ascii=False))
    print("\n== mega-intervall detalj ==")
    for e in mega_int:
        print(json.dumps(e, ensure_ascii=False))


if __name__ == "__main__":
    main()
