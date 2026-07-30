# rex-ml — ALLTID-LADDAT MISSIONSANKARE (Grundlag v3: Manifestet, 2026-07-30)

Denna fil återinjiceras automatiskt, även efter autocompact.
Läser du detta efter en kompaktion: **du är mitt i missionen, inte vid en nystart.**

## Resume-ritual (gör FÖRST efter varje kompaktion)
1. Läs `~/rex-ml/PROGRESS.md` — sista posten säger exakt var du är.
2. Läs `~/rex-ml/BRIEF.md` — hela specen (Grundlag v3, faser 0–3).
3. Avgör aktuell fas. Fortsätt den. Fråga inte vad du ska göra.

## Missionen (ägarens manifest 2026-07-30, med ratificerade amendments)
Träna en autonom rörelseagent med **ren djup förstärkningsinlärning (PPO)** — inga rutter,
inga waypoints, ingen navmesh, ingen mänsklig-linje-BC i policyn. Rumsperception (raycast)
+ rekurrent minne + intrinsisk motivation. Den gamla rutt-/A/B-missionen är ARKIVERAD
(`docs/phase-archive/`) och får inte återupptas.

## Terminerande mål — missionen är KLAR när BÅDA gates är passerade MED BEVIS
**Gate 1 — Kinetisk dominans (SKÄRPT av ägaren 2026-07-30 19:35):** uppmätt **peak ≥ 820
UPS** på `100m.bsp` på RIKTIGA mvdsv-servern (bästa körning över ≥30; hela fördelningen
rapporteras). Gamla 800-golvet är ersatt. Tak OMMÄTT i bit-exakta qwsim: analytiskt
optimum 833,4 @77 Hz (8/8 över 820, evidence/strafe_ceiling_qwsim.json) — kravet nåbart.
**SUBMÅL (ägaren 20:00): peak 850** — ÖVER kända analytiska taket; spåras separat,
kräver teknik bortom analytisk styrning (sökning pågår, evidence/ceiling_850_search.*).
**Gate 2 — Spatial dominans:** fritt strövande på dm3 från slumpade startpunkter, ≥30
körningar × 60 s på riktiga servern: medelhastighet > **500 UPS** inom inkluderade zoner
(`evidence/gate2_zones.json` — evidensbaserat härledda; vatten/hiss/tele exkluderade,
geometriskt takade zoner enligt zondokumentets gate-formel), **noll fastnade episoder**.
Bevisregeln (stående, ägarens): en gate/runda rapporteras ALDRIG klar förrän replay-bevisen
är inspelade på riktiga servern, validerade och publicerade i bevisartefakten.
När båda gates håller: skriv `~/rex-ml/REPORT.md` med bevisen, sedan stopp.
REPORT.md:s existens är den ENDA klarsignalen.

## Ratificerad arkitektur (ägarbeslut 2026-07-30 — ändra inte utan nytt ägarbeslut)
- **Miljö:** `sim/` libqwsim — bespoke C++-vektoriserad sim kring mvdsv:s RIKTIGA
  `pmove.c` (bit-exakt, validerad mot QWD usercmds+replay_ticks), pybind11, trådpool,
  GIL-fri batchstegning. INTE EnvPool-ramverket (idén hedras, ramverket skippas).
- **Träning:** Sample Factory (asynkron PPO/APPO) på H100. Endast PPO.
- **Handlingsrum:** kontinuerlig Gaussisk yaw/pitch + diskreta knappar (W/A/D/hopp).
- **Observationer:** raycast mot BSP + kinetiskt tillstånd; LSTM/GRU-minne.
- **Nätstorlek FRI under träning** (ägarbeslut: 0,5 ms/tick-invarianten SLÄPPT under
  träning; destillering/optimering mot tick-budget är en SEPARAT fas EFTER Gate 2).
- **Curriculum:** Gate 1 steg 1–4, Gate 2 steg A–D enligt BRIEF. Intrinsisk motivation:
  voxelnyhet skalad med passagehastighet, kollisionsimpuls-straff, kinetisk multiplikator.
- **Korpusen** (908 M sampel) är utvärderings-/härledningsmaterial (baslinjer, zontak) —
  ALDRIG träningsdata för policyn.

## Stående mandat: operatörsisolering
Arbeta kontinuerligt genom faserna. Ägaren kontaktas ENBART vid: hårdvarukollaps,
jobb som skriver >20 GB, radering/överskrivning av data, eller matematiskt påvisbar
olöslighet inom systemresurserna. Policykollaps, stagnation och katastrofal glömska är
FÖRVÄNTADE fenomen — felsök och justera belöningsvikter/hyperparametrar själv, logga
beslutet i PROGRESS.md. Långa träningar (>4 h) är normen: kör i tmux-fönstret `jobs`
med checkpoints, vänta aldrig blockerande i egen kontext.

## Checkpoint-disciplin (det som gör kompaktion överlevbar)
PROGRESS.md ska alltid räcka för att en färsk kontext ska kunna återuppta ensam.
Skriv efter varje milstolpe: vad gjordes, vad MÄTTES (siffror, inte adjektiv), vad är
nästa, vilka antaganden du själv beslutade. Skriv INNAN långa jobb startar, inte efter.

## Skyddsräcken
- Disk är enda knappa resursen (~168 GB fritt). Ange kostnad före jobb som skriver >5 GB.
- Korpora är oersättliga och skrivskyddade. `rm`/`rmdir`/`shred`/`dd`/`git clean` NEKAS.
- `vendor/` modifieras aldrig — extrahera genom att kopiera ut.
- Mätningar, aldrig påståenden. "Klart" kräver bevis, inspelade på riktiga servern.
- Allt arbete pushas till https://github.com/Xerialen/rex-ml (main).
