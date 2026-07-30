# dm3-teleportrarna och Gate 2-bevismätningen — hastighetsanalys

Analys: dm3-analytikern, 2026-07-30. Fråga från Gate 2-bevisdesignen: hur ska
bevismätningen på riktiga mvdsv-servern behandla tele-genomfarter, givet att
kandidatpolicyn tränats i en sim där teleportrarna är döda?

## Fråga och omfattning

1. Hastighetsprofil sista ~0,5 s före inträde / första ~0,5 s efter utträde, per teleporter.
   Bevarar servern farten, nollställer den, eller ger utkastet en impuls?
2. Använder skickliga spelare telen som fartverktyg eller ompositionering, kvantifierat
   mot zonernas normala farter?
3. Konkret regel för Gate 2-protokollet.

Kohort: hela store-dm3 (3 777 demos, 7 564 spelartimmar, 908 M trajectory_samples;
MVD + QWD, alla splits). Strikt kohort redovisas separat: demos utan
wipeout/2v2v2v2-CA/FFA i namnet (3 561 demos, 7 265 spelartimmar) — storens
`mode=4on4`-partition innehåller bevisligen även dessa specialformat
(match-validitetskontroll enligt analyst.md §2; se Validering).

## Geometri (observerad: BSP-entitetslumpen, `~/mlx/qwserver/serverdir/id1/maps/dm3.bsp`)

| Tele | Trigger (rå bbox) | Läge | Destination | Vinkel | 2D-förflyttning |
|---|---|---|---|---|---|
| t1 | (1169,−927,−15)–(1191,−881,15) | YA-gården, väster om YA | (1328, 544, 44) | 270° | 1 455 u → window-zonen |
| t2 | (−519,−471,1)–(−497,−425,47) | RA-låg | (224, −320, 48) | 45° | 741 u → ring-underplanet |

Parsning: `pipeline.gate2_zones.Bsp` + `entity_volumes` (samma kod som zonklassningen);
`info_teleport_destination` t1/t2 ur samma entitetslump.

## Metod (reproducerbar)

Verktyg: duckdb 1.5.5 (`~/rex-ml/.venv`), 12 trådar, direkta pass över
`~/dm3-extract/store-dm3/trajectory_samples/split=*/**/*.parquet`.

1. **Delextrakt** (32 s, 2,8 GB scratch-parquet, 426 M rader): alla sampel inom
   ±460 u xy / ±250 u z runt de fyra punkterna trigger-t1, dest-t1, trigger-t2, dest-t2
   (0,5 s före inträde ryms: p99,9-fart 909 u/s ⇒ ≤ 455 u).
2. **Eventdetektering:** per (demo_key, slot) sorterat på t: sampelpar med
   `1 ≤ dt ≤ 200 ms`, 3D-steg > 250 u, föregående sampel i hull-expanderad triggerbox
   (±16 xy, −32/+24 z — samma expansion som EXCLUDED_TELE) och nästa sampel inom
   160 u 2D av destinationen med |z−60| ≤ 120.
3. **Hastighetsprofil:** parvisa positionsdifferenser (dt ≤ 200 ms, 3D-steg ≤ 250 u,
   samma filter som gate2-pipelinen) i 125 ms-binnar −750..0 ms före inträdet och
   0..+625 ms efter utträdet, plus per-event medelfart över 0,5 s-fönstren.
   QWD-sampel med `velocity_present` ger dessutom serverns wire-velocity som facit.
4. **Fotbaslinje:** för spelare som lämnar triggerzonen UTAN teleport: tid till första
   ankomst inom 120 u 2D av destinationen inom 30 s.

## Fynd

### 1. Servern bevarar INTE farten och nollställer den inte — den ERSÄTTER den med en fast 300 u/s-impuls

**Observerat (wire-facit, QWD):** utträdessampelns servervelocity är exakt
|v_xy| = 300,0 u/s, yaw = −90° = destinationsvinkeln 270°, vz = 0
(demo `d4dac3132de728d5_PAINvsDS.qwd`, slot 2, t_in = 3 544 593 ms).
Detta är standard-QW-progs `teleport_touch`: `velocity = v_forward * 300`,
oberoende av inträdeshastigheten.

**Observerat (positionsderiverat, t2, n = 27 event):**

| 125 ms-bin | −750 | −625 | −500 | −375 | −250 | −125 | +0 | +125 | +250 | +375 | +500 | +625 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| p50 h-fart (u/s) | 301 | 319 | 385 | 402 | 423 | **444** | **302** | 308 | 358 | 369 | 412 | 420 |

