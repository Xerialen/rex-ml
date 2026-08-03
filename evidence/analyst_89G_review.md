# DOMSLUT: EVENT A (traj_89G ep8, "ring→quad NV ramla") — **GODKÄNT** (genuint påbörjad NV-korsning: grundad NV-ledgeanvändning följd av gaphopp som driver över axeln och slutar i gropfall — exakt den dominanta mänskliga NV-felmoden, 11/13 humana NV-ramla har samma signatur); EVENT B (probe_ledge_89G ep4, "quad→ring SO ramla") — **GODKÄNT med probvillkor** (genuin SO-ytterledgekorsning som når ringcirkeln och faller i gropen i bekräftelsefönstret; inom human qr-SO-ramla-enveloppen på alla primära mått)

## Vetogranskning av 8.9G-gate-eventen (analyst, review 11, 2026-08-03)

### Detektorstatus och repro av claims

Detektor `rl/jump_gates.py` v7.3 (d33ba28), av mig spec-verifierad och
baslinjeomlåst i `evidence/analyst_v73_baseline.md` (726 gate-event;
förutsättning för denna granskning, uppfylld). Båda claims REPRODUCERAR:

```
cd ~/rex-ml
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/traj_89G.json
  # ⇒ ring→quad NV 1/0/1/0 (nivå 1); axial 4 (2 ramla + 2 retreat); 30 ep
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ledge_89G.json
  # ⇒ quad→ring SO 1/0/1/0 (nivå 1); axial 7 (6 ramla + 1 retreat); 10 ep
PYTHONPATH=. sim/.venv-sf/bin/python evidence/repro/review_89G_events.py
  # sampel-för-sampel-rekonstruktion av bägge eventen (tabellerna nedan)
PYTHONPATH=. .venv/bin/python evidence/repro/human_89G_calib.py
  # humankalibrering: alla 726 gate-event instrumenterade (ankare, sidomassa,
  # expo, fallpunkt) -> evidence/repro/human_89G_calib.json
```

Alla claim-siffror oberoende bekräftade före dom (A: 51 sampel/1.30 s,
z −109..100, min dPit 80.1, min dQuad 385.7, 3 grundade masksampel, grop-
slut (742,−92,−109); B: 77 sampel/1.98 s, z 56..100, min dPit 54.5,
min dRing 259.0, 4 grundade masksampel, sista intervallsampel (494,−84,59)
dPit 79.1).

Regressionskontext bekräftad: traj_89G:s v7.2-NV-retreat är nu ep11
`axial ring→quad retreat` med min dPit **255.3** — dörrtröskelbandet
(208–260) ur review 10, korrekt demoterad av RETREAT_PIT_R=192.

---

## EVENT A — traj_89G ep8, transit [2228,2278] (FRI dump)

### Uppmätt banbild (bot)

1. **Källvistelse:** ringplattformen [2183,2228], 1.17 s, **7 grundade
   sampel** — källkravet genuint uppfyllt.
2. **NV-ledgefas** (2229–2243, 15 masksampel, perp +194..+199 = inre
   NV-ledgen): **grundad ledgegång 2234–2236 på z=56** (x 384–406,
   y 244–247) — 3 ankare. Sidomassa 66.2 u·s (krav 14).
3. **Gaphoppet:** avstamp vid tax≈0.39, apex z 99.8 mitt över gropen
   (2250), bågen driver över axeln (perp +199 → −264), passerar quads
   sydsida (min dQuad **385.7** luftburet vid 2271, tax 0.564) utan att nå
   plattformscirkeln.
4. **Gropfallet:** i=2278, (742,−92,−109), **fall-dPit 183.6** < 260 ⇒
   ramla (gropfall, inte ytterkantsnedhopp). Exponering 35 sampel = 0.91 s.

### Humankalibrering (24-demoskohorten, v7.3; 13 rq-NV-ramla + 208 rq-NV-lyckat)

