# Review: vertikala belöningstrappan (V1–V3) mot mänskliga korpusen
*DM3-analytikern, 2026-08-01. Beställd som granskning av gate2_v2:s beslutade
reward-trappa (PROGRESS.md 2026-08-01 02:50) mot mänskligt 4on4-spel.*

## Fråga och omfattning
Granska tre målförflyttningar (RA-botten→RA-toppen, SNG→mega, highbridge→RL-boxen
via fönstret) i mänskligt spel utan raket, testa V2-trösklarna (span>240 u,
golvdjup>96 u) mot uppmätta mänskliga hopp, jämföra zonfördelning människa/bot
för V1-viktningen, och kvantifiera fartkostnaden för vertikal rörelse (500-UPS-risken).

## Kohort och metod (reproducerbart)
- Store: `~/dm3-extract/store-dm3/trajectory_samples`, filter `format='mvd' AND
  mode='4on4' AND map='dm3'` = 826,4 M sampel. Spelarfilter: `(demo_key,slot)` med
  `team_id IS NOT NULL` i `players`-tabellen (tar bort spectators/trackers — utan
  detta dyker falska 0,14 s-"klättringar" med slot 17 upp i svansarna).
- `h` = BSP-höjd-över-golv, finns på 65,5 % av sampel; `h<=2` = markkontakt
  (kalibrerat: RA-toppens campare p50 h=0,000). Luftsegment = sammanhängande h>2
  mellan två markkontakter; span = horisontell TA→landning; golvdjup ≈ max(h) i
  segmentet; avfyrningsfart = centraldiff-hspeed (3-sampel-median) vid TA-sampeln.
- Transit: sista A-boxsampel → första B-boxsampel (B-entré = >1,5 s utanför B),
  förkastad vid positionswarp >250 u/steg eller dt-hål >400 ms. Boxar:
  - T1 A=RA-låg x[-250,150] y[-880,-520] z[-64,40]; B=ratop x[-224,320]
    y[-736,-512] z[288,360]; max 25 s. 63 599 transiter i korpusen, 6 000 samplade,
    3 115 giltiga (1 609 demos).
  - T2 A=SNG-rummet x[-780,-400] y[300,700] z[-64,170]; B=mega-hyllan x[-864,-672]
    y[32,160] z[118,210]; max 8 s. 57 559 transiter, 5 868 giltiga (1 970 demos).
  - T3 fönsterboxen x[1300,1450] y[540,655] z[15,130]: 125 292 besök, 7 996
    analyserade (1 968 demos).
- Zonfördelning: exakt replikering av `rl/spatial_report.py`:s ZoneNamer
  (familjekollaps + närmsta centroid, 0,3-viktad z, VATTNET ur voxelklass 1)
  applicerad på `pipeline/out/gate2/voxel_classes.npz` per-voxel-trafik
  (898,9 M sampel) — direkt jämförbar med `evidence/spatial_report_latest.json`.
- Korsvalidering: referensdemo-hoppen i `evidence/manoeuvres_by_route.json`,
  ruttider i `evidence/route_graph.json`, fartkorridorer i
  `evidence/human_sustained_speed_dm3.md`.

## Fynd 1: RA-botten→RA-toppen — långsam trapp-serie, inte gap-hopp
Observerat (n=3 115 giltiga klättringar):
| mått | p25 | p50 | p75 | p90 | p99 |
|---|---|---|---|---|---|
| total tid (s) | 5,0 | **5,4** | 6,2 | 8,6 | 20,9 |
| höjdvinst (u) | 273 | 280 | 280 | 280 | 312 |
| **höjdvinst/s (u/s)** | 45,3 | **51,1** | 56,0 | 62,1 | 113,6 |
| max z-vinst i 1 s-fönster (u) | 129 | 137,5 | 140 | 155 | 238 |
| medel-hspeed under klättring (UPS) | 357 | **382** | 400 | 413 | 433 |

Teknik: serie GRUNDA upp-hopp — per hopp (n=201 med rise>20): rise p50 **32,8 u**,
span p50 219 u (p75 309, max 564), avfyrning p50 442 UPS, golvdjup under hoppet
p50 **43,8 u** (p75 99,6). Svansen (höjdvinst/s p99 113,6; 1 s-vinst p99 238 u;
snabbaste giltiga klättring 1,52 s, demo `cf943cdff496974e…a4ed0` slot 1
t=398,8–400,3 s, vmean 471) är raketassisterad — utan raket är ~50 u/s och ~5,4 s
den mänskliga normen för 280 u.

V2-test: 39 % av klätterhoppen har span>240 MEN golvdjup p50 43,8 → djupkravet 96
fäller majoriteten. Av ALLA luftsegment i RA-korridoren (n=18 881) passerar 14,2 %
span>240 men bara 5,6 % span>240∧djup>141. **V2 träffar inte RA-klättringen;
den ska bäras av V1:s klätterbonus.** Kalibrering för V1: belöna landning med
rise ≥ 24 u (mänskligt klätterhopp rise p50 32,8, min 22,4) — inte tid i stigning.

