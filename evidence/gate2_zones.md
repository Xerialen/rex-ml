# Gate 2 — evidensbaserad zonklassificering av dm3 (vilka voxlar räknas i >500 UPS-medlet)

Genererad av `pipeline/gate2_zones.py` (stegen `stats → classify → zonestats → report`).
Maskinläsbar version: `evidence/gate2_zones.json`. Raster: `pipeline/out/gate2/` (format sist i dokumentet).

## Datakällor och metod

- **Korpus:** `~/dm3-extract/store-dm3/trajectory_samples`, 907 977 350 råa rader (alla splits,
  MVD + QWD), varav **898 923 363 filtrerade hastighetssampel** ingick i mätningen.
- **BSP:** `~/mlx/qwserver/serverdir/id1/maps/dm3.bsp` — leaf-contents (hull 0) för vatten,
  entiteter för func_plat (3 st, kedjade hissar), trigger_teleport (2 st) och destinationer.
- **Hastighet:** HORISONTELL fart via centraldifferens över positioner per (demo_key, slot),
  eftersom MVD-samplen saknar velocity-kolumner. Vertikalkomponenten ingår inte alls:
  16 u-trappsteg ger fantom-vz upp till ~1140 u/s.
- **Filter (alla mätta, inte antagna):**
  - båda intilliggande luckorna ≤ 200 ms; 3D-diskontinuiteter > 250 u kastas (respawns,
    teleporter, pauser). Storen har ingen run-kolumn — demo/slot-partitionerna plus
    diskontinuitetsfiltren ÄR run-gränserna.
  - **centraldifferensens spann ≥ 20 ms**: spann < 20 ms ger p99,9 = 1394–4094 u/s
    (förstärkt 0,125 u-kvantiseringsbrus) mot QWD-facit |v_xy| p99,9 = 840 u/s;
    spann 20–40 ms ger 916 u/s (inom 9 % av facit). Bortfall: ~0,4 % av samplen.
  - **3-sampels medianfilter** på fartsekvensen före alla percentiler.
- **Tak-kriteriet är p99,9, inte rå max:** deriverad max är warpkontaminerad
  (uppmätt 12 361 u/s mot QWD-sant max 3 135 u/s). p99,9 spårar sanna hastigheter.
- Voxelstorlek 32 u, index = floor(koordinat/32).

**Korsvalidering av vattenklassningen:** QWD-delens liquid-flagga (`lq`) ger 99,3 % våt-andel
i voxlar klassade som vatten och 0,4 % i torra — klassningen och BSP-parsningen stämmer.
Tre zoner vid vattenytan (spelarorigin i luftspalten OVANFÖR vatten-leafen, BSP säger EMPTY)
var 100 % våta enligt `lq` och flyttades till EXCLUDED_WATER — simfysiken cappar dem lika hårt.

## Klassandelar (42 379 voxlar med trafik)

| Klass | Voxlar | Volymandel | Sampel | Trafikandel | p50 | p95 | p99 | p99,9 |
|---|---|---|---|---|---|---|---|---|
| EXCLUDED_WATER | 4 716 | 11,1 % | 89,9 M | 10,0 % | 168 | 208 | 327 | 500 |
| EXCLUDED_LIFT | 254 | 0,6 % | 9,7 M | 1,1 % | 30 | 362 | 431 | 597 |
| EXCLUDED_TELE | 28 | 0,07 % | 0,37 M | 0,04 % | 0 | 342 | 427 | 754 |
| INCLUDED_OPEN | 31 971 | 75,4 % | 739,4 M | 82,3 % | 335 | 496 | 580 | 909 |
| INCLUDED_CONSTRAINED | 854 | 2,0 % | 59,5 M | 6,6 % | per zon | — | — | 345–497 |
| INCLUDED_LOWDATA (<30 sampel) | 4 556 | 10,8 % | 40 k | 0,005 % | brus | — | — | — |

## Varför varje exkludering

- **Vatten (10,0 % av trafiken):** simfysik cappar farten (maxspeed 360 × 0,7 = 252 u/s i
  serverns dominerande movevars). Uppmätt: p50 168, p95 208, medel 149 u/s. Fysiskt
  oförenligt med 500-målet — ingen policy kan ändra det.
