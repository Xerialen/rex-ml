# UNDERKÄND

## Vetogranskning: ledgeprobe-claimet "quad→ring SO: 1 försök, 0 lyckade, 1 ramla"

Analyst, 2026-08-02. Claim: v4-detektorn (`rl/jump_gates.py`, orörd) på
`~/dumps/probe_ledge_60G.json` (gate2_v2 @6.0G, 10 episoder, `--spawn ledge`).
Detektorn har inte ändrats i denna granskning.

## Domslut

**UNDERKÄND.** Siffrorna reproducerar exakt, och plattformslämningen + gropfallet är
genuint beteende — men eventet är **inte en påbörjad korsning längs SO-ledgen**. Det är
ett enda ballistiskt hopp rakt ut i gropgapet längs ring→quad-axelns mitt: noll sampel
(grundade eller luftburna) i SO-ledgebandet, och SO-etiketten vilar på 2 luftburna
sampel som passerar dödzonen med 0,8 respektive 0,04 enheter. Bottens sidosignal
(|side_acc| = 201) ligger **under samtliga 37 mänskliga misslyckade quad→ring
SO-korsningar** i samma detektor (min 205, median 12 468) — trots att bottens 26
ms-sampling ger ~2× fler bidragssampel per tidsenhet än människornas 51 ms.

## Reproduktion

```
cd ~/rex-ml && PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ledge_60G.json
# → quad→ring SO: {"försök": 1, "lyckade": 0, "ramla": 1, "retreat": 0, "nivå": 1}; övriga gates 0. Claimet reproducerar.

# Instrumenterat spår (assert-verifierat identiskt med detektorns eventlista):
PYTHONPATH=. sim/.venv-sf/bin/python evidence/repro/vet_ledgeprobe.py ~/dumps/probe_ledge_60G.json

# Mänsklig baslinje genom SAMMA v4-detektor (24 slumpade 4on4-dm3-demos ur store-dm3):
.venv/bin/python evidence/repro/human_ledge_baseline.py
# → evidence/repro/human_ledge_baseline.json
```

## Det exakta transitsegmentet (episod 8, sampel 493–523)

Observerat (allt ur `vet_ledgeprobe.py`-spåret; 26 ms/punkt):

- **Kontext före:** spawn sampel 0 på NV-ledgen (688, 464, 56; perp +264 — probens
  spawnspec uppfylld). Eventet inträffar vid t ≈ 12,8 s — **inte spawnsettling**.
  Sampel 440–447: botten går grundad på SO-ledgens quad-ände (z 56, perp −229..−290,
  d(pit) 331–449), hoppar därifrån upp på quadplattformen.
- **Plattformsvistelsen (utgångsvillkoret):** 8 grundade sampel på quadplattformens
  golv, sampel 475–482 (z = 56,0; d(quad) 116–194; 0,21 s). Kort men äkta markkontakt
  — inte flyktig radiepassage i luften (44-punktersintervallet 450–493 är i övrigt en
  hoppbåge genom plattformscylindern).
- **Avstampet:** sista grundade sampel 482 vid (759, 317, 56). Horisontell fart
  483→493: 455 u/s, riktning (−0,32, −0,95).
- **Ledgevistelsens z-kurva:** det finns ingen. Transitsegmentet 493–523 har **0
  grundade sampel**; d²z över sampel 486–523 är medel −0,542 u/sampel² (min −0,70, max
  −0,40) = exakt gravitationen (800 u/s² × 0,026² = 0,541). En enda obruten hoppbåge:
  apex z 99,8 (sampel 496), fritt fall till z −101,2 (sampel 523).
- **Sidoklassningen:** side_acc = −201 från exakt 2 sampel: 509 (perp −100,8, z 52 —
  luftburet) och 510 (perp −100,0(4), z 45 — luftburet). Banans perp går +11 → −101 →
  +21: den **korsar axeln** och tangerar SO-bandets innerkant i en punkt. Max |perp| i
  transiten = 101. SO-ledgebandet (|perp| 100–300, z 48–112) besöks aldrig i övrigt.
- **Progressionen:** d(ring) < 350 uppnås först vid sampel 513–516 (d 341→305) vid
  z 19,2 → −11,2 — **under ledgebandet (48–112), i fritt fall**. Framstegsvillkoret
  intjänas alltså av själva störtningen, inte av korsningsframsteg på ledgenivå.
- **Fallpunkten:** z ≤ −100 vid (476, 99); botten bottnar z −200 vid (491, 177) och
  går sedan uppför gropsluttningen österut. Detta är **MH-gropen** (gropgolv −192)
  — inte hiss, vatten eller annan geometri. "Ramla"-utfallet i sig är korrekt.