## Fynd 2: SNG→mega-hoppet — span ~180 u, djup ~244 u: V2 missar 95 % av det
Observerat (n=2 621 luftsegment med landning i mega-hörnet; transit-nivå n=5 868):
- Span: p10 143, p25 167, **p50 182**, p90 218, p99 295, max 332 u.
- Avfyrningsfart: p10 354, **p50 412,5**, p90 453, p99 487 UPS.
- Rise ≈ 0 (p50 0,0 — hoppet går plant från sydhyllan z≈200, klustret
  (-800±50, 300±50) står för 59 % av avstampen), lufttid p50 0,7 s.
- **Golvdjup under flykten: p50 243,7 u** — ett äkta gap-hopp över SNG-rummets golv.
- Transit: total tid p50 2,1 s, medel-hspeed p50 309 UPS. Exempel:
  demo `7aa6e48960f7a8be…2d91e1` slot 3 t=719,7–720,9 s (1,25 s, 395 UPS).

V2-test: **span>240 passeras av 4,5 %** (118/2 621; alla 118 klarar också djup>141).
Det kanoniska mänskliga mega-hoppet (180 u) är alltså osynligt för V2 som det är
specat. Djupkravet 96 är däremot väl kalibrerat här (243,7 >> 96).

## Fynd 3: fönstret är en stridsposition, inte en transitrutt — och inflygningen
är under båda V2-trösklarna
Observerat (7 996 fönsterbesök): ankomstlägen **91 % lokalt tassande** (strid/
positionering), 4,8 % kontinuerligt västerifrån (quad-golvet), 3,2 % söderifrån
(bro-sidan), 1,0 % YA-tele. Fart i fönsterboxen p50 **264 UPS** (p90 360).
- Fönsterinflygningen (luftsegment med landning i fönsterboxen, n=24 över två
  extraktioner + 5 referenshopp i `manoeuvres_by_route.json` window_to_rl):
  span p50 150–191, **max 250** (referenshoppens max gap 238,8); avfyrning
  p50 297–452, max 686 UPS; **golvdjup 13–128 u, p50 48–64** — ALDRIG >141.
  → **0 av 29 uppmätta fönsterflygningar passerar span>240∧djup>96.**
- Nedsläppet till RL-boxen: fönster (z 44) → RL-golvet (z −88..−152), dz p50 −158
  (n=62 direkta fönster→RL-box-transiter). Mänsklig medeltid fönster→RL-item
  4,83 s (n=11 193, route_graph) mot **bron→RL 2,48 s** (route-lab-referens,
  start [1359,−348,−24]) — människor når RL-boxen snabbast via bron/östra
  ledgen, INTE genom fönstret. Fartkorridoren RL↔window (71–75 % av >450-trafiken,
  human_sustained-rapporten) går längs korridoren — fönsteröppningen själv är
  långsam (zon-p50 196, tak 381 i gate2_zones).

## Fynd 4: zonfördelning — botens täckningsunderskott är främst HORISONTELLT
Samma ZoneNamer som botens spatialrapport; människa = 898,9 M korpussampel,
bot = gate2_v2 (10 ep):

| zon | människa % | bot % | bot/människa |
|---|---|---|---|
| vid mega (hill/sng/pent-familjen) | **15,3** | 3,6 | 0,23 |
| vid RA-toppen | 14,5 | 13,4 | 0,92 |
| vid quad | **10,2** | 3,3 | 0,32 |
| VATTNET (exkl. ur gaten) | 10,0 | 4,0 | 0,40 |
| vid YA/SSG | 9,3 | 5,2 | 0,56 |
| vid RL | 8,8 | 9,8 | 1,11 |
| vid YA | **8,1** | 1,3 | **0,16** |
| vid ringen | 6,4 | 3,4 | 0,53 |
| vid SNG | 5,1 | 10,0 | 1,96 |
| vid tele | 3,8 | 3,7 | 0,97 |
| vid RA-nedre/NG-tunneln | 3,2 | 3,0 | 0,93 |
| vid window | 2,7 | **25,1** | **9,37** |
| vid pent | 2,5 | **14,1** | **5,55** |

V1-zonsällsynthetsviktningen ska bita först i: **YA-gården (0,16×), mega/hill-
gården (0,23×), quad-övre (0,32×), ringen (0,53×), YA/SSG (0,56×)** — och trycka
NED window (9,4×) och pent (5,6×). OBS: dessa underbesökta zoner är till största
delen LÅGA öppna gårdar (YA-gården, hill/mega-gården), inte höga platser —
**z-nivå-komponenten i V1 siktar delvis fel axel; zonsällsynthetskomponenten
måste bära täckningsarbetet.** Goda nyheter: gårdarna är människornas snabbaste
ytor (hill/mega-gården 21,8 % och YA-gården 13,2 % av alla >500-tickar) —
täckning där HOTAR INTE fartkriteriet.

