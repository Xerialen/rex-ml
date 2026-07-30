# DM3-korpus: räcker rutterna, eller behöver du spela in fler demos?

Datum: 2026-07-30. Metod: samma-liv-körningar A→B ur `store-dm3` (item taget → första
globala tagningen av målet, samma slot, dt ≤ 15 s, målet aktivt vid start, ingen respawn
emellan — exakt route-labs cohort-SQL-semantik, generaliserad). Vet = pipelinens egen
`vet()` i `pipeline/human_paths.py` med oförändrade trösklar: ≥12 samples/s, max
sample-lucka 220 u ("gap" = teleporter/inspelningslucka), max stigning 95 u per 0,5 s
("rocket_jump"). Bedömning: **tillräcklig** ≥15 vettade körningar, **tunn** 3–14,
**saknas** <3. Alla siffror är mätta, inte uppskattade. Full matris (179 riktade par)
i `corpus_sufficiency.json`.

## Träningsrutterna (gate-filtrerade, ur pipeline/out/paths)

| rutt | kandidater i gate | överlever vet | envelope-band (p95) | bedömning | behövs inspelning? |
|---|---|---|---|---|---|
| window → RL | 636 | 24 (tak 24) | 40,2 u | tillräcklig | nej |
| ralow → RA-topp | 1302 | 24 (tak 24) | 47,8 u | tillräcklig | nej |
| lifts → SNG-mega | 2500 | 24 (tak 24) | 23,6 u | tillräcklig | nej |
| quad → RA-topp | 669 | 24 (tak 24) | (band ej beräknat) | tillräcklig | nej — men ägar-referensdemo saknas, se nedan |
| ring → RA-topp | 493 | 24 (tak 24) | 84,3 u | tillräcklig | nej |
| sngspawn → mega | 388 | 24 (tak 24) | 51,2 u | tillräcklig | nej |
| tunnel → RA | 106 | **8** (98 avvisade som rocket_jump) | **110,7 u — bredast av alla** | **tunn** | **ja, gärna 2–3 st** |
| sngspawn → quad | 59 | **0** (59/59 "gap" = teleportern) | — | **saknas** | ja, om trickhoppet undviker telen (separat agent utreder rutten) |

## Övriga granskade par (rå = samma-liv-körningar ≤15 s; vet på de snabbaste, max 120)

| rutt | korpuskörningar (rå) | överlever vet | snabbast vettad | bedömning | behövs inspelning? |
|---|---|---|---|---|---|
| **YA → RA-topp** | 50 | **0** (49 gap/tele, 1 rocket_jump) | — | **saknas** | **JA — bekräftat: noll movement-only-körningar finns** |
| RL → RA-topp | 11 | **0** (9 rocket_jump, 2 gap) | — | **saknas** | ja/nja — korpusen antyder att snabba linjen kräver raketjump; kolla först om movement-only-linje alls finns (dina `rl_to_ratop`-demos: är de RJ?) |
| SSG → RA-topp | 52 | 4 (37 rocket_jump, 11 gap) | 10,46 s | tunn | ja, några st (demo `ssg-to-ratop.qwd` finns) |
| SNG → quad | 8 | 4 (4 gap) | 5,27 s | tunn | ja, några st (demo `sng-to-quad.qwd` finns) |
| ring → RL | 14 | 11 (1 gap, 2 rocket_jump) | 6,97 s | tunn | gärna (demo `ring-to-rl.qwd` finns) |
| LG → pent | 3 | (ej vettad, rå <3) | — | **saknas** | dina `lg-to-pent-*`-demos är i praktiken enda källan (pent uppe sällan i 4on4) |
| YA → RL (utan tele) | 834 | 61 (767 gap/tele, 6 rocket_jump) | 4,26 s | tillräcklig | nej |
| YA → RL (via tele) | (samma 834) | 0 — telen ger alltid "gap" | — | ej extraherbar ur korpus | din `ya-to-tele-to-window-to-rl.qwd` är enda geometrikällan |
| quad → SNG | 521 | 118 av 120 testade | 4,21 s | tillräcklig | nej |
| RA-topp → SSG | 470 | 120 av 120 testade | 5,38 s | tillräcklig | nej |
| YA → SSG | 5837 | 120 av 120 testade | 1,36 s | tillräcklig | nej |

Ej mätbara som item-par (start är spawn/plats, inte item-pickup): `highbridge-to-rl`,
`spawn-lift-to-pent`, `(spawn)rarox-to-quad`, `(spawn)ra-tunnel-to-lg`,
`rj-pent-to-lifts-to-window-to-quad` (RJ-rutt, utanför movement-policyn per design).
Dina demos är där den primära källan.

## Önskade demos (prioritetsordning)

1. **YA → RA-topp, movement-only, med sngspawn→quad-trickhoppet speglat** — BEKRÄFTAT
   SAKNAS: 50 korpuskandidater, 0 överlever vet (49 tele-gap, 1 raketjump). Närmast
   liggande demo (`ya-to-tele-to-window-to-rl.qwd`) går åt fel håll efter telen.
   Spela in.
2. **tunnel → RA** — bara 8 vettade körningar, bredaste envelope-bandet (110,7 u mot
   window:s 40,2 u från 24 körningar). 2–3 demos stramar åt bandet direkt.
3. **sngspawn → quad utan teleporter** — korpusen kan aldrig leverera geometrin
   (teleportern syns som gap i alla 59). En demo med trickhoppet är enda vägen,
   om hoppet undviker telen. (Separat utredning pågår om själva rutten.)
4. **RL → RA-topp movement-only** — 0 av 11 överlever (9 RJ). Om en movement-only-linje
   finns: spela in. Om inte: markera rutten som RJ-beroende och utanför scope.
5. **SSG → RA-topp** och **SNG → quad** — tunna (4 vettade vardera); ett par demos per
   rutt räcker.
6. **quad → RA(-topp): INGEN inspelning behövs för korpusen** — 669 kandidater i gaten,
   24 vettade banor, snabbast 6,71 s. Det enda som saknas är din egen referenstid
   (ingen `quad-to-ra`-demo finns i `demos/dm3-drillar/`), vilket bara spelar roll om
   du vill ha en egen ägartid som gate — träningen är täckt.
