"""Instrumentering av de två 7.3G-eventen (spegling, assertad mot detektorn)."""
import json
import sys

import numpy as np

sys.path.insert(0, "/home/benjamin-adm/rex-ml")
import rl.jump_gates as jg
from rl.jump_gates import (RA, PIT_2D, PIT_EXPOSURE_R, QUAD, RING,
                           APPROACH_MIN, CLIMB_GAIN, _d2, _grounded, _side,
                           _on_ledge, _plat)

# ---------- EVENT A: traj_73G ep20, RA-intervall ----------
d = json.load(open("/home/benjamin-adm/dumps/traj_73G.json"))
path = np.asarray(d["episodes"][20]["path"], dtype=float)[:, :3]
att, suc, evs = jg._item_events(path, RA, 300.0, lambda p: p[2] < 150.0)
print("== EVENT A: traj_73G ep20 ==")
print("detektor (hela ep):", att, suc, evs)
ev = evs[0]
i0, i1 = ev["i0"], ev["i1"]
g = _grounded(path)
seg = path[i0:i1 + 1]
z_entry = path[i0][2]
d2s = np.array([_d2(p, RA) for p in seg])
simult = [i for i in range(i0, i1 + 1)
          if path[i][2] >= z_entry + CLIMB_GAIN and _d2(path[i], RA) < APPROACH_MIN
          and g[i]]
print(f"intervall [{i0},{i1}] n={i1-i0+1} dur={(i1-i0+1)*0.026:.2f}s "
      f"z_entry={z_entry:.1f} min_d2={d2s.min():.1f}")
print(f"simultana sampel (grundade, z>=entré+80, d2<120): {len(simult)} -> {simult}")
for i in simult:
    p = path[i]
    print(f"  i={i} pos=({p[0]:.0f},{p[1]:.0f},{p[2]:.1f}) d2={_d2(p,RA):.1f} "
          f"z-entré={p[2]-z_entry:.1f}")
# grundade platåer i intervallet
gi = [i for i in range(i0, i1 + 1) if g[i]]
print(f"grundade sampel i intervallet: {len(gi)}/{i1-i0+1}")
lv = {}
for i in gi:
    lv.setdefault(round(path[i][2]), []).append(i)
for z in sorted(lv):
    idx = lv[z]
    dmin = min(_d2(path[i], RA) for i in idx)
    print(f"  grundad nivå z={z:+5d} (entré{z-z_entry:+.0f}): n={len(idx)} "
          f"idx {idx[0]}..{idx[-1]} d2min={dmin:.1f}")
# max grundad z; max z alls
zg = max(path[i][2] for i in gi) if gi else None
print(f"max grundad z={zg:.1f} (entré+{zg-z_entry:.1f}); max z alls={seg[:,2].max():.1f} "
      f"(entré+{seg[:,2].max()-z_entry:.1f})")
# banutskrift var 4:e sampel
print("bana (var 4:e sampel):")
for i in range(i0, i1 + 1, 4):
    p = path[i]
    v = np.hypot(*(path[min(i+1, len(path)-1)][:2] - path[max(i-1,0)][:2])) / (2*0.026)
    print(f"  i={i} t={i*0.026:6.2f} ({p[0]:7.1f},{p[1]:7.1f},{p[2]:6.1f}) "
          f"d2RA={_d2(p,RA):6.1f} v2d={v:5.0f} {'G' if g[i] else '.'}")
# efterspel: vart tog boten vägen efter exit?
print("efterspel i1+1..i1+40 (var 4:e):")
for i in range(i1 + 1, min(len(path), i1 + 41), 4):
    p = path[i]
    print(f"  i={i} ({p[0]:7.1f},{p[1]:7.1f},{p[2]:6.1f}) d2RA={_d2(p,RA):6.1f}")

# ---------- EVENT B: probe_ledge_73G ep8, NV-retreat ----------
print("\n== EVENT B: probe_ledge_73G ep8 ==")
d = json.load(open("/home/benjamin-adm/dumps/probe_ledge_73G.json"))
path = np.asarray(d["episodes"][8]["path"], dtype=float)[:, :3]
evs = jg._ring_quad_events(path)
print("detektor (hela ep):", evs)
ev = [e for e in evs if e["utfall"] == "retreat" and not e["hopp"].startswith("axial")][0]
t0, j1 = ev["i0"], ev["i1"]
g = _grounded(path)
seg = path[t0:j1 + 1]
dpit = np.array([_d2(p, PIT_2D) for p in seg])
dq = np.array([_d2(p, QUAD) for p in seg])
exposed = dpit < PIT_EXPOSURE_R
runs = []
r = 0
for e in exposed:
    r = r + 1 if e else 0
    runs.append(r)
print(f"transit [{t0},{j1}] n={len(seg)} dur={len(seg)*0.026:.2f}s "
      f"z {seg[:,2].min():.1f}..{seg[:,2].max():.1f}")
print(f"min dPit={dpit.min():.1f} @ i={t0+int(dpit.argmin())}; "
      f"exponerade sampel (dPit<260): {int(exposed.sum())}; "
      f"max konsekutiv run: {max(runs)}")
imin = t0 + int(dpit.argmin())
for i in range(max(t0, imin - 4), min(j1, imin + 5)):
    p = path[i]
    v = np.hypot(*(path[i+1][:2] - path[i-1][:2])) / (2*0.026)
    # radialhastighet mot gropen (negativ = närmar sig)
    rdot = (_d2(path[i+1], PIT_2D) - _d2(path[i-1], PIT_2D)) / (2*0.026)
    print(f"  i={i} ({p[0]:7.1f},{p[1]:7.1f},{p[2]:6.1f}) dPit={_d2(p,PIT_2D):6.1f} "
          f"dQuad={_d2(p,QUAD):6.1f} perp={_side(p):6.1f} v2d={v:5.0f} "
          f"rdotPit={rdot:+6.0f} {'G' if g[i] else '.'}{' <MIN' if i==imin else ''}")
print(f"min dQuad={dq.min():.1f} @ i={t0+int(dq.argmin())}")
print(f"start=({path[t0][0]:.0f},{path[t0][1]:.0f},{path[t0][2]:.0f}) "
      f"slut=({path[j1][0]:.0f},{path[j1][1]:.0f},{path[j1][2]:.0f})")
# axialprojektion t och perp över transiten
AX = (QUAD - RING)[:2]
tax = ((seg[:, :2] - RING[:2]) @ AX) / (AX @ AX)
perp = np.array([_side(p) for p in seg])
print(f"tax min/max: {tax.min():.3f}/{tax.max():.3f}; "
      f"perp min/med/max: {perp.min():.0f}/{np.median(perp):.0f}/{perp.max():.0f}")
print("bana (var 6:e sampel):")
for k in range(0, len(seg), 6):
    i = t0 + k
    p = seg[k]
    print(f"  i={i} t={k*0.026:5.2f} ({p[0]:7.1f},{p[1]:7.1f},{p[2]:6.1f}) "
          f"dPit={dpit[k]:6.1f} dQuad={dq[k]:6.1f} tax={tax[k]:5.2f} "
          f"perp={perp[k]:5.0f} {'G' if g[i] else '.'} {'EXP' if exposed[k] else ''}")
