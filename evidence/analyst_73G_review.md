# DOMSLUT: EVENT A (traj_73G ep20, "RA-tagningen försök") — UNDERKÄNT (trappspring/korridorpassage över mellanavsatsen z=104, utanför hela 619-eventsenveloppen av mänskliga RA-försök); EVENT B (probe_ledge_73G ep8, "ring→quad NV retreat") — UNDERKÄNT (review 9-klassen i ny skepnad: gårdscirkulationsloop vars ENDA gropexponering är 0,10 s dörrtröskelklipp vid återinträdet på ringplattformen)

## Vetogranskning av 7.3G-gate-eventen (analyst, review 10, 2026-08-03)

### Detektorstatus och repro av claims

Detektor `rl/jump_gates.py` @ HEAD (3fe4955). Diff mot v7.2-låsningen (5e08e3f)
egenverifierad: `git diff 5e08e3f..HEAD -- rl/jump_gates.py` — endast
`_item_events`-eventlista (i0/i1) + klipputskrift; räknelogiken orörd.
Regression: `traj_66G` ⇒ axial 4 ramla (= låst baslinje).

Båda claims REPRODUCERAR exakt:

```
cd ~/rex-ml
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/traj_73G.json
  # ⇒ RA-tagningen 1/0 (nivå 1); axial 8 ramla; 30 ep
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ledge_73G.json
  # ⇒ ring→quad NV 1/0/0/1 (nivå 1); axial 5 (4 ramla + 1 retreat); 10 ep
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ra_73G.json
  # ⇒ gates 0; axial 3 (2 ramla + 1 retreat); 10 ep
```

Underkännandena gäller som i review 9 SEMANTIKEN (ägarens nivå 1-ord:
"uppvisad medvetenhet om hoppet/tagningen som mål"), prövad mot humandata
genom exakt samma detektorlins. Instrumenteringen anropar detektorns EGNA
funktioner (`jg._item_events`, `jg._ring_quad_events`) — ingen spegling,
inga assert-behov.

Repro (allt nedan):

```
cd ~/rex-ml
PYTHONPATH=. sim/.venv-sf/bin/python evidence/repro/review_73G_events.py
  # bot-eventens fulla rekonstruktion (bägge event, bana + efterspel)
PYTHONPATH=. .venv/bin/python evidence/repro/human_73G_calib.py
  # humankalibrering, 24-demoskohorten (227 segment, dt 0.051):
  # 619 RA-försök + 22 gate-retreats + 318 NV-referens
  # -> evidence/repro/human_73G_calib.json
```

---

## EVENT A — traj_73G ep20, RA-intervall [1923,2055]

### Uppmätt (bot)

Claimets siffror bekräftade: entré z=−0,7; 1 samtidighetssampel (i=2023,
pos (257,−588,104), d2=116,4 = 3,6 u innanför APPROACH_MIN 120); max grundad
z=104,0=entré+104,7; min d2=96,5; pickupbox ej nådd. Därutöver uppmätt:

- **Max z i HELA intervallet = 104,0.** Boten är aldrig — grundad eller
  luftburen — över entré+104,7. RA ligger på +304,7 över entrén.
- **Grundade nivåer:** −16 (golv), 24/32/40 (trappsteg), 104 (mellanavsatsen
  norr om RA; 5 sampel = 0,13 s, i 2019–2023). 32/133 sampel grundade.
- **min d2=96,5 nås LUFTBURET i NEDFART** (i≈2027–2031, z 101→90 fallande):
  2D-närmandet sker när boten dyker AV avsatsen förbi RA:s bas, inte i
  klättring mot den.
- **v2d 350–500 u/s genom hela intervallet** — ingen inbromsning, ingen
  positionering, inget uppåthopp från avsatsen. Intervalltid 3,46 s.
- Efterspel: lämnar 300-radien västerut (mot tele/SNG-hållet) och
  cirkulerar tillbaka på golvet z=−16.

