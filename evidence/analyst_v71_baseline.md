# LÅST — v7.1 verifierad på alla tre kontrollpunkter: lyckat-retention 98.6 % av v6.1:s 584 äkta (576 kvar; 186 av 194 v7-felfällda räddade = 95.9 %, prognos 97 %), alla 40 ytterkantsfall→lämnade med 0 av 133 genuina gropfall tappade, 0 grazers — SLUTLIG humanbaslinje: 750 gate-event = 580 lyckat + 133 ramla + 37 retreat

## Slutlig v7.1-baslinje (analyst, 2026-08-02)

Detektor: `rl/jump_gates.py` v7.1 (oförändrad av mig; båda varningsåtgärderna
ur `evidence/analyst_v7_baseline.md` implementerade exakt enligt min formel —
dt-robust bekräftelse `grundat ELLER >=0.25 s konsekutiv dst-vistelse`,
fönster 1.4 s tidsbaserat; gropexponering dPit<260 vid fallpunkten, även i
bekräftelsefönstret). 40/40 test. Repro:
`evidence/repro/human_ledge_v71_baseline.py` (+.json) — TRIPPELSPÅRNING
v6.1/v7/v7.1 i samma transitloop, 227 assert-verifierade segment mot
detektorn, 24-demoskohorten, dt 0.051.

## SLUTLIG LÅST REGRESSIONSBASLINJE (v7.1, 24-demoskohorten, dt 0.051)

**1614 eventposter, varav 750 gate-event:**

| gate | lyckat | ramla | retreat | försök |
|---|---|---|---|---|
| ring→quad NV | 208 | 13 | 25 | 246 |
| ring→quad SO | 232 | 43 | 5 | 280 |
| quad→ring NV | 84 | 13 | 5 | 102 |
| quad→ring SO | 56 | 64 | 2 | 122 |
| **totalt** | **580** (292 NV / 288 SO) | **133** (26 NV / 107 SO) | **37** (30 NV / 7 SO) | **750** |

Kontroller: **0 grazers**, **0 oförankrade gate-ramla**; ramla-fallpunkter
dPit p10/p50/p90 = 20/98/215, max 255 (alla gropexponerade per konstruktion).
Axial (informationsspår): 794 = 497 lyckat / 291 ramla / 6 retreat.

Human-lyckandegrader per gate (för botjämförelser): ring→quad NV 85 %,
ring→quad SO 83 %, quad→ring NV 82 %, quad→ring SO 46 % (SO-gapet i
returriktningen förblir det svåraste — konsistent med v6.1-bilden).

## Verifiering (a): lyckat-retention

- v6.1:s 584 äkta gate-lyckade → **576 kvar som v7.1-gate-lyckat (98.6 %)**.
- Av v7:s 194 felfällda: **186 räddade (95.9 %**, min prognos 97 % — inom 1,1
  procentenheter). Kvarvarande 8: 4 → lämnade (ankomster utan vare sig
  grundat sampel eller 0.25 s sammanhängande vistelse — marginella
  genomflygningsgraze) och 4 → ramla (gropfall inom fönstret före bekräftad
  vistelse — äkta touch-and-fall).
- **v7:s 12 grop-inom-fönstret-ramla: 8 → lyckat, 4 → kvar ramla.** Detta
  AVVIKER från beställningens förväntan ("fortfarande ramla") men är korrekt
  per min varning 1-diagnos och per den implementerade regeln: de 8 bekräftar
  vistelse (grundat/0.25 s) FÖRE gropfallet = äkta ankomst följd av
  avsiktligt grophopp (MH-dyk); de 4 föll utan bekräftad vistelse. Jag
  godkänner avvikelsen — den är formelns avsedda semantik.
- Botregressionen påverkas inte: traj_63G ep8-fallet är fortfarande axial
  ramla (fall utan bekräftelse, gropexponerat), ep1/ep4 står (SO 2/1/1).

## Verifiering (b): ytterkantsfall

- v7-gate-ramla med fallpunkt dPit ≥ 260: **40 st → samtliga "lämnade"**
  (inget event) i v7.1. (Min v7-varning angav 26 via transit-min-dPit > 200;
  fallpunktsmåttet ger 40 — samma klass, skarpare mått.)
- v7-gate-ramla med genuint gropfall (dPit < 260): **133 av 133 behållna** —
  inget genuint gropfall tappat.
- Stickprov botdata (beställt): traj_53G:s borttappade axial är ep4
  [1915,1934] — fallet korsar z −100 vid dPit 264.6 PÅ VÄG UT (dPit ökar
  214→325 under fallet), landar vid dPit ≈ 325 och simmar därefter i vattnet
  (z −150…−185, dPit 400–490). Ytterkantsfall förbi gropens NO-hörn, inte
  gropfall — **klassningen "lämnade" är korrekt**. traj_53G v7.1 = axial
  2 (1 ramla + 1 retreat), övriga dumpar enligt beställningen (63G SO 2/1/1 +
  axial 2/0/2; probe 1/0/1; 0907 0).

## Verifiering (c): grazers

0 gate-event med massa < 14 u·s (per konstruktion + verifierat i utfallet).

## Övergångar v7 → v7.1 (exakta, per transit)

oförändrade 1211; gate-ramla→gate-lyckat 8; gate-ramla→inget 40;
inget→gate-lyckat 179; inget→axial-lyckat 154; axial-ramla→inget 17;
axial-ramla→axial-lyckat 4; axial-ramla→gate-lyckat 1.

## Kvarstående övervakningspunkter (inga blockerare)

1. Retreat har inget gropexponeringskrav (design: inget fall inblandat) —
   "vandra-ut-och-tillbaka" på breda sidogolvet bokförs som försök med
   retreat-utfall (37 human, 24 aldrig nära gropen). Ofarligt i humandata
   men kan inflatera botens försöksnämnare vid nivå 3-bedömning — övervaka
   retreat-andelen i botdumpar.
2. Bhop-underdetektion vid 26 ms (kvarstår från v6-listan).
3. Plattformscirkeln (r 260), gropcirkeln (r 260) och maskens t-fönster är
   modeller, inte BSP — gropcirkeln verifierad mot 53G-ep4-stickprovet men
   inte uttömmande mot gropens hexagonala geometri.

## Repro

```
cd ~/rex-ml
.venv/bin/python evidence/repro/human_ledge_v71_baseline.py
  # ⇒ 227 segment; gate 580/133/37; retention 576/584; 40 ytterkant→lämnade; 0 grazers
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/traj_63G.json      # SO 2/1/1, axial 2/0/2
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ledge_60G.json  # SO 1/0/1
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/traj_53G.json      # axial 2
PYTHONPATH=. sim/.venv-sf/bin/python -m pytest rl/tests/ -q                      # 40 passed
```

Konfidens: hög. Baslinjen LÅST för framtida omvalideringar av denna kohort.