## Fynd 5 (risk): vertikala passager kostar 230–350 UPS mot sim-baslinjen — mätbart men hanterbart
- Uppmätt mänsklig fart under målförflyttningarna: RA-klättring **382** (p50),
  SNG→mega **309**, fönsterpassage **264** UPS. Trafikviktad voxel-p50: RA-hallen
  335 (p95 435), SNG→mega-korridoren 330 (436), bron 341 (499), RL-boxen+gården
  **204** (369, långsammaste målytan; boten är redan där 9,8 % @ 393).
- Kostnadsräkning mot gate2_v2:s open-mean 616: en RA-klättring à 5,4 s drar
  (616−382)·5,4/60 ≈ **−21 UPS** på ett 60 s-episodsnitt; SNG→mega ≈ −11;
  fönsterpassage ≈ −12. Marginalen 616→500 (116 UPS) tål ~5 vertikala passager/min;
  vid ~10/min är snittet nere vid ~470–520 — **kriteriet hotas först om täckningen
  tvingar tät repetition av klättring**. Motmedel (stöds av data): klätterbonus per
  VUNNEN höjd (u), inte per tid i klättring, så snabb klättring dominerar.
- V3-stöd: människornas enda snabba vertikal är raketen (höjdvinst/s p99 113,6;
  1 s-vinst p99 238 u; 1,5–2 s-klättringar finns bara i raketsvansen). Utan raket
  är RA-klättringen strukturellt ~50 u/s. **Rjump-stödet (V3) är det som gör
  "vertikal + fart" förenliga, precis som trappan antar.**

## Kalibrerade V2-trösklar (förslag med siffror)
Nuvarande (span>240 ∧ djup>96) belönar: 4,5 % av mega-hoppen, 0 % av
fönsterflygningarna, och i RA-korridoren mest icke-klättringssegment. Kalibrering:
- Fysikgräns för djupkravet: ett platt bunnyhopp når max(h) ≈ 43,8 u (hopp-apex
  45 u; T2-luftsegmentens hmax p90). **Djup>56 u** utesluter alla platta hopp med
  marginal (96 gör det också, men fäller fönstret).
- **Förslag: span>150 ∧ golvdjup>56, bonus skalad med span·(1+djup/100).**
  Träffar då: mega-hoppet ~90 % (span p10 143, djup 244), fönsterflygningen
  ~50–60 % (span p50 150–191, djup p50 48–64 — medvetet marginellt; höj till
  djup>40 om fönstret ska fångas fullt), RA-klätterhoppen faller fortfarande
  (djup p50 43,8 — korrekt: de ska belönas av V1:s rise-bonus, inte gap-bonus).
- Behåll gärna en extra nivå för äkta djupgap (djup>141): där ligger mega-hoppet
  (100 %) och inget av de platta — användbar som förstärkt bonus utan falska träffar.

## Validering och felkällor
- Spectator-kontaminering upptäckt (slot 17, 0,14 s-"klättringar") och eliminerad
  med players-join; percentilerna ändrades <1 % — svansarna var det enda drabbade.
- Först användes felfiltret `team_id IN ('red','blue')` (–80 % kohort);
  korrigerat till `IS NOT NULL` — resultaten stabila inom ~5 % mellan körningarna
  (mega-span p50 182 oförändrad; fönster-span konsistent 150–191).
- h-fragmentering ger låg recall på luftsegment (t.ex. 23 strikta vs 2 621 breda
  mega-landningar) men geometrin är konsistent över båda urvalen och mot
  referensdemos — Hög konfidens på geometri, Medium på exakta andelar.
- MVD-samplingen (29–72 Hz) slätar avfyrningsfarter något (medianfilter);
  systematiskt åt det låga hållet, ~±10 UPS.
- Fönsterinflygningens n=24+5 är litet (Medium); allt annat n≥200 (Hög).
- Rate-svansen (p99) innehåller raketassist — medvetet redovisad separat;
  V3-slutsatsen bygger på den, V1/V2-kalibreringen på p25–p90.

## Slutsats
1. (Hög) **V2:s span>240 är felkalibrerad mot alla tre målen**: mega-hoppet p50
   182/max 332 (4,5 % över 240), fönsterflygningen max 250 med djup ≤128 (0 %
   klarar båda kraven), RA-klättringen är grunda 33 u-hopp som V2 inte ska fånga.
   Sänk till span>150 ∧ djup>56 (djup>141 som förstärkningsnivå).
2. (Hög) **RA-klättringens mänskliga norm är 51 u/s och 5,4 s @ 382 UPS** —
   belöna vunnen höjd per landning (rise ≥ 24 u), inte tid.
3. (Hög) **Botens täckningsunderskott är främst låga öppna gårdar** (YA 0,16×,
   mega/hill 0,23×, quad 0,32×), inte höga platser — zonsällsynthet ska bära V1,
   z-nivå-vikten är sekundär; och gårdarna är mänskliga fartytor, så täckning där
   är förenlig med 500-kravet.
4. (Medium) **Fartkostnaden för vertikalt är −11..−21 UPS per passage** på
   60 s-snittet — hanterbart till ~5 passager/min, farligt vid tät repetition.
5. (Hög) **Människans snabba vertikal är raketen** — V3 är rätt slutsteg; utan
   den finns ingen mänsklig evidens för snabb RA-klättring.
