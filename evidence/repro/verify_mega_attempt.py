"""Repro: SNG-mega-"försöket" i ~/dumps/traj_53G.json (episod 6, sampel 2248-slut).

Visar entré-z, z-kurvan, d2-kurvan och samtidighetssamplen som triggade
detektorns (rl/jump_gates.py) enda mega-försök, plus den fysikaliska
dekompositionen via gravitationsfit (andradifferens av z ≈ −800·0.026² =
−0.541/sampel² ⇒ luftburen): hela "klättringen" är två kedjade bunnyhops
in i NO-hörnets väggar — ingen stödd yta över golvet nås utom en
ensamplig touch på ett ~26-enheterssteg mellan hoppen.

Kör:  PYTHONPATH=~/rex-ml ~/rex-ml/sim/.venv-sf/bin/python \
        ~/rex-ml/evidence/repro/verify_mega_attempt.py [dump]
Granskning: evidence/analyst_megattempt_review.md (UNDERKÄND, 2026-08-02).
"""
import json
import sys

import numpy as np

from rl.jump_gates import APPROACH_MIN, CLIMB_GAIN, MEGA_SNG, _d2

DUMP = sys.argv[1] if len(sys.argv) > 1 else \
    "/home/benjamin-adm/dumps/traj_53G.json"
EP = 6
GRAV_DD = 800.0 * 0.026 ** 2          # 0.541 u/sampel² @ 26 ms

ep = json.load(open(DUMP))["episodes"][EP]
path = np.asarray(ep["path"], dtype=float)
d = np.array([_d2(p, MEGA_SNG) for p in path])
z = path[:, 2]

# 1) Detektorns besöksintervall (d<300) med låg entré
inside = np.flatnonzero(d < 300.0)
s0 = int(inside[np.flatnonzero(
    np.diff(np.concatenate([[-9], inside])) > 1)][-1])
s1 = len(path) - 1
z_entry = z[s0]
print(f"episod {EP}: intervall sampel {s0}..{s1} "
      f"({(s1 - s0) * 0.026:.1f} s, ÖPPET vid episodslut)")
print(f"entré-z = {z_entry:.1f}  (låg-villkor z<100: {z_entry < 100})")

# 2) Samtidighetsvillkoret: z >= entré+80 OCH d2<120 i samma sampel
simul = np.flatnonzero((z >= z_entry + CLIMB_GAIN) & (d < APPROACH_MIN)
                       & (np.arange(len(path)) >= s0))
print(f"samtidighetssampel: {simul.tolist()}  "
      f"(z {z[simul].min():.1f}-{z[simul].max():.1f}, "
      f"d2 {d[simul].min():.1f}-{d[simul].max():.1f})")

# 3) Luftburenhet via gravitationsfit på intervallet
zz = z[s0:s1 + 1]
air = np.zeros(len(zz), bool)
for i in np.flatnonzero(np.abs(np.diff(zz, 2) + GRAV_DD) < 0.15):
    air[i:i + 3] = True

print(f"\n{'sampel':>6} {'x':>8} {'y':>7} {'z':>6} {'spd':>5} {'d2':>6}  fas")
for i in range(s0, s1 + 1):
    p = path[i]
    fas = "LUFTBUREN (gravitationsfit)" if air[i - s0] else "stödd"
    if 2270 <= i <= 2285 and air[i - s0]:
        fas += ", väggslide y=144.0 (fart 471->194)"
    if 2286 <= i <= 2299:
        fas = "LUFTBUREN, andra väggen x=-800.0 (fart 46), fritt fall"
    mark = " <== SIMUL" if i in simul else ""
    print(f"{i:>6} {p[0]:8.1f} {p[1]:7.1f} {p[2]:6.1f} {p[3]:5.0f} "
          f"{d[i]:6.1f}  {fas}{mark}")

# 4) Nyckelmått för domslutet
sup = zz[~air]
print(f"\nmax STÖDD z i intervallet: {sup.max():.1f} "
      f"(entré {z_entry:.0f} + {sup.max() - z_entry:.0f}; "
      f"touch z~26-27 vid 2269-2270 är 1-2 sampel = bhop-mellanlandning)")
print(f"max z i intervallet (luftburen apex): {zz.max():.1f}")
print(f"hopp 1: takeoff ~2253 från z=-16, apex 27.8 @2266 (vz~265);")
print(f"hopp 2: takeoff ~2270 från steget z~26, apex 67.8 @2282 (vz~250),")
print(f"samtidigt väggkollision y=144 (fart 471->194), sen x=-800 (fart 46).")
print("mänsklig nerifrån-väg (store-dm3, 21/24 låg-entré-tagningar av 352 "
      "totalt; 93 % tar megan uppifrån): trappsteg origin 24..104 -> STÖDD "
      "platå origin 120 (= golv -16 + 136) vid x -896..-960, y 32..96 -> "
      "hopp apex ~163 nuddar megan (z 160).")
print("botten: max stödd z = golvet -16; apex 67.8 är 20 u under trappsteget "
      "origin 88 och 92 u under mega-z 160; hopppunkten (y=144-väggen, "
      "NO-hörnet) ligger på motsatt sida om trappbasen (bottten passerade "
      "trappbasens x vid y=-199..-109 utan att engagera den).")
