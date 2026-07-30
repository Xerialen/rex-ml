# Ceiling 850-sökning på 100m.bsp — metod, resultat, slutsats

**Fråga:** ägarens submål är peak 850 u/s på 100m.bsp. Uppmätt analytiskt tak var
833,4 (evidence/strafe_ceiling_qwsim.json). Finns en känd-fysik-väg till 850?

**Svar: JA — verifierat 924,1 u/s FÖRE mållinjen med ärlig 77 Hz-klient (msec=13).**
Nyckeln är inte msec-trixande utan **banlängd**: serpentinväg mellan väggarna.

Verktyg: `sim/ceiling_850_search.py` (libqwsim, bit-exakt mvdsv-pmove, karta
checksum2 86ae4c54). Full data: `evidence/ceiling_850_search.json`.

## Fysikgrund (verifierad ur sim/csrc/pmove.c)
- +900 u²/s² per luftburen tick (addspeed-cappen 30 binder alltid), oberoende av dt.
- Perfekt bunny är friktionsfri ⇒ v³ ≈ v0³ + 1350·L_bana/dt — taket sätts av BANLÄNGD.
- **Svängar är gratis i v²:** samma vinkelräta +30-add som accelererar är det som
  svänger velocity. Kostnaden är bara korridorbredd (svängradie r = v²·dt/30,
  ~313 u vid 850). Serpentin med kursoffset ±φ ger banfaktor 1/cos φ.

## Geometri (trace-probad, inte antagen)
Korridor x∈[−256,768] (1024 bred), y∈[−2176,3584], platt golv z=0, tak z=256.
Startgrind: 40-hög kant y≈−1680 (x 0..512) + stolpar x 600..616 och −104..−92
(från y≈−1528) — fria filer x 636..736 och −240..−124. Målskylt y≈3068 är
SVÄVANDE (z 104..128) — passerbar under/förbi. Inga ramper/trappor; airstep=0,
rampjump=0, bunnyspeedcap=0 ⇒ inga vertikala tricks finns på kartan (metod 3: nej).

## Resultat (peak vid/före mål-y 2900, 8 startfaser per rad)

| Metod | msec | max | median | ≥850 |
|---|---|---|---|---|
| A. Rak (replikation av 833,4) | 13 | 833,4 | 826,7 | 0/8 |
| B. Serpentin φ=25° | 13 | 852,1 | 744,2 | 1/8 |
| B. Serpentin φ=35° | 13 | 862,2 | 751,5 | 1/8 |
| B. Serpentin φ=45° | 13 | 860,7 | 790,8 | 2/8 |
| **B. Serpentin φ=55°** | **13** | **924,1** | 798,7 | 1/8 |
| C. Bakstart (y≈−2080) rak | 13 | 845,4 | 797,2 | 0/8 |
| C. Bakstart + serpentin φ=55° | 13 | 877,3 | 798,4 | 2/8 |
| E. Bästa konfig, äkta 77 Hz-mix (12/13) | mix | 905,6 | 788,4 | 1/8 |
| D. Overrun FÖRBI mål (till y≈3480) | 13 | 938,6 | 851,8 | — separat regim |
| F. msec=12 (kräver 83,3 cmd/s) | 12 | 926,3 | 825,2 | protokollutnyttjande |
| F. msec=6 (kräver 166,7 cmd/s) | 6 | 896,3 | 809,7 | protokollutnyttjande |

## Verifiering av bästa ärliga körningen (tick-loggad, fristående reproduktion)
Konfig: msec=13 rent, φ=55°, yaw0=315, ingen bakstart, ingen overrun.
- Reproducerad peak **924,1** = grid-peaken (exakt match).
- Peak-tick: t=10 036 ms, y=2904,6 (själva målpasseringsticken), x=218,6.
- **850 passeras första gången vid t=8 138 ms, y=1763** — 1137 u FÖRE mållinjen.
- Launch 488,2 u/s vid y=−1501; 13 blockade ticks (väggskrap) under körningen;
  x-svep −177..687. Fartkurva var 10:e tick + peakfönster ligger i JSON:ens
  `verification`-block.

## msec-regimen (ur vendor/mvdsv-src/src/sv_user.c, SV_RunCmd)
AM101 (sv_speedcheck, default 1, sv_main.c:133) klipper ett kommandos msec **bara
nedåt när begärd msec > förfluten väggklocketid** (+ bank, cappad 500 ms);
msec>50 delas rekursivt. **Ingen undre gräns finns** — servern accepterar msec≥1
så länge cmd-takten ≤ 1000/msec Hz i väggtid. Ärlig 77 Hz-klient = 76×13+1×12 ms.
msec=12 kräver 83,3 cmd/s, msec=6 kräver 166,7 cmd/s — över 77 fps-standarden ⇒
redovisas som protokollutnyttjande, separat från ärliga siffror. Mätningen visar
dessutom att det INTE behövs: ärlig 13-ström slår både 12 och 6 här (924 vs
926/896 — styrningen, inte dt, är flaskhalsen i de regimerna).

## Slutsats
1. **850 är nåbart med känd fysik i ärlig 77 Hz-regim** — via serpentinväg
   (banlängdsköp), inte via uppskjut, vertikala tricks eller msec. Bevisat med
   bit-exakt fysik och tick-logg: peak 924,1 före mål, 850 passerat redan vid
   y=1763.
2. Rangordning av metoderna: serpentin ≫ bakstart (+12 u/s rak) ≫ msec-trixande
   (onödigt) ≫ vertikalt (finns inte på kartan).
3. **Robusthetsförbehåll:** fasmedianen ligger under 850 (799 vid φ=55°) — det
   analytiska taket 924 kräver bra launchfas och ren väv. För policyträningen
   betyder det: 850 är ett legitimt men elitnivå-mål; korridorens raka tak utan
   väv är fortfarande ~833.
