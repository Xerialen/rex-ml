# LÅST — v7.3-omlåsning av humanbaslinjen: gate-event 735 → **726** (lyckat 580 + ramla 133 OFÖRÄNDRADE/identiska, retreat 22 → **13**; de 9 fällda är samtliga ring→quad NV-dörrtröskelretreats, min dPit 208.0–251.9, alla → axial retreat) + item-gate-baslinje under strict (RA **618** försök / 371 lyckade) + MEGA-BESLUT: **strict=True KAN driftsättas för SNG-mega med oförändrade trösklar (0.15 s / +130)** — korpusmätt 248/248 lyckade retained, alla 21 fällda missar är genomfartstrafik på z=112-gångbron (max z ≤ 112.0, ingen tar megan inom 10 s)

## v7.3-baslinje (analyst, 2026-08-03)

Detektor: `rl/jump_gates.py` v7.3 (commit d33ba28, koordinatorns implementation
av mina spec ur `evidence/analyst_73G_review.md`; 43 tester gröna).
Egenverifierad mot spec (diff `3fe4955..d33ba28` läst rad för rad):

- retreat-kvalifikation: `min_dpit >= RETREAT_PIT_R (192)` ⇒ `progressed=False`
  ⇒ axialspåret — exakt min skärpning (var 260). ✓
- item-gates `strict=True` (RA): kvalificering kräver `max_run*dt >= 0.15`
  ELLER `max_ground_gain >= 130`. dt-normeringen korrekt (3 sampel @51 ms =
  0.153 s; 6 @26 ms = 0.156 s). ✓
- SNG-mega körs `strict=False` (v7.2-semantik) i väntan på mega-beslutet
  nedan. ✓

**Flaggade avvikelser (ingen kod ändrad av mig):**

1. **Dwell-grenen räknar KONSEKUTIVA kvalificerande sampel (`max_run`), min
   kalibrering i review 10 räknade TOTALA (`n_simult`).** Uppmätt konsekvens
   på RA-humandata: retention **618/619** (99.84 %), inte 619/619 som
   koddocstringen påstår. Det enda fällda eventet är en genuin "loiterer"
   (demo 37651 slot 8, i0 83580: 14.5 s under RA, min_d2 113.6, n_simult 3
   icke-konsekutiva, max_run 1, grundad +83.6, EJ lyckat; samma spelares
   systerintervall i0 76626 överlever via konsekutiv run). Lyckat-retention
   **371/371 = 100 %**. Bedömning: acceptera — tolkningen är strikt
   konservativ mot bot-FP och kostar 0.16 % av försök, 0 % av lyckanden.
   Baslinjen låses på den DRIFTSATTA detektorn (618). Bevakningspunkt, ej
   ändringskrav.
2. Kosmetiskt: `_item_events`-docstringen citerar min uppmätta tomma region
   "grundad<+150" men tröskeln är (korrekt per spec) 130 — ingen åtgärd.

## SLUTLIG LÅST REGRESSIONSBASLINJE (v7.3, 24-demoskohorten, dt 0.051)

**726 gate-event:**

| gate | lyckat | ramla | retreat | försök |
|---|---|---|---|---|
| ring→quad NV | 208 | 13 | 1 | 222 |
| ring→quad SO | 232 | 43 | 5 | 280 |
| quad→ring NV | 84 | 13 | 5 | 102 |
| quad→ring SO | 56 | 64 | 2 | 122 |
| **totalt** | **580** (292 NV / 288 SO) | **133** (26 NV / 107 SO) | **13** (6 NV / 7 SO) | **726** |

Axial (informationsspår): **818** = 497 lyckat / 291 ramla / 30 retreat
(v7.2: 809 = 497/291/21 — de 9 fällda gate-retreaterna hamnar här).

Item-gates (samma kohort, deployerad semantik): **RA 618 försök / 371
lyckade** (strict); SNG-mega 1 försök / 1 lyckat (v7.2-semantik; kohorten är
för liten för megan — se korpusbeslutet nedan).

Human-lyckandegrader per gate (uppdaterade försöksnämnare, för
botjämförelser): ring→quad NV **94 %** (208/222), ring→quad SO 83 %,
quad→ring NV 82 %, quad→ring SO 46 %.

## Verifiering av prognosen ur analyst_73G_review (träffar)

