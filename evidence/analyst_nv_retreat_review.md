# DOMSLUT: probe_ledge_66G "ring→quad NV 1 retreat ⇒ nivå 1" — UNDERKÄND (siffran reproducerad, men eventet är sidogolvsvandring utan korsningsengagemang, inte ett påbörjat korsningsförsök); probe_ra_66G "ring→quad NV 1 retreat ⇒ nivå 1" — UNDERKÄND (samma klass: ut-och-tillbaka på sidogolvet, gropexponering saknas helt)

## Vetogranskning av NV-retreat-claims @6.6G (analyst, 2026-08-02)

### Claims och repro

Båda claims REPRODUCERAR exakt under låst v7.1 (`rl/jump_gates.py` oförändrad):

```
cd ~/rex-ml
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ledge_66G.json
  # ⇒ ring→quad NV 1/0/0/1 (nivå 1); axial 8 ramla
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ra_66G.json
  # ⇒ ring→quad NV 1/0/0/1 (nivå 1); axial 1 ramla
```

Detektorutfallet är alltså korrekt — underkännandet gäller SEMANTIKEN
("försök = uppvisad medvetenhet om hoppet som genväg", ägarens nivå 1-ord),
prövad mot exakt den övervakningspunkt jag dokumenterade vid baslinjelåsningen
(`evidence/analyst_v71_baseline.md`, punkt 1: retreat saknar
gropexponeringskrav).

### Transitextraktion (instrumenterad spegling av detektorloopen,
assertad event-för-event mot `jg._ring_quad_events`;
`evidence/repro/nv_retreat_review.py` → `nv_retreat_review.json`)

| | probe_ledge_66G ep8 [16,157] | probe_ra_66G ep4 [1934,1998] |
|---|---|---|
| källvistelse (sampel/grundade) | 17 / 13 (ring) | 57 / 1 (ring) |
| transitlängd | 3.67 s | 1.66 s |
| masksampel (grundade) | 81 (2) | 63 (9) |
| luftburna transitsampel | 124 | 55 |
| \|perp\| i mask min/med/max | 176 / 225 / 469 | 158 / 217 / 287 |
| min d(quad) | 430 | 400 |
| max axialprogression t | 0.563 | 0.550 |
| **min dPit över transiten** | **328** | **310** |
| retreatpunkt (perp, dPit) | (289,219,81) v=499; 207, 383 | (342,204,99) v=449; 172, 336 |

Banbilder (rådata i reprons utskrift): **ep8** bunnyhoppar från ringen längs
NV-golvet till tax≈0.56, svänger sedan UT ur masken till perp 643 / dPit 797
(3 u från HEX_R=800 ⇒ hade blivit "lämnade"), stannar (v=43) i NV-gården,
och tar en returbåge tillbaka till ringen — en cirkulationsloop. **ep4** gör
en tajtare ut-och-tillbaka helt inne i masken: vänder vid (550,321), tax
0.55, med varvtalsdipp 472→371, aldrig närmare gropen än 310.

### Humankalibrering (24-demoskohorten, dt 0.051; samma instrumentering,
750 gate-event = exakt baslinjetabellen; `nv_retreat_review_human.json`)

min dPit över transiten (min_dpit_all):

| kohort | n | p5 | p50 | p95 | max |
|---|---|---|---|---|---|
| NV **lyckat** (båda riktningar) | 292 | 120–130 | ~150 | 169–176 | **192** |
| NV **ramla** | 26 | 3–49 | 54–149 | 155–183 | 192 |
| ring→quad NV **retreat** | 25 | 208 | 267 | 298 | **305** |
| quad→ring NV **retreat** | 5 | 127 | 139 | 164 | 167 |
| SO retreat | 7 | 15 | 115 | 136 | 136 |
| **bot ep8 / ep4** | 2 | — | — | — | **328 / 310** |

Tre lägen i humandatan:

