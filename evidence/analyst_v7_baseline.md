# BASLINJE OMKALIBRERAD OCH LÅST för detektor v7 (ägardefinitionen): 610 gate-event = 392 lyckat (194 NV / 198 SO) + 181 ramla (51 NV / 130 SO) + 37 retreat; 0 grazers; 0 oförankrade ramla; probe-ep5 KORREKT gate-ramla under ägardefinitionen — MED TVÅ VARNINGAR: (1) landningsbekräftelsen är dt-miskalibrerad för 51 ms-humandata och fäller 194 av 584 äkta v6.1-lyckade (33 %), (2) 26 gate-ramla är ytterkantsfall som aldrig exponerats för gropen

## v7-omkalibrering av humanbaslinjen

Analyst, 2026-08-02, efter ägarbeslutet ~18:30 (BRIEF-amendment: gaten =
plattform→plattform PÅ ANGIVEN SIDA utan att ramla i gropen; sidovägen
omfattar hela sidogolvet inkl. ytterkanten). Detektor: `rl/jump_gates.py` v7
(mask 300→460, landningsbekräftelse ≤27 sampel; oförändrad av mig; 40/40 test).
Repro: `evidence/repro/human_ledge_v7_baseline.py` (+.json) — dubbelspårning
v6.1↔v7 i samma transitloop, 227 assert-verifierade segment mot detektorn,
24-demoskohorten (`human_ledge_baseline.json`-nycklarna), dt 0.051.

## Botdumpsverifiering (v7, omkörd av mig)

| dump | v7-utfall |
|---|---|
| traj_63G | ring→quad SO **2/1/1** ⇒ nivå 2 (ep1 lyckat + ep4 ramla); axial 2/0/2 (ep8-"lyckat" nu korrekt ramla via landningsbekräftelsen) |
| probe_ledge_60G | quad→ring SO 1/0/1; axial 1 |
| traj_53G | sidogates 0; axial 3 |
| traj_0907 | 0; axial 0 |

**Probe-ep5-bedömning (beställd):** KORREKT gate-ramla under ägardefinitionen.
Transiten (sampel 16–92) har äkta grundad sidogolvsvistelse: z=56-golv vid
perp −424…−459, dPit 277–350 (7 MASK+GND-sampel 45–51) — under ägarens
"hela sidogolvet"-semantik är det förankring på sidovägen, inte artefakt.
Fallet sker via ett inåtriktat hopp från ytterkanten in över gropens luftrum
(dPit min 44.7, luftburet) ner i gropen. Min v5/v6-underkännande byggde på att
dess enda IN-BANDS-sampel var luftburna över gropen — det kriteriet är ersatt
av ägarbeslutet; grundkravet (förankring) uppfylls nu av golv som ägaren
förklarat giltigt. Ingen invändning.

## NY LÅST REGRESSIONSBASLINJE (v7, 24-demoskohorten, dt 0.051)

**1614 event totalt, varav 610 gate-event:**

| gate | lyckat | ramla | retreat |
|---|---|---|---|
| ring→quad NV | 139 | 19 | 25 |
| ring→quad SO | 157 | 50 | 5 |
| quad→ring NV | 55 | 32 | 5 |
| quad→ring SO | 41 | 80 | 2 |
| **totalt** | **392** (194 NV / 198 SO) | **181** (51 NV / 130 SO) | **37** (30 NV / 7 SO) |

Kontroller: **0 grazers** (massa<14 u·s), **0 oförankrade gate-ramla**,
1 sidoetikettbyte (NV→SO, breddad massa). Axial: 658 (339 lyckat / 313 ramla /
6 retreat). Fördelningar för framtida botjämförelser: lyckade massa p10/p50/p90
= 68.4/418.6/1201.0 u·s, grundade masksampel 0/14/57 (andel 0: 11.7 %);
ramla massa 45.7/285.4/1247.3, grundade masksampel 2/15/62.

**Övergångar v6.1→v7 (exakta, per transit):** oförändrade 1206;
återinträden till gate 24 st = axial-ramla→gate-ramla 11, axial-retreat→
gate-retreat 4, axial-lyckat→gate-lyckat 2, inget→gate-ramla 7. Endast 7
gate-event har ENBART ytterkantsmask-kontakt (0 sampel i gamla bandet) —
breddningen ändrar alltså få eventklassningar i sig.
*Om "545 tidigare demoterade":* siffran matchar ingen av mina arkiverade
klasser (v6.1-axial totalt 838; därav med v4-sidoetikett 167; med någon
v4-etikett 631) — de exakta övergångarna ovan ersätter den. Av de 838
v6.1-axiala återinträder 17 som gate; 164 axial-lyckat FALLER BORT HELT
(→inget) och 25 blir axial-ramla via landningsbekräftelsen, se varning 1.