Banbild: golvet → trappan (+24..+40) → luftburen cirkulationsbåge längs
östväggen (z 60–104) → 0,13 s på 104-avsatsen → dyker av → golvet → ut.
Detta är korridortrafik över mellanavsatsen — exakt den klass som
v1-korrigeringen fällde 95/96 av (tele↔RA-nedre-passager); den passerar nu
för att avsatsens sydläpp råkar klippa d2<120 med 3,6 u under ett (1) sampel.

### Humankalibrering (24-demoskohorten, dt 0.051; 619 RA-försök genom
detektorlinsen: 371 lyckade / 248 missade; `human_73G_calib.json`)

| mått | lyckade (371) | missade (248) | bot ep20 |
|---|---|---|---|
| n_simult p25/p50/p95 | 10 / 26 / 295 | 6 / 10 / 35 | **1** |
| samtidighetsdwell p50 | 1,33 s | 0,51 s | **0,026 s** |
| max grundad dz p5/p25/p50 | 231 / 272 / 300 | 208 / 272 / 272 | **104,7** |
| max dz (inkl. luft) p5/p50 | 284 / 299+ | 208 / 272 | **104,7** |
| intervalltid min / p5 | 6,0 / — | 4,03 / 4,6 | **3,46 s** |

- 612/619 försök når abs grundad z ≥ 200 (platånivåerna 208–328 under/vid RA).
- **n_simult ≤ 2 förekommer (22/619 = 3,6 %) men UTESLUTANDE hos
  toppklättrare:** samtliga 22 har max grundad dz ≥ 152 (deras enda/få
  samtidighetssampel ligger uppe vid RA-hyllan).
- **max grundad dz < 150 förekommer (4/619 = 0,6 %) men UTESLUTANDE med
  dwell:** n_simult 3–5 (≥ 0,15 s), intervalltider 6–17,5 s (uppehåll på
  mellanavsatsen under RA, min_d2 48–114).
- **Snittmängden (dwell < 0,15 s ∧ max grundad dz < 150): 0/619.**
  Boten (0,026 s ∧ 104,7) ligger i den tomma regionen — utanför HELA
  humanenveloppen, dessutom under humana intervalltidsminimum (3,46 < 4,03 s).

### Svar på frågorna

1. **Genuin klättringsansats i människomening? NEJ.** Människors
   nerifrån-försök (även misslyckade) klättrar till platånivåerna 208–328
   eller uppehåller sig på mellanavsatsen; boten sprintar rutten till
   +104-avsatsen i full korridorfart och dyker av den, med 2D-närmandet i
   nedfarten. (Obs: "platåer på entré+104..+136" i review 4 avsåg
   SNG-MEGA-trappan; RA:s humana klättring går till +208..+328.)
2. **Räcker 1 samtidighetssampel?** Ensamt: NEJ. Hos människor är
   1-sampelsförsök alltid toppklättrare (max grundad ≥ entré+152); ett
   ensamt 26 ms-klipp på första avsatsen har ingen mänsklig motsvarighet.

### Detektorändringskrav A (ej implementerat av mig)

`_item_events`-försök ska utöver dagens villkor kräva:
**samtidighetsdwell ≥ 0,15 s (dt-normerat: ≥3 sampel @51 ms, ≥6 @26 ms)
ELLER max grundad z ≥ entré+130.**

- Humanretention (RA): **619/619 = 100 %** per konstruktion (snittmängden tom).
- Marginaler: höjdgrenen 22 u till närmaste human (152) och 25,3 u till
  boten (104,7); dwellgrenen fäller boten 6× (1 av 6 sampel).
- **Förbehåll:** kalibrerat på RA. SNG-mega (platåer entré+104..136 —
  somliga UNDER 130-gränsen) måste återvalideras mot de mänskliga
  mega-positiva innan driftsättning, analogt med review 4-proceduren
  (mega-människor står på platån ⇒ förväntas passera via dwellgrenen,
  men det ska MÄTAS, inte antas).

