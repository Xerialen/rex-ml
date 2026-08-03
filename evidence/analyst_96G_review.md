# DOMSLUT: EVENT A (probe_ledge_96G ep6, "quad→ring SO ramla") — **GODKÄNT med probvillkor** (genuin SO-ytterledgekorsning med 4 golvankare och mitt-transit-vändning som slutar i gropfall; ALLA 14 uppmätta mått inom human-qr-SO-ramla-enveloppen, inkl. vändsignaturen som 4/64 humana delar); EVENT B (probe_ra_96G ep5, "ring→quad SO ramla") — **GODKÄNT med anmärkningar** (genuint tidigt-avstampat SO-gaphopp som faller i gropen halvvägs — den MODALA humana rq-SO-felformen, 14/43 humana har ≤2 ankare; två utstickare utanför enveloppen: ankar-tax 42–49 u bakom humanmin och expo 0.37 s under klassmin, båda fart-/geometrikonsekvenser, ingen FP-signatur; RA-spawnad prob men transiten funktionellt FRI — 18.8 s och ~10 zonbesök mellan spawn och försöket)

## Vetogranskning av 9.6G-gate-eventen (analyst, review 12, 2026-08-03)

Detektor `rl/jump_gates.py` v7.3 (oförändrad sedan omlåsningen
`evidence/analyst_v73_baseline.md` frånsett mega strict=True — min egen
order, påverkar inte rq/qr-gaterna). Granskningsstandard = review 11
(`evidence/analyst_89G_review.md`).

### Repro av claims

```
cd ~/rex-ml
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ledge_96G.json
  # ⇒ quad→ring SO 1/0/1/0 (nivå 1); axial 3 ramla; 10 ep
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ra_96G.json
  # ⇒ ring→quad SO 1/0/1/0 (nivå 1); axial 5 (4 ramla + 1 retreat); 10 ep
PYTHONPATH=. sim/.venv-sf/bin/python evidence/repro/review_96G_events.py
  # sampel-för-sampel-rekonstruktion av bägge eventen
PYTHONPATH=. .venv/bin/python evidence/repro/review_96G_human.py
  # humanpass: alla 726 gate-event + NYA mått (rev_tax, max|perp|, källgrundning)
  #   -> evidence/repro/review_96G_human.json (reproducerar 580/133/13 exakt)
```

Alla claim-siffror oberoende bekräftade före dom:

- **A:** [992,1086] = 95 sampel (2.47 s ≈ "2.5"), z −108.7..99.8, min dPit
  **140.6**, min d(ring) **382.7**, **4** grundade masksampel, gropfall
  i=1086 **(604,87,−109)**. ✓
- **B:** [724,768] = 45 sampel (1.17 s ≈ "1.2"), z −108.7..99.8, min dPit
  **51.7**, min d(quad) **442.3**, gropfall i=768 **(594,36,−109)**. ✓
  "3 grundade": transitspårning i0+1..i1 ger **2** grundade masksampel;
  claimets 3 inkluderar t0-samplet i=724 (grundat, på ledgemasken, perp
  −246.7) — samma t0-räknekonvention som review 10/11-skillnaden.
  Klassgränser opåverkade; bokförs som konventionsnot, inte fel.

---

## EVENT A — probe_ledge_96G ep6, transit [992,1086]

### Uppmätt banbild (bot)

1. **Källvistelse:** quadplattformen [961,992], 0.81 s, **4 grundade sampel**
   (human qr-SO-ramla-min är 1; 3/64 humana har ≤4). i0-samplet luftburet
   (z 81.5) — hoppet initierat före plattformsgränsen, som 63G ep1.
2. **SO-ytterledgefas ut:** perp −226→−540, grundat ankare i=1014 på
   ledgegolvet z=56 (perp −441, tax 0.656→prog 0.344). Luftburen utflykt
   till perp −540.3 (80 u utanför masken 460, jfr humanklassens max 573;
   9/64 humana qr-SO-ramla överskrider 460).
3. **Vändning + andra ansats:** grundade ankare i=1042–1044 (z=56, perp
   −440..−417, tax 0.352–0.355 = prog 0.645–0.648), sedan luftburen båge
   TILLBAKA mot quadhållet (raw tax 0.352→0.597, prog-regress **0.245**)...
4. **Gropfallet:** ...som viker av över gropens sydkant och slutar i
   gropen i=1086 (604,87,−109), fall-dPit **140.6** < 260 ⇒ ramla.
   fall-perp −44.3, fall-tax 0.485. Expo 42 sampel = 1.09 s.
   Masksampel 36; sidomassa 340.6 u·s (24× kravet 14).

### Humankalibrering (64 qr-SO-ramla, human_89G_calib + review_96G_human)