## VARNING 1 (allvarlig): landningsbekräftelsen är dt-miskalibrerad för humandata — 33 % av äkta lyckade fälls

v6.1 hade 584 gate-lyckade; v7 behåller 392. Förlusten är INTE maskbreddningen
utan landningsbekräftelsen: 182 gate-lyckat→inget ("lämnade") och 12
gate-lyckat→gate-ramla. Diagnos av alla 206 obekräftade ankomster
(gatekandidater, andra passet i repro-kedjan):

| klass | n | dst-platsampel i fönstret p10/p50/p90 | maxrun ≥0.26 s | i gropen ≤2.75 s |
|---|---|---|---|---|
| obekräftad→inget | 193 | 9/16/27 | 97 % | **12 %** |
| obekräftad→ramla | 13 | 3/6/13 | 69 % | 100 % |

→inget-klassen är alltså ÄKTA ankomster med uthållig plattformsvistelse
(p50 0.82 s kontinuerligt) som saknar STRIKT grundat sampel (±0.5 u dz +
|d²z|≤0.2) — vid 51 ms-sampling registrerar bhoppande människor sällan
grundat (samma bias som källplattformskravets dokumenterade 11 %).
27-sampelfönstret är dessutom tidsinkonsistent: kalibrerat på ep1 (26 ms,
0.70 s) men blir 1.38 s på humandata. →ramla-klassen (13, varav 12 f.d.
lyckade): alla når gropen, men 38 % har först ≥0.5 s kontinuerlig
plattformsvistelse — sannolikt äkta ankomst följd av AVSIKTLIGT grophopp
(MH-dyk) som nu bokförs som misslyckad korsning.

**Bot-datat (26 ms) påverkas inte** (ep1 bekräftas, ep8 fälls korrekt — det
var syftet). Men bot-mot-human-jämförelser av lyckandegrad genom v7 blir
skeva (humannämnaren underskattas ~33 %). Rekommenderad dt-robust
bekräftelse (kräver beslut + omvalidering innan detektorändring):
`grundat dst-sampel ELLER ≥0.25 s/dt konsekutiva dst-plattformssampel utan
gropfall` — behåller 97 % av →inget-klassen och fäller fortfarande ep8
(1 enda fallande plattformssampel).

## VARNING 2: "ramla" utan gropexponering (ytterkantsfall) — 26 av 181

FP-sonderingen (punkt 3): den breddade masken släpper INTE in
korridortrafik som lyckade — **0 av 392 lyckade** har min dPit > 200
(p10/p50/p90 för alla gate-event: 69/132/176). Däremot har 26 av 181
gate-ramla (och 24 av 37 retreat) aldrig varit närmare gropcentrum än 200 u:
fall över YTTERKANTEN ner till undervåningen (z ≤ −100 utanför gropen),
dominerat av quad→ring (25 av 26). Under ägarformuleringen "utan att ramla i
gropen" är dessa strikt taget inte gropfall, och för människor är en del
sannolikt avsiktliga nedhopp till nedre våningen (ruttval) som nu bokförs som
misslyckade gateförsök. Om måttet ska betyda gropfall: villkora ramla på
fallpunktens gropnärhet (t.ex. dPit < 260 vid z≤PIT_Z; ytterkantsfall ⇒
"lämnade"). Ingen detektorändring gjord — beslut åt ägaren/koordinatorn.

## Kvarstående övervakningspunkter

1. Varning 1-beslutet (dt-robust bekräftelse) — före nästa humanjämförelse.
2. Varning 2-beslutet (gropexponeringskrav för ramla).
3. Bhop-underdetektion vid 26 ms (kvarstår från v6-listan).
4. Plattformscirkeln (r 260) och maskens t-fönster (−0.15…1.15) är modell.

## Repro

```
cd ~/rex-ml
.venv/bin/python evidence/repro/human_ledge_v7_baseline.py
  # ⇒ 227 segment, 1614 event; gate 392/181/37; 0 grazers; övergångsmatris
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/traj_63G.json      # SO 2/1/1
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ledge_60G.json  # SO 1/0/1
PYTHONPATH=. sim/.venv-sf/bin/python -m pytest rl/tests/ -q                      # 40 passed
```

Konfidens: hög på siffrorna (assert-paritet, dubbelspårning i samma loop);
varningarna är uppmätta klasser, inte tolkningar.