| mått | human rq-NV ramla (13) | bot ep8 | inom? |
|---|---|---|---|
| min dPit | 6.0 – 191.6 (p50 149.2) | **80.1** | JA |
| fall-dPit | 6 – 250 (p50 192) | **183.6** | JA (vid medianen) |
| fall-tax | 0.37 – 0.68 | **0.55** | JA (mitt i) |
| fall-perp | −238 .. +38 (**11/13 negativa**) | −264.4 | 26 u bortom min |
| ankare (grundade masksampel) | 2 – 62 (min 2) | **3** | JA |
| max ankar-tax | 0.27 – 0.68 (10/13 ≤ 0.36) | **0.339** | JA (typisk) |
| sidomassa u·s | 16.1 – 787 (p50 76.9) | **66.2** | JA |
| min d(quad) | 271.9 – 443.8 | **385.7** | JA |
| transittid | 1.43 – 7.14 s | 1.30 s | 0.13 s under min |
| expo-tid | 1.12 – 6.43 s | 0.91 s | 0.21 s under min |

Nyckelfyndet: **den dominanta mänskliga NV-felmoden är exakt botens** —
ledgen ankras nära källan (10/13 humana har sista ankaret vid tax ≤ 0.36),
själva misslyckandet är gaphoppet, och fallet landar på NEGATIV perp
(11/13) sedan bågen drivit över axeln. Botens −264 ligger 26 u utanför
NV-klassens uppmätta min (−238) men väl inom gropfallens totala spann
(qr-SO-ramla når −334 i samma grop). Tids-/expo-underskridandena (0.13 s
respektive 0.21 s under ramla-minima, men ÖVER lyckat-minima 0.92/0.51 s)
är fartrelaterade (bot i högre transitfart), inte geometriska.

### Falskpositivklasserna, prövade en i taget

- **Dörrtröskel (review 9/10):** NEJ — min dPit 80.1, djupt under
  korsningsenvelopen 192; exponeringen (0.91 s) ligger i själva överfarten,
  inte vid ett återinträde.
- **Luftöverflygning (ep5/ep23-klassen, review 6/7):** NEJ — 3 grundade
  masksampel på NV-ledgeGOLVET (z=56 exakt), förankringskravet uppfyllt
  på riktigt (human ramla-min är 2).
- **Gårds-/sidogolvscirkulation (review 9):** NEJ — monoton framåtprogression
  (tax 0.24 → 0.57), aldrig i närheten av HEX-randen.
- **Axialt gaphopp med fejksida (review 5):** NEJ — 15 masksampel,
  tidsnormerad massa 66.2 u·s = 4.7× kravet, i sammanhängande inre-NV-band.

**DOMSLUT EVENT A: GODKÄNT som ring→quad NV ramla (genuint påbörjat,
misslyckat NV-korsningsförsök). Första fria NV-gateeventet — rq-NV bokförs
1 försök / 0 lyckade / 1 ramla ⇒ nivå 1.**

---

## EVENT B — probe_ledge_89G ep4, transit [1325,1401] (ledge-spawnad prob)

### Uppmätt banbild (bot)

1. **Källvistelse:** quadplattformen [1268,1325], 1.48 s, **13 grundade
   sampel**. (Proben spawnar på ledgen, men eventet börjar från en genuint
   grundad plattformsvistelse — probvillkoret gäller bokföringen, inte
   detektionens giltighet; samma förbehåll som liggarens probe60G ep5.)
2. **SO-ytterledgefas:** perp −226 → −487; masksampel 36, **grundade ankare
   4 st på ytterledgegolvet z=56** (i=1345 @tax 0.68; i=1373–1375
   @tax 0.364–0.365, perp −430..−419). Sidomassa **339.7 u·s** (24× kravet).
   Kort luftburen utflykt till perp −487 (27 u utanför masken 460) räknas
   inte i sidomassan — in-mask-samplen dominerar.
3. **Gaphoppet mot ringen:** från 1382, diagonalt över gropens sydkant —
   **min dPit 54.5** (i=1395, mitt över gropen), z fallande 99.8 → 59.
4. **Ankomst + fall:** i=1401 (494,−84,59.2) nås ringcirkeln (dRing 259.0,
   dPit 79.1) ⇒ plat=ring; i bekräftelsefönstret: inget grundat ringsampel,
   gropfall i=1416 (383,−135,−101), dPit 200.8, 0.39 s efter ankomst ⇒
   ramla enligt v7.1-landningsbekräftelsen. Expo 26 sampel = 0.68 s.

### Humankalibrering (64 qr-SO-ramla + 56 qr-SO-lyckat, samma kohortpass)