- **lyckat 580 → 580, ramla 133 → 133** — per-event-identiska (True/True).
- **retreat 22 → 13** = 7 SO (rq 5 + qr 2) + 5 qr-NV + 1 rq-NV — exakt
  prognosen. De 9 fällda: samtliga ring→quad NV, min dPit **208.0–251.9**
  (alla ≥ 192), samtliga → `axial ring→quad` retreat.
  (Prognosen sade 208.0–250.4; skillnaden 250.4→251.9 är mätfönstret —
  review 10-kalibreringen inkluderade transitens t0-sampel, spårningen här
  börjar vid t0+1. Klassgränserna opåverkade.)
- **Behållna retreater: max min-dPit 169.3** (alla < 192) — 22.7 u marginal,
  som uppmätt i review 10.
- rq-NV: 208/13/**1** (222 försök) — prognosens exakta siffror.

## Liggarverifiering (uppdraget angav "4 liggarförda event" — jag finner **3**)

Kumulativa liggaren (`evidence/jump_gates_latest.json`) innehåller 3
gate-event: rq-SO = 63G ep1 lyckat + ep4 ramla (2), qr-SO = probe60G ep5
ramla (1). Alla 3 överlever v7.3 med IDENTISKA intervall:

- traj_63G ep1 `ring→quad SO lyckat` [186,249] ✓
- traj_63G ep4 `ring→quad SO ramla` [1098,1142] ✓
- probe_ledge_60G ep5 `quad→ring SO ramla` [16,92] ✓
- Dumpnivå: traj_63G ⇒ rq-SO 2/1/1/0 + axial 2; probe_ledge_60G ⇒
  qr-SO 1/0/1/0 + axial 1. Oförändrat mot v7.2.

**AVVIKELSE FLAGGAD:** om koordinatorn räknar ett fjärde liggarfört event
finns det inte i `jump_gates_latest.json` — specificera vilket.

Övriga regressioner (egenkörda, dumpnivå): traj_66G axial 4 ramla ✓;
probe_ledge_66G gate 0/axial 9 ✓; probe_ra_66G gate 0/axial 2 ✓;
traj_73G **RA 0** (v7.2-claimet borta) + axial 8 ramla ✓; probe_ledge_73G
**NV-retreat 0** (dörrtröskeleventet → axial, 6 = 4 ramla + 2 retreat) ✓;
probe_ra_73G gate 0/axial 3 ✓; traj_89G axial-retreat ep11 min dPit 255.3 =
den v7.2-demoterade dörrtröskel-NV:n ✓.

---

## MEGA-BESLUT: strict=True KAN DRIFTSÄTTAS för SNG-mega, oförändrade trösklar

Revalidering mot HELA korpusen (inte bara 24-demoskohorten, som genom
detektorlinsen bara har 1 mega-attempt): alla **2146** dm3/4on4/mvd-demos i
store-dm3, 964 parquetfiler, ~826 M sampel. Vektoriserad replika av
`_item_events`, PARITETSVALIDERAD mot detektorns egen funktion på hela
kohorten före korpuspasset (RA 619 v7.2-event + 618 strict-event + mega 1 —
intervallgränser, lyckat och strict-kvalifikation assertade identiska).
dt per segment = median(diff t) (korpusen spänner 13–54 ms).

**Korpusresultat: 323 mänskliga mega-attempts (v7.2-lins): 248 lyckade / 75
missade.**

| klass | n | retention under (dwell ≥ 0.15 s ∨ gain ≥ 130) |
|---|---|---|
| lyckade | 248 | **248/248 = 100 %** (dwell min 0.357 s = 2.4× marginal; 11 st med gain < 130 hålls av dwellgrenen, samtliga med dwell ≥ 0.52 s) |
| missade | 75 | 54/75 (72 %) — **men alla 21 fällda är genomfartstrafik, se nedan** |

**De 21 fällda missarna är den mänskliga analogen till
RA-trappspringklassen (genomfart på gångbron z=112 under megan), inte
genuina försök** (`evidence/repro/mega_dropped_inspect.json`, alla 21
individuellt uppmätta):

- max z i intervallet **67.9–112.0** — ingen når över gångbronivån
  (megan på 160; pickupgolvet 128). De 54 behållna: max z 133.9–240,
  z vid min-d2 oftast 184 = STÅENDE PÅ MEGAHYLLAN (spawn-denial/miss).
- grundad platåtid 0.01–0.16 s, medelfart 183–427 u/s, **0/21 tar megan
  inom 10 s efter intervallet** (flera behållna gör det).
- samtliga fällda ligger i dt 13–15 ms-demos; deras "klättring" är
  gångbrons golv (grundad gain 83.8–127.8 = strukturellt tak 128.0:
  gångbron z 112.0 − entrégolvet −16.0).

Fällningen är alltså en KORREKTION (samma semantik som RA-domen i
review 10), inte retentionförlust. Effektiv retention av genuina
mega-event: **248/248 lyckade + 54/54 genuina missar = 100 %**.

**Trösklar: behåll 0.15 s / +130 oförändrade.** Marginalnoteringar:

- Gain-grenen ligger i det uppmätta TOMMA bandet (127.8, 131.9):
  gångbroklassens strukturella tak 128.0 (2.0 u under tröskeln), närmaste
  genuina gain 131.9 (1.9 u över). Smalt men GEOMETRISKT (fast
  gångbrohöjd; entré-z är golvet −16 i alla 323 event, inget lägre finns) —
  ingen brusberoende gräns. Alternativa trösklar mättes: gain ≥ 104
  släpper igenom 7 gångbroevent; gain ≥ 150 fäller 1 genuint lyckat-stöd;
  dwell 0.10–0.25 ändrar ingenting i någondera klassen.
- dt-känslighet dwellgrenen: endast 1/75 miss hålls av ENBART dwell
  (35672/5: dwell 0.27 s, hopp mot hyllan från hög entré 91.6); alla
  övriga genuina går via gain-grenen som är dt-oberoende.

**Åtgärd för koordinatorn (jag ändrar inte rl/):** sätt `strict=True` för
SNG-mega i `analyze()` och `main()` (två rader), uppdatera docstringen.
Efter bytet: kohortbaslinjen mega = **1 försök / 1 lyckat** (kohortens enda
attempt har dwell 3.52 s + gain 244 — passerar båda grenarna).

## Kvarstående övervakningspunkter

1. Konsekutiv- vs total-dwell (avvikelse 1 ovan): 618/619 RA-retention;
   ombedöm om en bot-klass med legitimt flackande grundkontakt dyker upp.
2. Bhop-underdetektion vid 26 ms (ärvd, kvarstår).
3. Plattforms-/gropcirklarna och maskens t-fönster är modeller, inte BSP
   (ärvd, kvarstår).
4. Mega-gain-marginalen 2.0 u mot gångbrotaket (strukturell men smal) —
   om en botdump någonsin visar mega-försök med gain 128–132: inspektera
   manuellt innan bokföring.

## Repro

```
cd ~/rex-ml
PYTHONPATH=. .venv/bin/python evidence/repro/human_ledge_v73_baseline.py
  # ⇒ 227 assert-verifierade segment; gate 580/133/13 (726); axial 497/291/30;
  #   fällda 9 = ring→quad NV, dPit 208.0-251.9, -> axial retreat;
  #   RA strict 618/371 (1 fälld loiterer listad); kohort-mega 1/1
PYTHONPATH=. .venv/bin/python evidence/repro/mega_dwell_corpus.py
  # ⇒ PARITET OK (227 segment, RA 619/mega 1); korpus 2146 demos,
  #   323 mega-attempts, retention 248/248 lyckade, 54/75 missade
PYTHONPATH=. .venv/bin/python evidence/repro/mega_dropped_inspect.py
  # ⇒ de 21 fällda: max z <= 112.0, 0/21 mega inom 10 s (tabell)
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/traj_63G.json         # rq-SO 2/1/1, axial 2
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ledge_60G.json  # qr-SO 1 ramla, axial 1
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/traj_73G.json         # gates 0, axial 8
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ledge_73G.json  # gates 0, axial 6
PYTHONPATH=. sim/.venv-sf/bin/python -m pytest rl/tests/ -q                         # 43 passed
```

Artefakter: `evidence/repro/human_ledge_v73_baseline.json` (1544 gate-
eventposter dubbelspårade v7.2/v7.3, 619 RA-instrumenterade, kohortmega),
`evidence/repro/mega_dwell_corpus.json` (323 korpus-megaevent),
`evidence/repro/mega_dropped_inspect.json` (21+54 inspekterade).

Konfidens: **hög** (gate-delen: per-event-identisk dubbelspårning assertad
mot detektorn på alla 227 segment; mega-delen: fullkorpus, paritetsvaliderad
replika, individuell inspektion av samtliga gränsfall). Baslinjen LÅST för
framtida omvalideringar av denna kohort. Ersätter
`evidence/analyst_v72_baseline.md` som regressionsbaslinje (v7.2-dokumentet
behålls som historik).