- **Hissar (1,1 %):** func_plat-bboxar + schaktet upp till översta stoppet, xy-expanderat 32 u,
  z från nedersta stoppet (topposition − travel; travel = brushhöjd − 8, Quake-standard) till
  toppyta + 64 u (ryttarens origin). p50 = 30 u/s — man STÅR på hissen. De tre hissarna är
  kedjade (vattennivå → z 191) och tvingar stillastående i hela schaktet.
- **Teleportrar (0,04 %):** triggervolymerna expanderade med spelarhullens halvmått
  (±16 xy, −24/+32 z) — dm3:s råa triggerboxar är 22×46×30 u, tunnare än en voxel, så utan
  expansionen träffas 0 voxlar (uppmätt innan fixen). p50 = 0: man materialiseras stillastående.
  Destinationsplattorna är INTE exkluderade (t2-utgången dyker i stället upp som takad zon).
- **LOWDATA:** 10,8 % av den traverserade volymen men 0,005 % av trafiken (engångsbesökta
  luftvoxlar under hopp m.m.). Percentiler på < 30 sampel är brus (aggregat-p99,9 = 2 183 —
  rena artefakter). Räknas inte i gaten; ingen fartutsaga går att försvara där.

## OPEN-tröskeln: briefens p95 ≥ 400 förkastad, ersatt med p99,9 ≥ 500

Briefens förslag (p95 ≥ 400 ⇒ OPEN) testades: 3 188 av 31 971 voxlar (10 %) där människor
bevisligen nått ≥ 500 u/s (p99,9 ≥ 500) har ändå p95 < 400 — det är item-ställen och
campytor där folk oftast står stilla. p95 mäter BETEENDE, inte geometri. Kriteriet blev
därför: **CONSTRAINED om mänsklig p99,9 < 500 u/s** (ingen av tiotusentals passager nådde
gate-farten ⇒ geometriskt tak), annars OPEN. Notera att OPEN-klassens egen p95 är 496 u/s —
även öppna ytor trafikeras av människor mestadels under 500 (4on4-strid, inte fartåkning);
gaten på 500 i medel är alltså ett krav ÖVER mänskligt spel, under bunny-taket (821 u/s på 100m).

## Takade zoner (torra, trafikerade, mänskligt tak < 500 u/s)

39 namngivna zoner (252 sammanhängande komponenter, 26-konnektivitet; namn = närmaste
landmärke, kurerad beskrivning i JSON:ens `desc`). De viktigaste, exakta sampelnivå-
percentiler ur andra korpuspasset:

| Zon (beskrivning) | Sampel | p50 | p95 | p99 | **p99,9 (tak)** |
|---|---|---|---|---|---|
| ratop — RA-toppplattformen | 18,0 M | 43 | 365 | 430 | **482** |
| rl — RL-plattformen | 9,5 M | 0 | 320 | 365 | **438** |
| quad* — avsatsen ovanpå översta hissen | 8,7 M | 98 | 359 | 396 | **440** |
| mega-sng — mega-hyllan i SNG-rummet | 3,1 M | 164 | 368 | 421 | **472** |
| pent* — hisschaktets norra avsatser | 2,9 M | 172 | 389 | 430 | **470** |
| ya — YA-stället | 1,8 M | 0 | 274 | 345 | **417** |
| tele-sng-in — trappschaktet mot t2/RA-låg | 0,69 M | 340 | 407 | 438 | **494** |
| ssg-ya — SSG-hyllan | 0,52 M | 320 | 402 | 438 | **484** |
| ratop-2 — kantavsatsen öster om RA-toppen | 0,51 M | 40 | 322 | 380 | **458** |
| ralow-ng-tunnel — NG-tunnelmynningen, RA-låg | 0,46 M | 47 | 312 | 356 | **444** |
| sng (+2..6) — SNG-rummets trånga partier | 0,97 M | — | 263–394 | 336–444 | **415–477** |
| window — fönstret quad-våningen ↔ RL | 0,33 M | 0 | 196 | 310 | **381** |
| ssg-ya-2 — östra rampen YA → RL/mega-pent | 0,28 M | 331 | 429 | 450 | **497** |
| quad-2 — övervåningspassagen ring ↔ quad | 0,16 M | 0 | 178 | 309 | **442** |
| ring — nedre korridorshörnet under ring | 53 k | 0 | 255 | 352 | **443** |
| mega-hill(+2) — spalten vid kullens mega | 27 k | 0 | 175 | 244 | **345–367** |
| constrained-misc — 335 spridda kantvoxlar | 11,4 M | 47 | 347 | 411 | **468** |