| mått | human qr-SO ramla (64) | bot ep6 | inom? |
|---|---|---|---|
| min dPit | 8.1 – 194.3 (p50 62.7) | **140.6** | JA |
| fall-dPit | 8.4 – 255.0 (p50 69.4) | **140.6** | JA |
| fall-tax | 0.30 – 0.83 | **0.515 (norm.)** | JA |
| fall-perp | −334.5 .. +43.5 | **−44.3** | JA |
| ankare | 1 – 87 (p50 22) | **4** | JA |
| ankar-tax (norm.) | min 0.073–0.546, max 0.166–0.950 | **0.344–0.648** | JA |
| sidomassa u·s | 15.2 – 1590 (p50 453.9) | **340.6** | JA |
| min d(ring) | 238.9 – 443.5 (p50 343.5) | **382.7** | JA |
| transittid | 1.2 – 7.4 s | **2.44 s** | JA |
| expo-tid | 0.8 – 5.7 s | **1.09 s** | JA |
| masksampel | 2 – 87 | **36** | JA |
| **rev_tax (NY)** | max 0.411; ≥0.245: **4/64** | **0.245** | JA |
| **max abs perp (NY)** | max 573; ≥540: **3/64** | **540.3** | JA |
| **källgrundning (NY)** | min 1; ≤4: 3/64 | **4** | JA |

Samtliga 14 mått inom enveloppen — inklusive de tre nya, som uppmättes
just för att pröva eventets ovanligaste drag (vändningen och
perputflykten): båda finns i humanklassen (4 resp. 3 av 64 event).

### Falskpositivklasserna, prövade en i taget

- **Dörrtröskel (review 9/10):** NEJ — min dPit 140.6 < RETREAT_PIT_R 192,
  och exponeringen ligger i själva överfarten/fallet.
- **Luftöverflygning (review 6/7):** NEJ — 4 grundade ankare på
  ledgeGOLVET z=56 exakt.
- **Fejksida/axialhopp (review 5):** NEJ — 36 masksampel, 340.6 u·s.
- **Gårdscirkulation (review 9):** NEJ — max dPit i transiten ~408 ≪ 800.
- **"Vändningen = retreat"?** NEJ — detektorsemantiken (v7.3) kräver
  återkomst till källplattformen för retreat; boten återvänder aldrig till
  quadcirkeln (max prog-regress 0.245 slutar vid tax 0.485 ÖVER gropen)
  och min dPit 140.6 < 192 gör den gropexponerad. 4/64 humana
  qr-SO-ramla har samma eller större vändsignatur.

**DOMSLUT EVENT A: GODKÄNT som quad→ring SO ramla, MED PROBVILLKOR
(ledge-spawnad probdump; eventet börjar dock från genuint grundad
quadvistelse — samma förbehåll som probe60G ep5/probe_ledge_89G ep4).
qr-SO kumulativt: 3 försök / 0 lyckade / 3 ramla.**

---

## EVENT B — probe_ra_96G ep5, transit [724,768]

### Uppmätt banbild (bot)

1. **Spawn/kontext:** RA-spawnad prob; boten spawnar "vid RA-toppen" och
   når ringen efter ~18.8 s egen förflyttning genom tele/mega/SNG/quad-
   zonerna (dumpens route-fält). Transiten är alltså funktionellt fri —
   spawnfördelen matar inte gaten.
2. **Källvistelse:** ringplattformen [677,724], 1.22 s, **6 grundade
   sampel** (human rq-SO-ramla-min 2; 17/43 humana har ≤6).
3. **Ledgeavstamp:** grundade masksampel i=724–726 på SO-ledgegolvet z=56
   strax utanför ringplattformens sydkant (perp −247..−265, tax
   −0.075..−0.066 — BAKOM källinjen, se anmärkning). Avstampsfart 433.5 u/s.
4. **Gaphoppet:** EN sammanhängande luftbåge 1.09 s (i=727..768) längs
   SO-sidan (perp −256→−297→−86), tax monotont 0→0.449 (rev_tax 0.002),
   apex z 99.8, min dPit **51.7** mitt över gropen (i=760–761, redan
   fallande), gropslut i=768 (594,36,−109), fall-dPit 89.5, fall-perp
   −86.1, fall-tax 0.447. Masksampel 17; sidomassa 124.6 u·s (8.9× kravet).
5. **Gate-kvalifikation:** via förankrat-fall-regeln (review 7):
   min d(quad) 442.3 < PROGRESS_D_BAND 450 (marginal 7.7 u, nås i själva
   gropfallet) + 2 grundade maskankare — exakt samma semantik som
   humanklassen, vars min_ddst-max är 448.7 (också falluppnådd).

### Humankalibrering (43 rq-SO-ramla)

| mått | human rq-SO ramla (43) | bot ep5 | inom? |
|---|---|---|---|
| min dPit | 7.5 – 144.8 (p50 74.9) | **51.7** | JA |
| fall-dPit | 11.4 – 234.2 (p50 132.4) | **89.5** | JA |
| fall-tax | 0.30 – 0.70 (p50 0.50) | **0.447** | JA |
| fall-perp | −335.2 .. −34.3 (p50 −143.9) | **−86.1** | JA |
| ankare | 1 – 73 (p50 4; **14/43 har ≤2**) | **2** (3 m. t0) | JA |
| sidomassa u·s | 25.6 – 1532 (p50 132.0) | **124.6** | JA (vid medianen) |
| min d(quad) | 253.9 – 448.7 (p50 421.3) | **442.3** | JA |
| masksampel | 2 – 79 (p50 9) | **17** | JA |
| rev_tax (NY) | p50 0.019 | **0.002** | JA |
| max abs perp (NY) | max 598 | **~297** | JA |
| källgrundning (NY) | min 2; ≤6: 17/43 | **6** | JA |
| **ankar-tax** | min −0.012 .. (max-led min 0.045) | **−0.075..−0.066** | **NEJ — 0.05–0.06 tax (42–49 u) bakom humanmin** |
| transittid | 1.2 – 7.8 s | 1.14 s | 0.06 s under min |
| **expo-tid** | 1.2 – 5.5 s | **0.83 s** | **0.37 s under min** |