## Mänsklig jämförelse (samma detektor, samma mått)

24 slumpade 4on4-dm3-demos (hash-ordnade demo_keys i
`evidence/repro/human_ledge_baseline.json`), alla slots, gap-splittade trajektorier:

| Kohort | n | ledge-grundade sampel p10/p50/p90 | andel 0 | \|side_acc\| p50 | prog_z p10/p50 |
|---|---|---|---|---|---|
| quad→ring alla | 472 | 0/0/15 | 0,67 | 207 | 89/99 |
| quad→ring SO | 119 | 0/4/18 | 0,35 | 16 374 | 32/98 |
| quad→ring SO **ramla** | 37 | 0/0/10 | 0,51 | **12 468** | −10/70 |
| quad→ring SO lyckat | 80 | 0/5/20 | 0,29 | 17 649 | 94/98 |

- En typisk mänsklig **misslyckad** SO-korsning tillbringar sekunder på SO-sidan
  (|side_acc| median 12 468 ≈ hundratals sampel djupt inne i bandet; transitlängd
  median 2,9 s) innan fallet. 49 % har grundad ledgekontakt; 51 % saknar den eftersom
  människor bunnyhoppar längs ledgen — **frånvaro av grundade ledgesampel fäller
  alltså inte ensamt bot-eventet**, det är sidosignalen som gör det.
- Bottens |side_acc| 201 < mänskligt minimum 205 (0/37 under botten); transit 0,78 s
  < mänsklig p10 1,1 s; prog_z 19 < mänsklig ramla-p50 70.
- Även människor producerar enstaka marginella axialhopp som SO-klassas (4/37
  "bot-lika" event med 0 ledge-grundade och |side_acc| < 500) — detektorluckan
  drabbar humandata med låg frekvens (~11 %), botdumpen med 100 % (1/1).

## Förmågeproben i övrigt (10 × 60 s med ledgestart)

Trots att episoderna startar PÅ ledgevoxlarna är total grundad ledgevistelse
(|perp| 100–300, z-band 40–130, inom hexagonen) **3,6 s av 600 s**; längsta
sammanhängande run 0,60 s (ep 0). Botten kliver av ledgen nästan omedelbart i varje
episod. Probens fråga — "kan botten korsa när den står där?" — besvaras: **ingen
korsningsförmåga uppvisad; botten stannar inte ens på ledgen.**

## Villkorsluckan (detektorn oförändrad; för ev. framtida ägar-/driftbeslut)

1. **Sidoetiketten saknar minimimassa:** `side` = tecknet på side_acc, så ett enda
   sampel 0,04 u utanför dödzonen (|perp| > 100) avgör NV/SO. Ett axialt gaphopp vars
   bana tangerar bandkanten bokförs som sidoledge-försök.
2. **`onto_ledge`/`progressed` kräver ingen ledgebandsnärvaro:** varje luftburet
   sampel utanför plattformarna med z > −20 sätter onto_ledge, och progressionen kan
   intjänas i fritt fall under ledgenivån (här z 19 → −11). Gatens semantik ("över
   hexagonens sidoledger") kräver rimligen ≥ några sampel med |perp| ∈ (100, 300) ∧
   z ∈ ledgebandet; annars bör eventet klassas "axialt gaphopp" (egen räknare), inte
   som någon av de fyra sidogaterna.

## Slutsats

- **Underkänt som claim:** "quad→ring SO-försök" — eventet är inte en SO-ledgekorsning.
- **Genuint och rapporterbart i stället:** ett äkta axialt gaphopp quad→ring (verklig
  plattformslämning efter 0,21 s markkontakt, ballistiskt språng 455 u/s mot
  ringhållet, fall i MH-gropen) vid 12,8 s in i ep 8 — första uppvisade
  gropkorsningsintentionen i riskregimen, men i en kategori detektorn inte har.
  Korrekt v4-bokföring för proben vore: sidogater 0 försök över hela linjen.
- Konfidens: **hög** (ballistisk signatur, sidosignal och humanbaslinje pekar
  samstämmigt; trace assert-verifierat mot detektorns eventlista).

Repro: `evidence/repro/vet_ledgeprobe.py`, `evidence/repro/human_ledge_baseline.py`,
`evidence/repro/human_ledge_baseline.json`. Dump: `~/dumps/probe_ledge_60G.json`
(oförändrad). Detektor: `rl/jump_gates.py` (oförändrad).
