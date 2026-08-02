"""Vetogranskning av genombrottsclaimet (traj_63G, gate2_v2 @6.35G).

Instrumenterad kopia av rl.jump_gates._ring_quad_events (v6.1) som återger
EXAKT samma eventbeslut (assertas mot detektorn) men dessutom dumpar per event:
episod, sampelindex, källplattformsvistelsens grundade sampel, transitens
grundade masksampel (förankring), sidomassa (u·s), min-d-kurva, gropavstånd
för masksamplen, utfallspunkt samt banans polyline i transitfönstret.

Kör:  cd ~/rex-ml && PYTHONPATH=. sim/.venv-sf/bin/python \
        evidence/repro/breakthrough_63G_extract.py ~/dumps/traj_63G.json
Ut:   evidence/repro/breakthrough_63G_events.json
"""
import json
import sys

import numpy as np

from rl.jump_gates import (HEX_R, MAX_TRANSIT_PTS, PIT_2D, PIT_Z, LEDGE_Z,
                           PROGRESS_D_BAND, QUAD, RING, SAMPLE_DT,
                           SIDE_MIN_MASS_US, _d2, _grounded, _on_ledge, _plat,
                           _side, analyze)


def events_instrumented(path: np.ndarray, dt: float = SAMPLE_DT) -> list[dict]:
    events = []
    grounded = _grounded(path)
    cur = _plat(path[0])
    cur_grounded = bool(grounded[0]) if cur is not None else False
    src_start = 0            # extra: början på nuvarande källvistelse
    src_grounded_idx = ([0] if (cur is not None and grounded[0]) else [])
    t0 = 0
    i = 1
    while i < len(path):
        p = path[i]
        plat = _plat(p)
        if cur is None:
            cur, t0 = plat, i
            cur_grounded = bool(plat is not None and grounded[i])
            src_start = i
            src_grounded_idx = [i] if cur_grounded else []
            i += 1
            continue
        if plat == cur:
            t0 = i
            if grounded[i]:
                src_grounded_idx.append(i)
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
        dst_c = QUAD if cur == "ring" else RING
        j = i
        mask_idx, mask_grounded_idx = [], []
        d_curve = []
        while j < len(path) and j - t0 <= MAX_TRANSIT_PTS:
            q = path[j]
            d_curve.append(round(_d2(q, dst_c), 1))
            min_d_all = min(min_d_all, _d2(q, dst_c))
            if _d2(q, PIT_2D) > HEX_R:
                outcome = "lämnade"
                break
            if q[2] <= PIT_Z:
                outcome = "ramla"
                break
            qp = _plat(q)
            if qp is None and q[2] > LEDGE_Z:
                if _d2(q, dst_c) < PROGRESS_D_BAND:
                    raw_progressed = True
                if _on_ledge(q):
                    onto_ledge = True
                    mask_idx.append(j)
                    side_acc += _side(q)
                    if grounded[j]:
                        anchored = True
                        mask_grounded_idx.append(j)
                    if _d2(q, dst_c) < PROGRESS_D_BAND:
                        progressed = True
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
            progressed = progressed or onto_ledge
            raw_progressed = True
        if outcome == "ramla":
            progressed = (min_d_all < PROGRESS_D_BAND) and anchored
        side_ok = abs(side_acc) * dt >= SIDE_MIN_MASS_US
        rec = None
        if onto_ledge and progressed and side_ok and cur_grounded \
                and outcome in ("lyckat", "ramla", "retreat"):
            dst = "quad" if cur == "ring" else "ring"
            side = "NV" if side_acc > 0 else "SO"
            rec = {"hopp": f"{cur}→{dst} {side}", "utfall": outcome}
        elif (raw_progressed or progressed) and outcome in ("lyckat", "ramla",
                                                            "retreat"):
            dst = "quad" if cur == "ring" else "ring"
            rec = {"hopp": f"axial {cur}→{dst}", "utfall": outcome}
        if rec is not None:
            tr = path[i:min(j + 1, len(path))]
            rec.update({
                "src_stay": [int(src_start), int(t0)],
                "src_stay_s": round((t0 - src_start) * dt, 2),
                "src_grounded_n": len(src_grounded_idx),
                "src_grounded_first_last":
                    [int(src_grounded_idx[0]), int(src_grounded_idx[-1])]
                    if src_grounded_idx else None,
                "transit": [int(i), int(j)],
                "transit_s": round((j - i) * dt, 2),
                "mask_idx": [int(k) for k in mask_idx],
                "mask_grounded_idx": [int(k) for k in mask_grounded_idx],
                "side_acc_u": round(side_acc, 1),
                "side_mass_us": round(abs(side_acc) * dt, 1),
                "min_d_all": round(min_d_all, 1),
                "d_curve": d_curve,
                "outcome_pt": [round(float(v), 1) for v in path[j][:3]]
                    if j < len(path) else None,
                "mask_pts": [[int(k)] + [round(float(v), 1) for v in path[k][:3]]
                             + [round(_side(path[k]), 1),
                                round(_d2(path[k], PIT_2D), 1),
                                bool(grounded[k])] for k in mask_idx],
                "traj_pts": [[int(i + k)] + [round(float(v), 1)
                              for v in tr[k][:3]] for k in range(len(tr))],
            })
            events.append(rec)
        cur = _plat(path[j]) if j < len(path) else None
        cur_grounded = bool(cur is not None and j < len(path) and grounded[j])
        src_start = j
        src_grounded_idx = ([j] if cur_grounded else [])
        t0 = j
        i = j + 1
    return events


def main():
    dump = json.load(open(sys.argv[1]))
    dt = float(dump.get("dt") or SAMPLE_DT)
    out = {"dump": sys.argv[1], "dt": dt, "events": []}
    for e, ep in enumerate(dump["episodes"]):
        path = np.asarray(ep["path"], dtype=float)
        for ev in events_instrumented(path, dt=dt):
            ev["episode"] = e
            ev["spawn_zone"] = ep.get("spawn_zone")
            out["events"].append(ev)
    # Assert: samma räkning som driftdetektorn
    ref = analyze(dump)
    so = ref["gates"]["ring→quad SO"]
    ax = ref["axiala_gropkorsningar"]
    mine_so = [e for e in out["events"] if e["hopp"] == "ring→quad SO"]
    mine_ax = [e for e in out["events"] if e["hopp"].startswith("axial")]
    assert so["försök"] == len(mine_so), (so, len(mine_so))
    assert ax["försök"] == len(mine_ax), (ax, len(mine_ax))
    n_gate = sum(g["försök"] for k, g in ref["gates"].items()
                 if "→" in k)
    assert n_gate == sum(1 for e in out["events"] if not
                         e["hopp"].startswith("axial")), n_gate
    path_out = "evidence/repro/breakthrough_63G_events.json"
    json.dump(out, open(path_out, "w"), indent=1, ensure_ascii=False)
    print(f"OK — {len(out['events'])} event skrivna till {path_out}; "
          f"detektorparitet verifierad (SO {so}, axial {ax})")


if __name__ == "__main__":
    main()