- Per-event inträdesmedel (0,5 s): p50 **495** u/s (p10 437, p90 571, spann 276–622).
- Per-event utträdesmedel (0,5 s): p50 **315** u/s (spann 213–403; innehåller återacceleration).
- Inträde 276–622 u/s mappas allihop till ~300 vid utträdet ⇒ **fartförlust ~145–200 u/s
  för en spelare i transitfart**, återhämtad på ~0,4–0,5 s.
- t1 (n = 2): inträde nästan stillastående (1 resp. 120 u/s) → utträde ~300 (0,5 s-medel
  238/263), därefter retardation — spelarna stannar vid window.

**Landningspunkt (derived):** fast = destination + 27 u i z (uppmätt medel z 76,2 mot
dest-z 48; 70,6 mot 44), spridning 7–18 u = samplingsfördröjning (15–30 ms × 300 u/s).
Warpsteget är alltid en enda sampeldiskontinuitet: 3D-steg 741/1 455 u på 11–90 ms.

### 2. Skickliga spelare använder i praktiken inte telen alls — och när t2 används är det i full fart som betalas med 300-impulsen

**Observerat:**

| | Hela korpusen (3 777 demos, 7 564 sp-tim) | Strikt kohort (3 561 demos, 7 265 sp-tim) |
|---|---|---|
| t1-transits | 2 | 1 |
| t2-transits | 27 | 14 |
| Dödsfall→respawn ur triggerboxarna | 1 452 (t1) / 573 (t2) | — |

- **1 äkta genomfart per ~480 spelartimmar** i strikt kohort (≈ 1 per 60 matcher).
  Spelare dör VID telen 50–70× oftare än någon använder den — triggervolymernas
  p50 = 0 i zonstatistiken är lik och intilliggande campare, inte "stillastående
  materialisering" (korrektion av formuleringen i gate2_zones.md, se Validering).
- t2-användarna går in i **per-event p50 495 u/s** — över tele-sng-in-zonens
  (inloppsschaktets) p95 = 407 och vid dess p99,9 = 494, dvs. maximal transitfart:
  när den väl används är den flykt-/transitverktyg, inte stillastående ompositionering.
  Mönstret är detsamma i båda kohorterna (strikt: pre-p50 485 → post 316; övriga:
  524 → 297).
- **Fotbaslinje** (utan tele, ankomst inom 30 s): t2: n = 287, p10 1,5 s, p50 9,8 s;
  t1: n = 559, p10 2,7 s, p50 13,5 s (medianerna inkluderar strider/omvägar).

**Härlett:** t2 sparar ~1,2–1,4 s netto mot snabbaste uppmätta fotväg efter
återaccelerationsstraffet; t1:s potentiella vinst är större (1 455 u) men används
nästan aldrig (2 händelser på 3 777 demos). Tolkning (Low confidence, ej mätning):
t1 ligger mitt i YA-stridszonen och kastar ut mot en campad yta med fast, förutsägbar
ankomstvektor — risken överväger.

### 3. Utträdena skapar LÅG-fartssampel i inkluderade zoner — inte höghastighetssampel

**Observerat:** landningsvoxlarna (uppslag i `pipeline/out/gate2/voxel_classes.npz`):

- t2-dest (224,−326,76): **INCLUDED_OPEN** (mål 500) — human-p50 där 334.
- t1-dest (1328,539,71): **INCLUDED_CONSTRAINED** zon 6 `constrained-misc` (mål 374,6).

Utträdessampeln ligger i ~0,25 s på påtvingade ~300 u/s och behöver ~0,5 s till
inträdesfart. 300/500 = 0,6 i score-bidrag per tick i t2-utgången — **bias NEDÅT**,
aldrig uppåt. Farhågan "tele-utträden ger legitima höghastighetssampel som förvränger
jämförelsen uppåt" är alltså empiriskt motbevisad; distorsionen är motsatt och drabbar
den agent som råkar nudda telen.

## Validering

- **Känslighet, samplingsluckor:** detektering med dt ≤ 2 000 ms i stället för 200 ms
  ger identiskt antal (2 + 27) — inga transits missas p.g.a. glesa sampel
  (grannskapens dt-p95 = 52 ms).
- **Respawn-förväxling:** warp-mål ur triggerboxarna klustrar på kartans spawnpunkter;
  närmaste spawn till en destination är (192,−208,−176) — 8 u 2D-marginal till
  t2-filtrets gräns men **z-skild med ~250 u** och entydigt utesluten av
  |z−60| ≤ 120-villkoret. Ingen spawn ligger inom något destinationsfilter
  (fullständig spawnlista ur BSP-entiteterna kontrollerad).