### Anmärkningarna, prövade mot FP-klasserna

De två utstickarna är inte signaturer för någon känd FP-klass:

1. **Ankar-tax −0.075..−0.066 (helt bakom källinjen).** 9/43 humana
   rq-SO-ramla ankrar delvis vid/bakom linjen (tax < 0.05; extremast
   demo 22382 slot 1: [−0.012, 0.045]) — boten ligger 42–49 u längre bak
   på SAMMA ledgeremsa (grundat z=56, i masken, direkt utanför ringens
   sydkant). Det är en tidig avstampspunkt, inte en annan geometri:
   ingen FP-klass definieras av ankarläge bakom källinjen.
2. **Expo 0.83 s (0.37 s under klassmin).** Ren kinematik: EN båge på
   1.09 s med anloppsfart 427 u/s korsar 260-cirkeln fortare än någon
   human i klassen (humanerna gör 2+ studsar). Samma fartrelaterade
   underskridandemönster som review 11 godkände (0.14–0.21 s), här
   större eftersom hela transiten är en enda båge. Expo ligger ÖVER
   lyckat-klassernas minima — inte en tom-exponeringssignatur
   (dörrtröskel kräver min dPit ≥ 192; her 51.7).

Övriga FP-klasser: luftöverflygning NEJ (2 grundade maskankare; humanmin
1); fejksida NEJ (17 masksampel, 124.6 u·s ≈ humanmedianen);
gårdscirkulation NEJ (max dPit ~367 ≪ 800, tax monoton);
ogrundad källvistelse NEJ (6 grundade källsampel).

**DOMSLUT EVENT B: GODKÄNT som ring→quad SO ramla, MED ANMÄRKNINGAR
(ankar-tax-utstickaren och expo-underskridandet bokförs som
bevakningspunkter, inte underkännandegrund) och PROBNOTERING (RA-spawnad
probdump; transiten funktionellt fri — 18.8 s/10 zonbesök från spawn).
rq-SO kumulativt: 3 försök / 1 lyckat / 2 ramla.**

---

## Konsekvens för kumulativa liggaren (koordinatorns bokföring)

| gate | före (jump_gates_latest) | efter review 12 |
|---|---|---|
| ring→quad SO | 2/1/1/0 | **3/1/2/0** (+probe_ra_96G ep5, PROB/funktionellt fri) |
| quad→ring SO | 2/0/2/0 | **3/0/3/0** (+probe_ledge_96G ep6, PROB) |
| ring→quad NV | 1/0/1/0 | oförändrad |
| övriga | 0 | oförändrade |

Exakt uppdragets siffror: qr-SO 3/0/3, rq-SO 3/1/2.

## Bevakningspunkter (nya)

1. **Bot-ankring bakom källinjen (B):** om fler rq-SO-event ankrar vid
   tax < −0.05 utan att någonsin ankra framför linjen — överväg
   ankar-tax-golv i detektorn (humanbandet börjar vid −0.012).
2. **En-båge-transiter:** botens expo-tider kryper under humanminima i takt
   med farten; expo är inte längre diskriminativ mot human-enveloppen för
   godkännande, bara mot tom-exponerings-FP.
3. **Vändsignaturen (A):** rev_tax 0.245 är human (4/64) men värdet bör
   följas — rena fram-och-tillbaka-oscillationer över gropen (rev_tax ≥
   0.5, human max 0.411 i qr-SO) vore en ny FP-kandidat.

## Validering och konfidens

- Bägge event rekonstruerade sampel-för-sampel ur detektorns egna
  funktioner; alla claim-siffror bekräftade (enda avvikelsen: B:s
  "3 grundade" är t0-inklusiv räkning, transiten har 2).
- Humanenveloppen: samtliga 726 baslinjeevent ominstrumenterade i
  review_96G_human.py (som dessutom reproducerar 580/133/13 exakt);
  de tre NYA måtten (rev_tax, max|perp|, källgrundning) mätta på hela
  populationen, inte urval.
- Falsifiering: alla kända FP-klasser prövade per event med siffror;
  B:s två utstickare granskade separat och befunna fartkonsekvenser
  utan FP-koppling.

Konfidens: **hög** för A (allt inom enveloppen). **Hög** för B på
gate-/utfallsklassningen, **medel** på att B:s banform är "samma
manöver som humanerna" — den är klassens modala form (tidigt hopp,
kort ankring, gropfall halvvägs) men exekverad från en aning längre
bak och klart fortare än någon uppmätt human.
