#!/usr/bin/env python
"""Vetogranskning av ledgeprobe-claimet (probe_ledge_60G.json, gate2_v2 @6.0G).

Instrumenterar rl.jump_gates._ring_quad_events utan att ändra detektorn:
återimplementerar samma loop med spårning, verifierar att eventlistan blir
identisk med detektorns, och dumpar det exakta transitsegmentet
(episod, sampleindex, x/y/z, d(ring), d(quad), perp, plattform, grundat).

Kör: cd ~/rex-ml && PYTHONPATH=. sim/.venv-sf/bin/python \
       evidence/repro/vet_ledgeprobe.py ~/dumps/probe_ledge_60G.json
"""
import json
import sys

import numpy as np

from rl.jump_gates import (HEX_R, LEDGE_Z, MAX_TRANSIT_PTS, PIT_2D, PIT_Z,
                           PROGRESS_D, QUAD, RING, SIDE_DEADZONE, _d2,
                           _grounded, _plat, _ring_quad_events, _side, analyze)

DT = 0.026  # 26 ms per path-punkt (var 2:e tick)


def trace_episode(path):
    """Samma tillståndsmaskin som _ring_quad_events, men returnerar även
    (t0, j, cur, dst) för varje räknat event."""
    events = []
    cur = _plat(path[0])
    t0 = 0
    i = 1
    while i < len(path):
        p = path[i]
        plat = _plat(p)
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
            events.append({"hopp": f"{cur}→{dst} {side}", "utfall": outcome,
                           "t0": t0, "j": j, "side_acc": side_acc})
        cur = _plat(path[j]) if j < len(path) else None
        t0 = j
        i = j + 1
    return events


def main():
    dump = json.load(open(sys.argv[1]))
    print("== Detektorns officiella utfall ==")
    print(json.dumps(analyze(dump)["gates"]["quad→ring SO"], ensure_ascii=False))
    for ei, ep in enumerate(dump["episodes"]):
        path = np.asarray(ep["path"], dtype=float)
        official = _ring_quad_events(path)
        traced = trace_episode(path)
        assert [{"hopp": e["hopp"], "utfall": e["utfall"]} for e in traced] \
            == official, f"trace != detektor i ep {ei}"
        p0 = path[0]
        print(f"\nep {ei}: spawn=({p0[0]:.0f},{p0[1]:.0f},{p0[2]:.0f}) "
              f"perp={_side(p0):+.0f} dRing={_d2(p0, RING):.0f} "
              f"dQuad={_d2(p0, QUAD):.0f} plat={_plat(p0)} "
              f"samples={len(path)} events={official}")
        for ev in traced:
            t0, j = ev["t0"], ev["j"]
            g = _grounded(path)
            # Hur länge var botten på cur-plattformen före lämningen?
            k = t0
            curplat = _plat(path[t0])
            while k > 0 and _plat(path[k - 1]) == curplat:
                k -= 1
            grounded_on_plat = int(g[k:t0 + 1].sum())
            print(f"  EVENT {ev['hopp']} ({ev['utfall']}): "
                  f"plattformsvistelse sampel {k}..{t0} "
                  f"({(t0 - k + 1)} pkt = {(t0 - k + 1) * DT:.2f} s, "
                  f"{grounded_on_plat} grundade), transit {t0}..{j} "
                  f"({(j - t0) * DT:.2f} s), side_acc={ev['side_acc']:.0f}")
            lo = max(0, k - 3)
            hi = min(len(path), j + 4)
            print(f"  {'idx':>5} {'t(s)':>6} {'x':>7} {'y':>7} {'z':>7} "
                  f"{'dRing':>6} {'dQuad':>6} {'perp':>6} {'dPit':>6} "
                  f"plat grd")
            for s in range(lo, hi):
                q = path[s]
                mark = ("<T0" if s == t0 else ("<J" if s == j else ""))
                print(f"  {s:>5} {s * DT:>6.2f} {q[0]:>7.1f} {q[1]:>7.1f} "
                      f"{q[2]:>7.1f} {_d2(q, RING):>6.0f} {_d2(q, QUAD):>6.0f} "
                      f"{_side(q):>+6.0f} {_d2(q, PIT_2D):>6.0f} "
                      f"{str(_plat(q)):>4} {int(g[s])}   {mark}")


if __name__ == "__main__":
    main()