**DOMSLUT EVENT A: UNDERKÄNT. RA-tagningen ska stå kvar på 0 försök;
nivå 1 bokförs inte.**

---

## EVENT B — probe_ledge_73G ep8, transit [379,526]

### Uppmätt (bot)

Claimets siffror bekräftade: 148 sampel / 3,85 s; z 56..99,8; min dPit=256,0;
min dQuad=425,2; start (321,208,74) slut (412,159,97). Därutöver uppmätt:

- **Loopbana:** ring → NV-ledgen (tax max 0,60 nås redan t=0,94 s) →
  NV-gården perp 646, **dPit max 799,6 = 0,4 u från HEX_R 800** (hade
  blivit "lämnade") → grundad gårdsvandring på z=56 → returbåge → ring.
  Samma cirkulationsklass som review 9:s ep8 @6.6G (den gick till dPit 797).
- **Utvägens min dPit = 302,1 — utvägen är ALDRIG exponerad.** All
  exponering (exakt 4 sampel = 0,10 s, i 523–526) ligger i returens sista
  0,10 s, och **sampel i=526 ÄR retreat-samplet** (plat=ring, dRing 256,5).
  dRing över de exponerade: 293,7→256,5 — boten är på väg IN i
  ringplattformen. Radialhastighet mot gropen vid min: +2 u/s (tangentiell).
  min dPit nås 2,9 s EFTER vändpunkten (max tax).
- **Dörrtröskelgeometrin:** ring-center→gropcenter = 324,4; PLAT_R 260 ⇒
  exponeringscirkeln (260) når 64 u från plattformskanten. Varje
  återinträde längs axelsidan klipper dPit<260 strax före landning —
  exponeringskravet kan uppfyllas VAKUÖST utan gropengagemang.
- min dQuad 425,2 (i=404, t=0,65 s, på väg UT förbi quad-sidan): 24,8 u
  innanför 450-bandet — samma nära-gränsen-karaktär som review 9 (430/400).

### Humankalibrering (samma kohort; alla 22 v7.2-retreats + 318 NV-korsningar
som exponeringsreferens; `human_73G_calib.json`)

De 22 behållna retreaterna faller i TVÅ uppmätta klasser:

| klass | n | min dPit | expo-tid | max run | d(källa) vid min | tax vid min |
|---|---|---|---|---|---|---|
| **genuin** (7 SO + 5 q→r NV + 1 r→q NV) | 13 | 15,1–169,3 | 0,46–3,11 s | 7–31 | 259,9–599,8 | 0,285–0,694 |
| **dörrtröskel** (alla r→q NV) | 9 | 208,0–250,4 | 0,15–1,94 s | 3–17 | 242–277 | 0,30–0,34 |
| **bot ep8** | 1 | **256,0** | **0,10 s** | 4 | **268,7** | 0,35 |

Referens NV-korsningar: lyckade (292) expo-tid p5 0,66 s, ramla (26) p5
0,78 s — genuina överfarter är alltid substantiellt exponerade.

- **Gapet 169,3→208,0 (38,7 u) är TOMT** i humandatan: ingen genuin
  avbruten korsning över 169,3, ingen dörrtröskelretreat under 208,0.
