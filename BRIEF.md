# BRIEF — Grundlag v3: Manifestet för Kognitiv Acceleration (2026-07-30)

Källa: ägarens manifest (arkiverad kopia: `docs/phase-archive/MANIFEST-2026-07-30.md`),
modifierad av fyra ratificerade ägarbeslut från invändningsrundan 2026-07-30.
Ersätter Grundlag v2 (rutt-/A/B-missionen, arkiverad i `docs/phase-archive/`).

## 0. Ratificerade amendments (invändningsrundan)

| # | Fråga | Ägarens utslag |
|---|-------|----------------|
| 1 | Träningsmiljö | **Bespoke pmove-sim**: pybind11 + C++-trådpool kring riktiga `pmove.c`/`pmovetst.c`, bit-exakt, validerad mot QWD usercmds+replay_ticks. Sample Factory behålls som träningsramverk. EnvPool-ramverket skippas (en-nods-maskin, 64 kärnor — inte klustret manifestet antog). |
| 2 | Gate 2-zoner | **Jag härleder zonerna själv** ur BSP, korpus, bilder/demos/locs — evidensbaserat. Leverans: `evidence/gate2_zones.json` + `.md` med gate-formel. |
| 3 | Tick-budget | **0,5 ms/tick SLÄPPT under träning.** Stora nät tillåtna i forskningsfasen; destillering/optimering mot serverbudgeten är en separat fas EFTER Gate 2. |
| 4 | Grundlag | **CLAUDE.md/BRIEF.md omskrivna nu**; gamla missionen parkerad i `docs/phase-archive/`, inget raderat. |

Oförändrat överlevande regler: bevisregeln (replay på riktiga servern före rapport),
korpusskydd, disk-disciplin, PROGRESS.md-checkpointing, GitHub-push av allt.

## 1. Missionen

Träna en autonom rörelseagent för QuakeWorld med ren DRL (PPO). Förbjudet i policyn:
fördefinierade rutter, waypoints, navmesh, mänsklig-linje-BC. Tillåtet: rumsperception
(raycast/djup), rekurrent minne, intrinsisk motivation, curriculum. Korpusen används
enbart för utvärdering och härledning (baslinjer, zontak, valideringsdata för simmen).

**Varför pivoten är rätt även enligt våra egna mätningar:** race_v9:s strikta prov gav 0/8
med diagnosen geometri-överanpassning — policyn följde tränade linjer, inte rummet.
Manifestets tes (ruttföljning är en kognitiv tvångströja) är samma slutsats.

## 2. Gates (terminerande mål)

### Gate 1 — Kinetisk dominans (100m.bsp) — SKÄRPT 2026-07-30 19:35
- **SUBMÅL (ägaren 2026-07-30 20:00): peak 850.** Ligger ÖVER bästa kända analytiska
  spel (uppmätt tak 833,4 @77 Hz / 842,9 @83 Hz, evidence/strafe_ceiling_qwsim.json) —
  dvs kräver teknik BORTOM den analytiska styrningen (~535 felfria luftticks + bättre
  uppskjut än cirkelfasens ~491 inom korridorlängden). Inte bevisat omöjligt (analytiska
  är undre gräns för optimum); spåras och rapporteras separat från 820-kravet.
- **Krav (ägarens ord):** "peaken ska vara 820 på 100m.bsp" ⇒ uppmätt peak ≥ **820 UPS**
  på riktiga mvdsv-servern, bästa körning över ≥30; hela fördelningen rapporteras.
  Tolkning loggad: bästa-körning-peak (medianpeak ≥820 vore fysiskt odefinierat mot
  taket); ägaren korrigerar om annan tolkning avses.
- **Takfråga ÖPPEN:** gamla 821,4 (`evidence/strafe_ceiling_100m.json`) mättes i rex_env
  med dt=1/77. Ommätning i bit-exakta qwsim (msec=13) pågår — ligger sanna taket under
  820 är gaten omöjlig och det är en arkitekturinvaliderande mätning (stoppvillkor 3).