- **Kohortblandning:** 13 av 27 t2-eventen kommer ur wipeout/2v2v2v2-CA/FFA-demos som
  ligger felmärkta under `mode=4on4` i storen — därför redovisas strikt kohort separat;
  fartmönstret (in ~500 → ut ~300) är detsamma i båda.
- **Wire mot positionsderivat:** enda QWD-eventets wire-fart (300,0) stämmer med de
  positionsderiverade post-binnarna (p50 302–308) för alla MVD-event.
- **Två korrektioner till gate2-underlaget:**
  1. `gate2_zones.md` skriver "man materialiseras stillastående, p50 = 0" om
     EXCLUDED_TELE — fel förklaring: p50 = 0 kommer från lik och campare intill
     triggern; utträden sker vid destinationerna i exakt 300 u/s.
  2. Zon 28 `tele-sng-out` (bounds 0..96, −480..−384) är felbeskriven som "t2-telens
     utgångsplatta" — den verkliga t2-utgången ligger vid (224,−320,75), 250 u österut,
     i INCLUDED_OPEN-voxlar. Zonens klassning/tak påverkas inte, bara `desc`.
- **Begränsningar:** n = 2 för t1 medger ingen fördelning, men wire-facit + fysikkoden
  (samma `teleport_touch` för båda) gör 300-impulsen High confidence även där.
  Intentionsutsagor (varför t1 undviks) är markerade som tolkning.

## Rekommendation för Gate 2-protokollet (fråga 3)

">250 u-klipp + exkludera tele-triggervoxlar" räcker **nästan**: warpsteget klipps
bevisligen alltid (alla 29 event är ett enda 741/1 455 u-steg), och inloppssidan
behöver inget extra (normala farter i redan inkluderade/exkluderade zoner). Två saker
saknas — utträdesfönstret och ruttmätnings-asymmetrin:

```
TELEPORT-EVENT := sampelsteg med 3D-dist > 250 u VARS landningspunkt ligger
                  inom 64 u 2D av (1328,544) eller (224,-320) och |z-75| <= 32

1. Själva steget räknas inte (täcks redan av >250u-klippet).
2. Exkludera alla tick i [t_event, t_event + 500 ms] ur fartmedlet
   (uppmätt: ~250 ms påtvingad 300-regim + återacceleration; 500 ms täcker
   p50-återhämtningen). Utan detta får en agent som nuddar telen omotiverat
   score-avdrag (300 u/s i mål-500-voxlar), aldrig ett tillskott.
3. Logga TELEPORT-EVENT per körning och rapportera antalet per agent
   (kandidat vs RTX-baseline).
4. Ruttmätningen (Gate 1): körningar som innehåller ett TELEPORT-EVENT på
   ruttsträckan flaggas och medianberäknas separat. Telen är en ~1,2-1,4 s
   nettogenväg (t2) som sim-policyn per konstruktion inte kan ha lärt sig;
   olika telefrekvens mellan agenterna bryter den kausala attributionen av
   tidsdeltat till rörelseskiktet. Väntat antal är ~0 (mänsklig frekvens
   1 per ~480 spelartimmar) - regeln är en billig vakt, inte en förväntad kostnad.
```

Ingen simändring behövs: döda teleportrar i träningsmiljön är förenligt med bevis­-
mätningen ovan, eftersom protokollet gör tele-genomfarter mätneutrala och synliga.

## Reproducerbarhet

- Delextrakt + detektering + profiler kördes som tre ad hoc-duckdb-skript
  (parametrar och predikat i sin helhet under Metod; boxarna, filtren och
  destinationskoordinaterna ovan räcker för exakt återkörning).
- Eventlistan (demo, slot, t_in) för alla 29 transits kan återskapas med
  detekteringspredikatet i Metod §2; exempel: `4on4_dk_vs_uk[dm3]19_tmp1.mvd`
  slot 8 t=895 213; `4on4_hgc_vs_dse[dm3]164_tmp1.mvd` slot 1 t=557 248;
  `d4dac3132de728d5_PAINvsDS.qwd` slot 2 t=3 544 593 (wire-facit-eventet).
- Zonstatistik/klassuppslag: `~/rex-ml/evidence/gate2_zones.json`,
  `~/rex-ml/pipeline/out/gate2/voxel_classes.npz`.