- Dörrtröskelklassens signatur = botens: min dPit vid källplattformens
  kant (d_src 242–277), tax 0,30–0,34 (korridormynningen vid ringen).
  Review 9 flaggade redan klassen som vandringsklass ("ofarlig i
  humanbaslinjen"); v7.2-tröskeln 260 behöll den enbart för att ingen ny
  parameter skulle införas.

### Svar på frågorna

1. **Är 256,0 förenligt med genuin gropexponering? NEJ.** 64 u utanför
   korsningsenveloppen (alla 318 genuina NV-överfarter ≤ 192, review 9),
   86,7 u utanför genuina retreatklassens max (169,3), och 5,6 u bortom
   t.o.m. dörrtröskelklassens max (250,4). Exponeringen nås på återvägen,
   vid ringens kant, med radialhastighet ≈ 0 mot gropen.
2. **Krav på flera konsekutiva exponerade sampel? SEPARERAR INTE** —
   uppmätt: genuina max_run 7–31 vs dörrtröskel 3–17 (överlapp; t.ex.
   46585/1: 38 exponerade sampel / 1,94 s vid tröskeln). Duration
   separerar inte heller (0,46–3,11 vs 0,15–1,94). Det som separerar är
   GEOMETRIN, inte varaktigheten.

### Detektorändringskrav B (ej implementerat av mig)

**Skärp retreat-kvalifikationen från min dPit < 260 till min dPit < 192**
(= den redan uppmätta korsningsenveloppen ur review 9 — ingen ny konstant,
en befintlig uppmätt storhet; PIT_EXPOSURE_R 260 för ramla-semantiken
berörs inte).

- Fäller alla 9 dörrtröskelevent (marginal 16 u ned till 208,0), behåller
  13/13 genuina (marginal 22,7 u upp från 169,3), fäller boten med 64 u.
- Baslinjekonsekvens vid antagande: gate-event 735 → **726**
  (580/133/13); ring→quad NV 208/13/**1** (222 försök, 94 %). De 9 fällda
  förväntas bli axial-retreat (rå-progression fanns i alla 15 fällda i
  v7.2-omlåsningen; ska verifieras). **Omlåsning av humanbaslinjen krävs
  innan nästa botclaim bedöms** — samma procedur som v7.1→v7.2.

**DOMSLUT EVENT B: UNDERKÄNT. Nivå 1 för ring→quad NV bokförs inte;
kumulativa stegen lämnas oförändrad.**

---

## Informationsspår: varför RA-proben ger 0 RA-event trots "8/10 slutar vid RA-toppen"

Uppmätt (`probe_ra_73G.json`, alla 10 episoder): **"vid RA-toppen" är
SPAWN-zonsetiketten** (8/10 spawnar med den etiketten — men på
RA-NEDRE-golvet, spawnpositioner z −16..56; zonuppslaget är 2D/kolumnbaserat
och RA-topp-zonen täcker kolumnen). **Ingen episod slutar uppe:** slutpositioner
z −194..+28 (RA-nedre-golvet respektive gropen), min dRA vid slut 116 med
z=−16. Detektorn ser 4–6 låg-entré-intervall per episod (entré-z −16..56,
low_pred passerar) men `climbed_near` håller aldrig — boten cirkulerar på
golvet och har inget grundat sampel ≥ entré+80 inom d2<120. **0 försök är
korrekt mätning, ingen detektorlucka.** (Repro: se utskriften i
`review_73G_events.py`-körningen ovan eller engångsraden i granskningsloggen.)

---

## Validering och konfidens

- Bägge bot-event rekonstruerade sample-för-sample ur detektorns egna
  eventintervall; alla claim-siffror oberoende bekräftade före domen.
- Humanenveloppen: 619 RA-försök resp. 22+318 transitevents genom EXAKT
  samma detektorfunktioner, samma kohort som den låsta v7.2-baslinjen
  (227 segment).
- Falsifieringsförsök: för A söktes mänskliga motsvarigheter till botens
  signatur (1-sampelsförsök, lågklättrare) — bägge finns var för sig men
  snittmängden är tom (0/619); för B prövades varaktighets- och
  konsekutivkrav som alternativ till geometrisk skärpning — de överlappar
  och förkastas med siffror.
- dt-förbehåll: humandata 51 ms, bot 26 ms — alla dwell-/varaktighetsmått
  tidsnormerade, aldrig råa sampelantal.

Konfidens: **hög** för båda domsluten (dubbel evidens: botbanornas rådata +
fullständiga humanfördelningar; tomma separationsgap 38,7 u (B) respektive
tom snittmängd 0/619 (A)).
