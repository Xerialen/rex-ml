# FAS1-VALIDERING: **avstampspunkt KANONISERAS** (alla percentiler reproducerade exakt; rätta dock citatet "1031 maskcentra" → 410) — **anloppsfart KORRIGERAS** (humansiffrorna är dt-artefakter: kohorten är INTE uniform 51 ms utan 13/14/16/34/51 ms per demo; fast dt=0.051 krossar farterna i 460/726 event med upp till 3.9×. Rättade kanoniska värden: human-lyckat p50 **372.8** / p90 **418.6** / max **451.4**, human-ramla p50 **362.7** — inte 271.6/388.8/443.7/242.7. Riktningsclaimet "ramla långsammare än lyckat" ÖVERLEVER (håller i varje dt-stratum, −7..−19 u/s), men gap-slutsatsen "boten anlöper bortom mänsklig regim" FALLER: botens 413–456 u/s ligger i humana toppdecilen, inte utanför enveloppen)

## Validering av ultracode-fas1 (analyst, 2026-08-03)

Granskat: `evidence/ultra_jump_conversion.json`, fältet `fas1_dimensioner`
(kritiska dimensioner: anloppsfart, avstampspunkt). Egen oberoende
reproduktion i `evidence/repro/review_96G_human.py` (samma kohortladdning
som de låsta baslinjepassen; detektorpasset reproducerar 580/133/13 exakt,
så eventpopulationen är identisk med workflow-agenternas).

```
cd ~/rex-ml
PYTHONPATH=. .venv/bin/python evidence/repro/review_96G_human.py
  # -> evidence/repro/review_96G_human.json  (726 event, fas1-mått + seg_dt)
PYTHONPATH=. .venv/bin/python evidence/repro/review_96G_human.py windows
  # -> evidence/repro/review_96G_human_windows.json (dt-korrekta farter,
  #    tidsnormerade fönster 0.50/0.15 s, per dt-stratum)
```

---

## DIMENSION 1: anloppsfart — **KORRIGERA**

### Reproduktion av deras metod (fast dt=0.051): träffar deras siffror

Med deras exakta definition (avstamp = sista grundade före första
luftburna i eventet, bakåtsökt; medel av positionshärledd fart över sista
10 grundade; dt fast 0.051) får jag lyckat p50 265.6 / p90 379.1 /
max 428.2 mot deras 271.6/388.8/443.7 (2–4 % skillnad = per-sampel-
fartdefinition, oväsentlig). **Deras pipeline är alltså korrekt
implementerad mot sin egen spec — felet sitter i specens dt-antagande.**
Botsidan verifierad likaså: traj_63G ep1 avstamp 177/anlopp 457.0 (deras
177/455.8), traj_89G ep8 avstamp 2206/430.0 (deras 2206/434.4) —
botvärdena är sunda (bot-dt 0.026 är korrekt och uniformt).

### Felet: kohorten är inte 51 ms

Uppmätt median-dt per segment (diff på trajectory_samples-t, per demo):

| seg_dt | 0.013 | 0.014 | 0.016 | 0.034 | 0.051 |
|---|---|---|---|---|---|
| gate-event | 85 | 70 | 4 | 301 | 266 |

10 av 24 demos ligger på 13–34 ms (t.ex. demo 2080/7185/22382 = 34 ms;
20171/49928 = 13 ms). Fast dt=0.051 ger då farter som är faktor
seg_dt/0.051 för låga — i 13 ms-segmenten 3.9× för låga (uppmätt
"anloppsfart" p50 118 u/s där, en absurd siffra för gapkorsningsanlopp).
De publicerade percentilerna är blandningar av korrekta 51 ms-värden och
krossade 13–34 ms-värden; p50 271.6 är en artefakt av blandningen, inte
en egenskap hos mänskligt anlopp.

**Kontroll:** enbart 51 ms-stratumet, deras egen metod: lyckat p50 360.0 /
p90 402.6 / max 428.2 — redan det motbevisar 271.6.

### Sekundärt metodfel: `_grounded` är ogiltig vid 13–16 ms