| mått | human qr-SO ramla (64) | bot ep4 | inom? |
|---|---|---|---|
| min dPit | 8.1 – 194.3 (p50 62.4) | **54.5** | JA (vid medianen) |
| fall-dPit | 8 – 255 (p50 69) | **200.8** | JA |
| fall-tax | 0.35 – 0.83 | 0.89 | 0.06 bortom max |
| ankare | 1 – 87 (min 1) | **4** | JA |
| max ankar-tax | 0.17 – 0.95 | **0.68** | JA |
| sidomassa u·s | 15.2 – 1590 (p50 450) | **339.7** | JA |
| min d(ring) | 238.9 – 443.5 | **259.0** | JA (ankomstklassen) |
| transittid | 1.17 – 7.39 s | **1.98** | JA |
| expo-tid | 0.82 – 5.66 s | 0.68 s | 0.14 s under min |

fall-tax 0.89 ligger strax bortom humana ramla-maxet 0.83 därför att boten
hann RÖRA målcirkeln före fallet — de närmaste humana (0.79–0.83) är samma
ankomst-nära-fall-klass. Expo-underskridandet (0.14 s) är fartrelaterat som
i A. Allt annat inom enveloppen, min dPit praktiskt taget PÅ medianen.

### Falskpositivklasserna

- **Review 5-klassen (axialhopp med 2 sampel fejk-SO):** NEJ — 36 masksampel,
  massa 339.7 u·s (humana misslyckade SO-korsningar: min ~15 tidsnorm.),
  sammanhängande ytterledgeväg med 4 golvankare.
- **Dörrtröskel:** NEJ — min dPit 54.5, nådd MITT ÖVER gropen i framfart,
  inte vid källkanten.
- **ep14-klassen (ogrundad källvistelse):** NEJ — 13 grundade källsampel.
- **Gårdscirkulation:** NEJ — max dPit i transiten 375 (aldrig nära 800),
  monoton måltax-progression efter vändningen vid 1351.

**DOMSLUT EVENT B: GODKÄNT som quad→ring SO ramla, MED PROBVILLKOR
(ledge-spawnad prob — bokförs som probe60G ep5 i liggaren, med
probvillkorsannotering). qr-SO kumulativt: 2 försök / 0 lyckade / 2 ramla
⇒ nivå 1.**

---

## Konsekvens för kumulativa liggaren (koordinatorns bokföring)

| gate | före | efter review 11 | nivå |
|---|---|---|---|
| ring→quad SO | 2/1/1/0 | oförändrad | 2 |
| ring→quad NV | 0 | **1/0/1/0** (traj_89G ep8, FRI) | **1** |
| quad→ring SO | 1/0/1/0 | **2/0/2/0** (+probe_ledge_89G ep4, PROB) | 1 |
| övriga | 0 | oförändrade | 0 |

min_nivå förblir 0 (qr-NV, RA-tagningen, SNG-mega utan försök).

## Validering och konfidens

- Bägge event rekonstruerade sampel-för-sampel ur detektorns egna funktioner
  (`jg._ring_quad_events`, `_on_ledge`, `_grounded`, `_side`); alla
  claim-siffror oberoende bekräftade.
- Humanenveloppen: SAMTLIGA 726 gate-event i den nyss omlåsta
  v7.3-baslinjen instrumenterade med identisk lins (fallpunkt, ankare,
  sidomassa, expo) — inte ett urval.
- Falsifieringsförsök: alla sex kända FP-klasser (review 5–10) prövade
  per event med siffror; ingen matchar. De enda måtten utanför human-
  ramla-enveloppen är tids-/expo-minima (fartrelaterade, båda ÖVER
  lyckat-minima) och fallpunktsutstickare på 26 u (A) / 0.06 tax (B) —
  inget av dem är en FP-signatur (FP-klasserna är geometriska).
- dt-förbehåll: humandata 51 ms, bot 26 ms — tidsmått jämförda i sekunder,
  massmått tidsnormerade.

Konfidens: **hög** för båda domsluten. A är dessutom kvalitativt viktig:
första beviset på fri (icke-probad) NV-sidoväg-användning — banformen
(ledgeankring nära källan + långt gaphopp) är samma strategi som humana
NV-korsare, felmoden (axeldrift) likaså.