- **Bevis:** inspelade demos + hastighetskurvor i bevisartefakten, före rapport.
- Referens: race_v5 (gamla arkitekturen) nådde 472 UPS; bryggans smoke 327,6 bevisade
  ENDAST sluten loop (ägaren: "320 är ingenting" — korrekt, fart bevisas av policyn).

### Gate 2 — Spatial dominans (dm3, ingen navmesh)
- **Krav:** fritt strövande från slumpade startpunkter/riktningar, ≥30 körningar × 60 s
  på riktiga servern, med den **evidensbaserade gate-formeln** (härledd 2026-07-30 ur
  898,9 M korpussampel + BSP, se `evidence/gate2_zones.md`; zonhärledningen var
  delegerad till agenten av ägaren):
  - T(v) = 500 u/s i INCLUDED_OPEN (75,4 % av volymen, 82,3 % av trafiken);
    T(v) = 0,8 × mänsklig p99,9 i INCLUDED_CONSTRAINED (39 namngivna takade zoner,
    tak 345–497 ⇒ mål 276–399); EXCLUDED_WATER/LIFT/TELE + LOWDATA räknas inte.
  - **PASS ⇔ medel[v_h/T(v)] ≥ 1,0 OCH medel(v_h | OPEN) > 500 OCH ≥70 % av
    OPEN-voxlarna besökta** (anti-loop: en bunny-slinga får inte maxa medlet).
  - **noll fastnade episoder** (>2 s under 50 UPS utanför EXCLUDED-zon), och ingen
    rutt-, waypoint- eller navmesh-information i policyns input.
- **AMENDMENT (ägarbeslut 2026-08-01 ~16:00) — gate-hoppens mognadsstege.** Botten ska
  KUNNA de kritiska trickhoppen i sim INNAN MVD-tester påbörjas. Mognadsnivåer per hopp:
  0 inga försök; 1 försöker (uppvisad medvetenhet om hoppet som genväg); 2 lyckas ibland;
  3 ≥5 försök med **≥90 % framgång** (tröskeln satt av ägaren 2026-08-01 ~17:05; ersätter
  ursprungliga 100 % efter analystens mätning: eliten når 8-44 % genom samma detektor).
  **Krav för MVD-övergång: nivå 3 på samtliga:**
  - ring↔quad över hexagonens BÅDA sidoledger — 4 hopp (NV/SO × båda riktningar),
    utan att ramla ner i MH-gropen,
  - RA-tagningen (uppklättring till item_armorInv),
  - SNG-mega (hoppnavigering fram till megan).
  Rjump pent/lift→window: UPPSKJUTEN av ägaren (kräver V3/raketsim); övriga hopp
  ej gate-kritiska. Mätning: `rl/jump_gates.py` på trajektoriedumpar; varje
  lägesuppdatering ska inkludera dessa metrics + befintliga gate-mått, och
  3D-artefakten ska hållas uppdaterad med metrics/targets + trendindikatorer.
- Platt "500 överallt utom vatten/hiss/tele" FÖRKASTAD med mätstöd: 6,6 % av trafiken
  är torra zoner med mänskligt tak under 500 — en platt gate lär agenten UNDVIKA dem.
- **Bevis:** inspelade fri-strövnings-demos + per-zon-hastighetsstatistik i artefakten.

När båda gates håller med bevis: skriv `REPORT.md`. Dess existens = klarsignalen.

## 3. Arkitektur

### 3.1 Miljö: `sim/` libqwsim
- Extraherad `pmove.c` + `pmovetst.c` + `cmodel.c` (BSP-hull-tracing) ur `vendor/mvdsv-src`
  — fysiken byte-identisk, varje avvikelse loggad i `sim/EXTRACTION-NOTES.md`.
- N oberoende spelarslots, batchsteg i C++-trådpool (OpenMP), pybind11-modul `qwsim`
  med numpy-I/O, GIL släppt. Statisk värld (hissar är server-entiteter utanför pmove —
  acceptabelt, hisschakt är exkluderade zoner).