Gravitationens kurvatur d²z = 800·dt² = **0.135 u vid 13 ms < tröskeln
GROUND_D2Z 0.2** (detektorns egen docstring förutsätter 26–51 ms, där
d²z ≈ 0.54–2.08). Vid 13–16 ms klassas luftbågsapex som grundad ⇒
"grundade" anloppssampel förorenas av luftfart (bidrar till att
13 ms-stratumet mäter högst: v10 p50 449.8). 159 event (13–16 ms)
exkluderas därför ur kanoniska fartvärden.

### Tertiärt: fönstret "sista 10 grundade" är inte tidsnormerat

10 sampel = 0.51 s @51 ms, 0.34 s @34 ms, 0.13 s @13 ms, och 0.26 s för
boten @26 ms — fönstren mäter olika saker. Uppmätt fönstereffekt
(51 ms-stratumet): 0.50 s-fönster 363.1 vs 0.15 s-fönster 387.1 vs fart
vid själva avstampet 398.5 — ca 25–35 u/s systematik. Botens 0.26 s-
fönster ligger mellan.

### Friskrivningar (det som HÖLL i granskningen)

- Positionshärledd fart i sig är sund vid 51 ms: kordfelet vid aggressiv
  sväng (360°/s) är < 0.5 %; **0 teleport-/spawnspikar** (>1000 u/s)
  hittades i något anloppsfönster (726/726 event).
- Avstampsdefinitionen (bakåtsökt sista grundade) är koherent och
  reproducerbar; notera bara att den för ramla-event typiskt landar
  0.1–0.2 s IN i transiten (första luftburna kommer efter i0) och för
  14 % av lyckat-event > 0.3 s FÖRE i0 (bhop-anlopp) — acceptabelt,
  det är den faktiska sista markkontakten.

### KANONISKA humanvärden (ersätter deras; dt-korrekt fart, seg_dt ≥ 34 ms där `_grounded` är giltig)

| klass | n | mått | p10 | p50 | p90 | max | medel |
|---|---|---|---|---|---|---|---|
| lyckat | 459 | v10 (deras fönster) | 276.2 | **372.8** | **418.6** | **451.4** | 361.6 |
| lyckat | 459 | vw050 (0.50 s-fönster) | 274.0 | 369.7 | 412.3 | 472.9 | 356.3 |
| lyckat | 459 | v_avstamp | 352.0 | 415.5 | 458.3 | 572.2 | 407.6 |
| ramla | 95 | v10 | 254.6 | **362.7** | **425.4** | **487.0** | 346.9 |
| ramla | 95 | vw050 | 266.9 | 357.9 | 415.3 | 487.0 | 343.9 |
| ramla | 95 | v_avstamp | 305.0 | 395.2 | 452.6 | 518.4 | 381.8 |

Rekommenderad kanonisk definition framåt: **dt = per-segment median(diff t)
obligatoriskt; 13–16 ms-segment exkluderas ur grundnings-beroende mått;
fönster tidsnormerat 0.50 s (vw050) med v10 som sekundärspår** (bot-dt
0.026 ger 19–20 sampel i 0.50 s-fönstret — jämförbart på riktigt).

### Slutsatskorrigeringar

1. **"ramla LÅNGSAMMARE än lyckat": BEKRÄFTAD i riktning** — håller i
   varje dt-stratum separat (vw050-p50: −19.1 @51 ms, −6.5 @34 ms,
   −17.2 @13 ms) och i kanoniska värdena (362.7 vs 372.8). Magnituden är
   dock ~10–20 u/s, inte 29.
2. **"botens anlopp (413–456) ligger över human-p90 och max": FALSK.**
   Mot kanoniska värden ligger botens fem event i humana p75–max-bandet:
   human-lyckat p90 är 418.6 (v10) och max 451.4; botens enda lyckade
   (455.8, 0.23 s-fönster) är ~4 u/s över dt-giltiga v10-maxet men under
   human v_avstamp-max (572) och under 13–16 ms-stratumets (opålitliga
   men indikativa) 551.9. Människor anlöper rutinmässigt 400–470 u/s.
