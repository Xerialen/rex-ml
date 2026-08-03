#!/usr/bin/env python
"""Rekonstruktion av 8.9G-gate-eventen (analyst-review 11, 2026-08-03).

EVENT A: traj_89G.json ep8 — "ring→quad NV ramla" (första fria NV-kandidaten)
EVENT B: probe_ledge_89G.json ep4 — "quad→ring SO ramla" (ledge-spawnad prob)

Instrumenterar detektorns egna funktioner (jg._ring_quad_events för
eventgränser; _plat/_on_ledge/_grounded/_side/_d2 för per-sampel-diagnos).

Kör:  cd ~/rex-ml && PYTHONPATH=. sim/.venv-sf/bin/python \
          evidence/repro/review_89G_events.py
"""
import json
import sys

import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg  # noqa: E402
from rl.jump_gates import (PIT_2D, PIT_EXPOSURE_R, PIT_Z, QUAD, RING,
                           SAMPLE_DT, _d2, _grounded, _on_ledge, _plat,
                           _side)

AX = (QUAD - RING)[:2]


def review(dump_fn, ep_i, want_hopp):
    d = json.load(open(dump_fn))
    dt = float(d.get("dt", SAMPLE_DT))
    path = np.asarray(d["episodes"][ep_i]["path"], dtype=float)
    evs = [e for e in jg._ring_quad_events(path, dt=dt)
           if e["hopp"] == want_hopp]
    assert len(evs) == 1, evs
    ev = evs[0]
    i0, i1 = ev["i0"], ev["i1"]
    print(f"\n{'=' * 72}\n{dump_fn} ep {ep_i}: {ev['hopp']} — {ev['utfall']} "
          f"[{i0},{i1}] ({(i1 - i0) * dt:.2f} s), dt={dt}")
    g = _grounded(path)
    src = RING if want_hopp.startswith("ring") else QUAD
    dst = QUAD if want_hopp.startswith("ring") else RING

    # källplattformsvistelsen (bakåt från i0)
    k = i0
    while k > 0 and _plat(path[k - 1]) == _plat(path[i0]):
        k -= 1
    n_src_g = int(g[k:i0 + 1].sum())
    print(f"källvistelse [{k},{i0}] ({(i0 - k) * dt:.2f} s), plat="
          f"{_plat(path[i0])}, grundade sampel: {n_src_g}")

    side_acc = 0.0
    n_mask = n_anchored = 0
    min_dpit = min_ddst = 1e9
    expo = 0
    fall = None
    rows = []
    for i in range(i0 + 1, i1 + 1):
        p = path[i]
        dpit = _d2(p, PIT_2D)
        ddst = _d2(p, dst)
        perp = _side(p)
        tax = float(((p[:2] - RING[:2]) @ AX) / (AX @ AX))
        onl = _on_ledge(p)
        pl = _plat(p)
        min_dpit = min(min_dpit, dpit)
        min_ddst = min(min_ddst, ddst)
        expo += int(dpit < PIT_EXPOSURE_R)
        if pl is None and p[2] > jg.LEDGE_Z and onl:
            side_acc += perp
            n_mask += 1
            if g[i]:
                n_anchored += 1
        if p[2] <= PIT_Z and fall is None:
            fall = (i, p.copy(), dpit)
        rows.append((i, p[0], p[1], p[2], round(dpit, 1), round(ddst, 1),
                     round(perp, 1), round(tax, 3),
                     "mask" if onl else "-", "G" if g[i] else "-",
                     pl or "-"))
    print(f"transit: min dPit {min_dpit:.1f}, min d(dst) {min_ddst:.1f}, "
          f"expo {expo} sampel = {expo * dt:.2f} s")
    print(f"masksampel {n_mask} (grundade {n_anchored}); "
          f"side_acc {side_acc:.1f} => massa {abs(side_acc) * dt:.1f} u·s "
          f"(krav >= {jg.SIDE_MIN_MASS_US})")
    if fall:
        print(f"gropfall i transiten: i={fall[0]} pos "
              f"({fall[1][0]:.0f},{fall[1][1]:.0f},{fall[1][2]:.0f}) "
              f"dPit {fall[2]:.1f}")
    # efterspel (bekräftelse-/fallfönster efter i1)
    for j in range(i1, min(len(path), i1 + int(round(1.4 / dt)) + 1)):
        p = path[j]
        if p[2] <= PIT_Z:
            print(f"efterspel: gropfall i={j} pos ({p[0]:.0f},{p[1]:.0f},"
                  f"{p[2]:.0f}) dPit {_d2(p, PIT_2D):.1f} "
                  f"({(j - i1) * dt:.2f} s efter i1)")
            break
    print(f"\n{'i':>5} {'x':>7} {'y':>7} {'z':>7} {'dPit':>6} {'dDst':>6} "
          f"{'perp':>7} {'tax':>6} mask G plat")
    for r in rows:
        print(f"{r[0]:>5} {r[1]:>7.0f} {r[2]:>7.0f} {r[3]:>7.1f} {r[4]:>6} "
              f"{r[5]:>6} {r[6]:>7} {r[7]:>6} {r[8]:>4} {r[9]} {r[10]}")


review("/home/benjamin-adm/dumps/traj_89G.json", 8, "ring→quad NV")
review("/home/benjamin-adm/dumps/probe_ledge_89G.json", 4, "quad→ring SO")