- Movevars låsta till riktiga serverns värden (testsuite-konfigen), dt = 1/77.
- **Bit-exakthetsvalidering:** QWD-delmängden i storen har usercmds (29,9 M) +
  replay_ticks — inspelade inputs spelas genom simmen, position/vel jämförs per tick.
  Legitima divergenspunkter (hiss, tele, vattenhopp, knockback) klipps och redovisas.
  Resultat: `evidence/libqwsim_bitexact.json`. Simmen är inte godkänd förrän felet är
  på flyttalsbrusnivå på klippta segment.
- Throughput mäts (`evidence/libqwsim_throughput.json`) — milstolpe 0 är en SIFFRA.

### 3.2 Träning: Sample Factory (APPO)
- Asynkron PPO på H100; miljöer på CPU-trådpoolen, nätet på GPU. Endast PPO.
- Klipp-surrogat med ε≈0,2 initialt, entropibonus mot lokala optima, γ högt (långa
  momentum-uppbyggnader), lr-schema över träningen. Hyperparametrar justeras autonomt
  vid stagnation/kollaps — loggas i PROGRESS.md, ägaren tillfrågas inte.

### 3.3 Nät
- Handlingsrum: Gaussisk kontinuerlig Δyaw (+Δpitch) med lärd std + diskreta knappar
  (framåt, vänster, höger, hopp) — fristående W-hantering (QW-bunny släpper W).
- Observationer: raycast-fält mot BSP (typ Lidar; antal/mönster bestäms empiriskt i
  fas 0-smoke) + kinetiskt tillstånd (vel, onground, jump-fas). Inga pixlar/texturer.
- Temporal kärna: LSTM/GRU. Nätstorlek fri under träning (amendment 3).

### 3.4 Belöningar (Gate 2)
- Kinetisk multiplikator: skalar med hastighet linjerad bort från närliggande hinder.
- Kollisionsimpuls-straff: massivt negativt för ofrivilliga hastighetsförluster.
- Global topologisk nyfikenhet: voxelraster (endast i belöningskalkylatorn, dolt för
  agenten); engångsbonus per ny voxel, proportionell mot passagehastigheten.
  Voxelrastret återanvänder fas 0-zonarbetets format (`pipeline/out/gate2/`).

## 4. Curriculum

**Gate 1:** (1) framdrivning → konvergens ~310 UPS; (2) momentumbevarande — frikton
straffas/lufttid belönas, hopprytm; (3) vektoracceleration — exponentiell belöning
>320 UPS, circle jump; (4) half-beat-strafe — väggstraff tvingar alternering, mål 800.
**Gate 2:** (A) öppen-rums-dominans (atrium, luft-strafe utan kollision);
(B) korridorer/hörn i höghastighet; (C) vertikalitet — trappor/drop utan inbromsning;
(D) global frigörelse — slumpade starter över hela dm3, medel >500 UPS i inkluderade zoner.
Fasväxling är automatisk på konvergenskriterier (skriptad i träningsövervakningen),
kriterierna loggas i PROGRESS.md när de fastställs.

## 5. Faser och milstolpar

- **Fas 0 — Fundament (pågår):** grundlag omskriven ✓; Gate 2-zonhärledning (agent);
  libqwsim byggd + bit-exakt + throughput-mätt (agent); Sample Factory-stack verifierad
  (agent); därefter: env-adapter (qwsim ↔ Sample Factory), obs/action-space-smoke.
- **Fas 1 — Gate 1:** curriculum 1–4 på 100m.bsp; kontinuerlig mätning; gate-bevis på
  riktiga servern (testsuite/route-lab-verktygen återanvänds för inspelning).
- **Fas 2 — Gate 2:** curriculum A–D på dm3; zonbaserad gate; fri-strövnings-bevis.
- **Fas 3 — Efterfas (utanför gates):** destillering/optimering mot 0,5 ms/tick-budgeten
  för skeppning i servern; mäts då, inte under träning.

## 6. Drift

- Långa träningar i tmux `jobs`, checkpointade; PROGRESS.md skrivs FÖRE start.
- Disk: ange kostnad före >5 GB-skrivningar; on-policy PPO behöver ingen stor buffer.
- Ägaren kontaktas endast per operatörsisoleringsregeln (CLAUDE.md).
- Allt pushas till https://github.com/Xerialen/rex-ml.