3. **"fartregim där människor nästan aldrig ens försöker": FALSK** —
   ~25 % av humana lyckade anlopp ligger ≥ 400 u/s (dt-giltigt).
   Bot-gapet i anloppsfart är en TOPPDECIL-fråga, inte en regimfråga;
   fas1:s dimensionsval är fortfarande vettigt men prioriteringsordningen
   bör omvärderas mot de rättade gapstorlekarna.

---

## DIMENSION 2: avstampspunkt — **KANONISERA** (med två textkorrigeringar)

Avstånden är dt-oberoende (rena positionsmått) och min oberoende
reproduktion träffar deras percentiler EXAKT:

| mått | deras | mitt |
|---|---|---|
| lyckat i0_d_edge_open p50/p90 | 15.3 / 71.5 | **15.3 / 71.5** |
| lyckat grundad_d_edge_open p50/p90 | 14.5 / 79.9 | **14.5 / 79.9** |
| lyckat i0_d_edge_side p50/p90 | 15.3 / 79.9 | 15.3 / 79.8 |
| ramla i0_d_edge_open p50/p90 | 13.1 / 21.6 | 13.1 / 21.5 |
| ramla grundad_d_edge_open p50/p90 | 13.2 / 22.1 | **13.2 / 22.1** |
| lyckat/ramla i0_d_pit p50 | 263.3 / 302.9 | 263.4 / 302.9 |

Även bot-per-event-värdena stickprovade utan avvikelse (63G ep1 sista
grundade 13.6 u etc. via samma `ledge_centers()`-uppslag). Slutsatserna
("kantlokaliseringen skiljer inte bot från human"; "humana ramla-avstamp
stramare kantbundna än lyckade, p90 21.6 vs 71.5"; rq-NV-ramlans
102.1 u-inneravstamp som största gap) är förenliga med mina mätningar
och KANONISERAS.

**Textkorrigering 1:** dimensionstexten citerar "de 1031 stödda
OPEN-maskcentrarna (ledge_centers() i rl.jump_gates)" — funktionen
returnerar **410** centra (docstringens 1031 är stale sedan
SIDE_LEDGE_MAX-filtret; percentilerna ovan ÄR beräknade på 410-setet,
så siffrorna står — bara citatet är fel). Koordinatorn bör rätta
docstringen i samband med annan rl/-ändring.

**Textkorrigering 2 (stratifieringsnot, ej sifferändring):** på
dt ≥ 34 ms-subsetet (566 event) skiftar ramla-i0-p90 21.5 → 31.1
(populationsskillnad mellan demoklasser, inte mätfel — avstånden är
dt-oberoende). Fullkohortvärdena kanoniseras, men subsetvärdet bokförs
som robusthetsnot.

**Definitionsnot (acceptabel inkonsekvens):** fas1 använder OLIKA
avstampsdefinitioner i dim 1 (bakåtsökt sista grundade) och dim 2
(i0 + sista grundade ≤ i0 i källvistelsen). Uppmätt konsekvens: fartens
avstampspunkt ger d_edge p50 15.9 / p90 84.2 (lyckat) — samma bild.
Ingen ändring krävs, men kanontexten bör nämna att definitionerna skiljer.

---

## ÖVRIGT (utanför de kritiska dimensionerna, flaggas utan fullmätning)

Dimension 3 (luftbåge-drift, u per 100 ms) har SAMMA dt-fel i
humanledet: driftrater normeras med dur = n·0.051 och luftrun-urvalet
(">= 0.10 s") använder både fast dt och `_grounded` — humanpercentilerna
där (p90 16.22 etc.) är alltså också blandartefakter och får inte
kanoniseras utan omräkning med seg-dt + 13–16 ms-exkludering.
Botvärdena (dt 0.026 uniformt) är opåverkade.

## Konfidens

**Hög** på båda huvuddomarna: dt-blandningen är direktuppmätt ur
korpusens t-kolumn (inte inferens), reproduktionen träffar deras siffror
när jag replikerar deras antagande och träffar helt andra när dt rättas;
avstampsavstånden reproducerar exakt och är dt-oberoende per
konstruktion. Artefakter: `evidence/repro/review_96G_human.json`,
`evidence/repro/review_96G_human_windows.json`.
