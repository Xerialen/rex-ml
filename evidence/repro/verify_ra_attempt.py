import json
import numpy as np

SP = "/tmp/claude-1001/-home-benjamin-adm-rex-ml/003dd697-8855-417d-9d80-53960851ebcf/scratchpad"
RA = np.array([256.0, -704.0, 304.0])
DT = 0.026

def d2(p):
    return float(np.hypot(p[0]-RA[0], p[1]-RA[1]))

d = json.load(open(f"{SP}/rex_trajectories.json"))
found = []
for ep, e in enumerate(d["episodes"]):
    path = np.asarray(e["path"], dtype=float)[:, :3]
    inside = False
    i0 = None
    z_entry = 0.0
    dmin = np.inf
    climbed = False
    suc = False
    for k, p in enumerate(path):
        dd = d2(p)
        if dd < 300.0:
            if not inside:
                inside = True; i0 = k; z_entry = p[2]; dmin = np.inf
                climbed = False; suc = False
            dmin = min(dmin, dd)
            if p[2] >= z_entry + 80.0:
                climbed = True
            if dd < 60.0 and -32.0 < p[2]-RA[2] < 80.0:
                suc = True
        elif inside:
            low = z_entry < 150.0
            if low and climbed and dmin < 120.0:
                found.append((ep, i0, k-1, z_entry, dmin, suc))
            inside = False
    if inside:
        low = z_entry < 150.0
        if low and climbed and dmin < 120.0:
            found.append((ep, i0, len(path)-1, z_entry, dmin, suc))

print("attempts found:", found)
for ep, i0, i1, z_ent, dmin, suc in found:
    path = np.asarray(d["episodes"][ep]["path"], dtype=float)[:, :3]
    print(f"\n== ep{ep} spawn={d['episodes'][ep]['spawn_zone']} interval [{i0},{i1}] "
          f"t={i0*DT:.1f}-{i1*DT:.1f}s z_entry={z_ent:.1f} d2_min={dmin:.1f} succ={suc}")
    a, b = max(0, i0-20), min(len(path), i1+21)
    for k in range(a, b, 2):
        p = path[k]
        mark = " <ENTRY" if k in (i0, i0+1) else (" <EXIT" if k in (i1, i1-1) else "")
        print(f"  k={k:5d} t={k*DT:7.2f}s xyz=({p[0]:7.1f},{p[1]:7.1f},{p[2]:6.1f}) d2RA={d2(p):6.1f}{mark}")
