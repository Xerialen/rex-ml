"""RA-noteringen i vetogranskningen (evidence/analyst_breakthrough_review.md):
dissekera varje RA-besök (d2<300) i traj_63G per sampel mot gate-villkoren
(gain>=+80 OCH d2<120 OCH grundat, SAMTIDIGT) och jämför med närhetsmätarens
per-besök-aggregat (zgain_max, d2min_elev40).

Kör:  cd ~/rex-ml && PYTHONPATH=. sim/.venv-sf/bin/python \
        evidence/repro/breakthrough_63G_ra_check.py ~/dumps/traj_63G.json
Väntat: 0 sampel i HELA dumpen uppfyller gain>=80 & d2<120 (grundat eller ej);
+202-besöket (ep3) har d2min_elev40 = 176.0; 64.5-besöket (ep6) har zgain +44.
"""
import json
import sys

import numpy as np

from rl.jump_gates import RA, _d2, _grounded


def main():
    d = json.load(open(sys.argv[1]))
    n_joint = n_joint_g = 0
    for e, ep in enumerate(d["episodes"]):
        p = np.asarray(ep["path"], float)[:, :3]
        g = _grounded(p)
        inside = False
        for i in range(len(p) + 1):
            dd = _d2(p[i], RA) if i < len(p) else 1e9
            if dd < 300.0 and i < len(p):
                if not inside:
                    inside, z_entry, samp = True, p[i][2], []
                samp.append(i)
            elif inside:
                inside = False
                zg = max(p[k][2] - z_entry for k in samp)
                e40 = [_d2(p[k], RA) for k in samp if p[k][2] >= z_entry + 40]
                joint = [k for k in samp
                         if p[k][2] >= z_entry + 80 and _d2(p[k], RA) < 120]
                n_joint += len(joint)
                n_joint_g += sum(bool(g[k]) for k in joint)
                if zg >= 80 or (e40 and min(e40) < 130):
                    print(f"ep{e} [{samp[0]},{samp[-1]}] z_entry {z_entry:.0f} "
                          f"zgain_max {zg:.0f} "
                          f"d2min_elev40 {min(e40):.1f} "
                          f"sampel(gain>=80 & d<120) {len(joint)}")
    print(f"TOTALT sampel med gain>=80 & d2<120: {n_joint} "
          f"(varav grundade: {n_joint_g})")
    assert n_joint == 0, "RA-gatens nolla beror INTE på samtidighetsvillkoret?"


if __name__ == "__main__":
    main()