*Auto-namnen "quad"/"pent" avser närmsta landmärke; geometrin är hisstoppens avsatser
(se `desc` i JSON). Full lista med bounds för alla 39 zoner: `evidence/gate2_zones.json`.

Caveat: zoner som RL-plattformen och RA-toppen är hårt campade — klassningen är
evidensbaserad, så "öppen geometri där ingen någonsin rusar" hamnar som takad med taket satt
av snabbaste uppmätta genomfart. Det är avsiktligt: taket ÄR det bevisat möjliga.

## Rekommendation och gate-formel

**"Exkludera vatten/hiss/tele + platt 500-gate på resten" räcker INTE.** 6,6 % av trafiken
ligger i torra zoner med uppmätta mänskliga tak 345–497 u/s. En platt 500-gate över dem gör
ett av två: sänker agentens uppmätta medel när den täcker kartan korrekt, eller (värre, med
RL-tryck mot gaten) lär agenten att UNDVIKA tunnlar, fönstret, hissavsatserna och RA-toppen —
tvärtemot "obehindrad navigering". Zonvisa trösklar behövs.

**Gate 2-formel (konkret):**

Under valideringsrundan (fritt strövande på riktiga mvdsv-servern, per bevisregeln), för
varje tick t med voxel v(t):

```
T(v) = 500                     om v ∈ INCLUDED_OPEN
T(v) = 0,8 × p999_zon(v)       om v ∈ INCLUDED_CONSTRAINED   (tabell: gate_recommendation.zone_targets_u i JSON, 276-399 u/s)
v ∈ EXCLUDED_* ∪ INCLUDED_LOWDATA  ⇒ ticket räknas inte

score = medel_t[ v_h(t) / T(v(t)) ]

PASS  ⇔  score ≥ 1,0
      OCH medel(v_h | INCLUDED_OPEN) > 500 u/s        (huvudkravet, oförvanskat)
      OCH ≥ 70 % av INCLUDED_OPEN-voxlarna besökta     (anti-loop-skydd: annars kan en
                                                        enda bunny-slinga maxa medlet)
```

Faktorn 0,8 mot p99,9 är medvetet sträng: p99,9 är enstaka perfekta genomfarter; 80 % av
det som UTHÅLLIGT medel i zonen kräver nära människo-optimal transit utan att kräva fysiskt
omöjliga trickhopp. (Jämför: mänskligt MEDEL i zonerna är 12–320 u/s — campning dominerar.)

## Filformat, raster (`pipeline/out/gate2/`)

- `voxel_classes.npz` (837 kB, numpy komprimerad, sparse): parallella arrayer över de
  42 379 trafikerade voxlarna — `ix,iy,iz` (int16, världskoord = index×32), `cls` (uint8:
  1=WATER 2=LIFT 3=TELE 4=OPEN 5=CONSTRAINED 6=LOWDATA), `n` (uint32), `p50,p95,p99,p999,mx`
  (float32, u/s), `zone` (int16, index i metans zonlista, −1 = ingen), `contents` (int8,
  BSP-leafcontents). Belöningskalkylatorn slår upp voxel → (cls, zon-tak) direkt.
- `voxel_classes_meta.json` — klasskoder, zonlista (id, namn, bounds, centroid), hiss-/
  televolymer, filterparametrar.
- `voxel_stats.parquet` (2,1 MB) — råa per-voxel-statistiken (n, percentiler, lq-våtandel).
- `zone_map.parquet` + `zone_stats.parquet` — voxel→zon-nyckeln och de exakta sampelnivå-
  percentilerna per zon/klass (andra korpuspasset).