1. **Korsningskorridoren kräver gropnärhet:** samtliga 292 lyckade och
   samtliga 26 ramla på NV har min dPit ≤ 192 (perp-komponent: gropcentrum
   ligger på perp −150, så dPit 192 ⇒ inre remsan perp ≲ 42 vid gropens
   axialläge). Det finns INGEN genuin NV-korsning som håller sig utanför
   dPit 192 — NV-golvet är kontinuerligt (voxelprofil i repro-utskriften,
   inget tax-gap) men själva överfarten skär gropens innerkant.
2. **Genuina avbrutna försök ser ut därefter:** quad→ring-NV- och
   SO-retreaterna (12 st) har dPit 15–167 — de nådde korridoren och vände.
3. **Vandringsklassen finns redan i humandatan:** ring→quad-NV-retreaterna
   är till stor del min varnade klass (15/25 har dPit ≥ 260; ofarlig i
   humanbaslinjen, som noterat vid låsningen).

Botarnas två event ligger på 310/328 — UTANFÖR även hela
humanretreat-fördelningen (max 305) och 118–136 u utanför varje genuin
korsnings envelope. Ingen gropexponering, ingen korridorkontakt, vändning
mitt på gångbart golv utan tvingande hinder. Detta är inte "påbörjad korsning
som avbryts" utan sidogolvsvandring som råkar uppfylla retreat-mekaniken
(mask + d<450 + massa + grundad källa). min-d-värdena (430/400) ligger
dessutom precis innanför 450-bandet — nära-gränsen-progression, inte
målinriktad ansats.

### Föreslaget retreat-kvalifikationskrav (v7.2-förslag, ägar-/huvudagentbeslut)

**Retreat bokförs som gate-försök endast om transiten var gropexponerad:
min dPit över transitsampeln < PIT_EXPOSURE_R (260) — samma konstant som
v7.1:s ramla-semantik.** Ingen ny parameter införs.

Humankalibrering av kravet:

- Lyckat/ramla: **opåverkade per konstruktion** (580 + 133 står).
- Retreat: 37 → **22** (7/7 SO + 15/30 NV behålls). De 15 som faller bort
  (dPit 260–305) är separerade från den genuina försöks-enveloppen (≤192)
  med ≥ 68 u — ingen genuin avbruten korsning i kohorten tappas
  (marginal till närmast behållna genuina: retreat-dPit 252→260 = 8 u;
  till närmast fällda: 260→305; botarna 310/328 fälls med ≥ 50 u marginal
  — inget knivseggsbeslut).
- Baslinjetabellen blir vid antagande: totalt 735 gate-event
  (580/133/22); ring→quad NV 208/13/10.

Kravet gäller endast retreat-utfallet; axialspåret berörs inte.

### Konsekvens för claims och kumulativa stegen

- Nivå 1-krediteringen "första NV-sidans försök" ska INTE bokföras för
  någon av dumparna; kumulativa stegen för ring→quad NV lämnas oförändrad.
- probe-dumparnas övriga utfall (axial 8 resp. 1 ramla) berörs inte.
- Om v7.2-kravet antas ska humanbaslinjen låsas om (samma repro,
  en rad ändras) innan nya botclaims bedöms mot den.

### Repro

```
cd ~/rex-ml
PYTHONPATH=. sim/.venv-sf/bin/python evidence/repro/nv_retreat_review.py
  # botdumparna: 9+2 event, assert mot detektorn; detaljrader ovan
PYTHONPATH=. .venv/bin/python evidence/repro/nv_retreat_review.py --human
  # humankohorten: 750 gate-event (=låst baslinje), 37 retreat, fördelningarna ovan
```

Konfidens: hög (dubbel evidens — bot-transiterna i rådata + hela
humanfördelningen på tre utfallsklasser; instrumenteringen assertad mot den
låsta detektorn på samtliga segment i båda kohorterna).
