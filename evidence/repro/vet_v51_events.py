#!/usr/bin/env python
"""Vetogranskning v5.1: instrumenterat spår av gate-kvalificerade event
(ep5 i probe_ledge_60G + ev. event i traj_53G). Assert-verifierar spåret mot
jg._ring_quad_events och dumpar transitsegmentets fulla mätserie.

Kör: cd ~/rex-ml && PYTHONPATH=. sim/.venv-sf/bin/python \
       evidence/repro/vet_v51_events.py <dump.json> [ep ...]
"""
import json
import sys

import numpy as np

import rl.jump_gates as jg
from rl.jump_gates import (HEX_R, LEDGE_Z, MAX_TRANSIT_PTS, PIT_2D, PIT_Z,
                           PLAT_ZBAND, PROGRESS_D, PROGRESS_D_BAND, QUAD,
                           RING, SAMPLE_DT, SIDE_DEADZONE, SIDE_LEDGE_MAX,
                           SIDE_MIN_MASS_US, _d2, _grounded, _plat, _side)


def trace(path, dt):
    events = []
    cur = _plat(path[0])
    t0 = 0
    i = 1
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
        onto_ledge = progressed = raw_progressed = False
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
                if _d2(q, dst_c) < PROGRESS_D:
                    raw_progressed = True
                if PLAT_ZBAND[0] < q[2] < PLAT_ZBAND[1]:
                    s = _side(q)
                    if SIDE_DEADZONE < abs(s) < SIDE_LEDGE_MAX:
                        onto_ledge = True
                    if abs(s) > SIDE_DEADZONE:
                        side_acc += s
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
        side_ok = abs(side_acc) * dt >= SIDE_MIN_MASS_US
        dst = "quad" if cur == "ring" else "ring"
        if onto_ledge and progressed and side_ok \
                and outcome in ("lyckat", "ramla", "retreat"):
            events.append({"hopp": f"{cur}→{dst} {'NV' if side_acc > 0 else 'SO'}",
                           "utfall": outcome, "t0": t0, "j": j,
                           "side_acc": side_acc, "gate": True})
        elif (raw_progressed or progressed) and outcome in ("lyckat", "ramla",
                                                            "retreat"):
            events.append({"hopp": f"axial {cur}→{dst}", "utfall": outcome,
                           "t0": t0, "j": j, "side_acc": side_acc,
                           "gate": False})
        cur = _plat(path[j]) if j < len(path) else None
        t0 = j
        i = j + 1
    return events


def show(path, ev, dt, every=1):
    g = _grounded(path)
    t0, j = ev["t0"], ev["j"]
    k = t0
    curplat = _plat(path[t0])
    while k > 0 and _plat(path[k - 1]) == curplat:
        k -= 1
    grounded_plat = int(g[k:t0 + 1].sum())
    tr = path[t0 + 1:j + 1]
    band = [(s, path[s]) for s in range(t0 + 1, j + 1)
            if _plat(path[s]) is None and path[s][2] > LEDGE_Z
            and PLAT_ZBAND[0] < path[s][2] < PLAT_ZBAND[1]]
    band_g = [s for s, p in band if g[s]]
    inledge = [s for s, p in band if SIDE_DEADZONE < abs(_side(p)) < SIDE_LEDGE_MAX]
    dsts = RING if curplat == "quad" else QUAD
    print(f"\nEVENT {ev['hopp']} ({ev['utfall']}), gate={ev['gate']}, "
          f"side_acc={ev['side_acc']:.0f} (massa {abs(ev['side_acc'])*dt:.0f} u·s)")
    print(f"  plattformsvistelse {k}..{t0}: {(t0-k+1)} pkt = "
          f"{(t0-k+1)*dt:.2f} s, {grounded_plat} grundade")
    print(f"  transit {t0}..{j} = {(j-t0)*dt:.2f} s; bandsampel {len(band)} "
          f"({len(band)*dt:.2f} s), varav grundade {len(band_g)}, "
          f"i ledgebandet(100-300) {len(inledge)}")
    print(f"  {'idx':>5} {'t(s)':>6} {'x':>7} {'y':>7} {'z':>7} "
          f"{'dDst':>6} {'perp':>6} {'dPit':>6} plat grd")
    lo, hi = max(0, k - 2), min(len(path), j + 4)
    for s in range(lo, hi, every):
        q = path[s]
        mark = "<T0" if s == t0 else ("<J" if s == j else "")
        print(f"  {s:>5} {s*dt:>6.2f} {q[0]:>7.1f} {q[1]:>7.1f} {q[2]:>7.1f} "
              f"{_d2(q, dsts):>6.0f} {_side(q):>+6.0f} {_d2(q, PIT_2D):>6.0f} "
              f"{str(_plat(q)):>4} {int(g[s])}   {mark}")


def main():
    dump = json.load(open(sys.argv[1]))
    dt = float(dump.get("dt", SAMPLE_DT))
    only = set(map(int, sys.argv[2:]))
    for ei, ep in enumerate(dump["episodes"]):
        path = np.asarray(ep["path"], dtype=float)
        evs = trace(path, dt)
        official = jg._ring_quad_events(path, dt=dt)
        assert [{"hopp": e["hopp"], "utfall": e["utfall"]} for e in evs] \
            == official, f"trace != detektor ep {ei}"
        if evs:
            print(f"== ep {ei}: {[(e['hopp'], e['utfall']) for e in evs]}")
        if only and ei not in only:
            continue
        for ev in evs:
            if ev["gate"] or ei in only:
                show(path, ev, dt, every=2 if ev["j"] - ev["t0"] > 80 else 1)


if __name__ == "__main__":
    main()
