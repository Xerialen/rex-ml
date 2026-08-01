# rex-ml — lägesbrief för en LLM-kollega

Skriven 2026-08-01 ~17:30 EEST av den opererande agenten. Målgrupp: en LLM som ska
förstå eller ta över arbetet. Läsordning vid övertagande: `CLAUDE.md` (grundlag) →
`PROGRESS.md` sista posterna (exakt läge) → `BRIEF.md` (fullständig spec) → denna.
Allt nedan är uppmätt, inte uppskattat, om inget annat sägs.

## Missionen i en mening

Träna en autonom rörelseagent för QuakeWorld med **ren djup-RL (PPO/APPO)** — inga
rutter, waypoints, navmesh eller mänsklig BC i policyn — tills den passerar två
ägarsatta, medvetet övermänskliga gates **med replay-bevis på riktig mvdsv-server**.
`REPORT.md`:s existens är den enda klarsignalen; den finns inte än.

## Tidslinje (hur länge vi jobbat)

- **Före 2026-07-30:** en tidigare mission (rutt-/A-B-jämförelser) byggde grunden:
  korpusextraktion (908 M trajectory-sampel mänskligt 4on4-dm3-spel, duckdb/parquet i
  `~/dm3-extract/store-dm3`), verktyg (route-lab, testsuite, mvd_analyzer). Den
  missionen är ARKIVERAD (`docs/phase-archive/`) och får inte återupptas.
- **2026-07-30:** ägarens manifest (Grundlag v3) ratificerades — ren RL, två gates.
  `sim/` libqwsim byggdes: mvdsv:s riktiga `pmove.c` extraherad till en bit-exakt
  C++-vektoriserad sim (validerad mot QWD usercmds + replay_ticks; obs-paritet mot
  servern 5.4e-7), pybind11, GIL-fri batchstegning, 16.55 M steg/s på maskinen.
- **2026-07-30→31: Gate 1 (kinetisk dominans, 100m.bsp) KLAR OCH SERVERBEVISAD.**
  Krav: peak ≥820 UPS på riktiga servern, bästa av ≥30 körningar. Uppmätt: **984.0**
  (30/30 inspelade; även ägarens skärpta delmål 850 passerat). Analytiskt strafe-tak
  i sim: 833.4 @ 77 Hz — policyn ligger på/över taket via serverdynamik.
- **2026-07-31→08-01 (pågår): Gate 2 (spatial dominans, dm3).** Detaljer nedan.
  Träningsvolym hittills i fas 2: ~3.6 G env-frames ≈ **~13 000 timmar simulerad
  dm3-tid** — mer än hela den mänskliga korpusens speltid, intränad på ~1,5 dygn
  väggklocka tack vare ~50 k FPS på 48 workers + H100.

Kalendertid under Grundlag v3: **~2 dygn**, i praktiken kontinuerlig autonom drift
med ägarinteraktion i skurar (operatörsisolering: ägaren kontaktas bara vid
hårdvarukollaps, >20 GB-skrivningar, dataradering eller bevisad olöslighet).

## Gate 2 — kraven och exakt var vi står

Mätformeln (`rl/zones.py`, härledd ur korpus + BSP, `evidence/gate2_zones.*`):
32u-voxelraster; OPEN-mål 500 UPS; CONSTRAINED-mål 0.8×mänsklig p99.9 per voxel;
vatten/hiss/tele/lowdata räknas inte. PASS ⇔ poolat OPEN-tickmedel >500 ∧
zonkvotsmedel ≥1.0 ∧ ≥70 % union av NÅBARA OPEN-voxlar (12 012 st; nåbar = ≤3
voxelnivåer över golv) över ≥30×60 s ∧ noll fastnade (>2 s <50 UPS) — allt på
riktiga servern med publicerade replays (bevisregeln).

**Senaste n=30 i sim (3.1 G frames, 2026-08-01 15:02):**

| Mått | Krav | Uppmätt | Trend |
|---|---|---|---|
| OPEN-medelfart | >500 | **628.9** | ✓, serie 684→536→629 |
| Täckningsunion | ≥70 % | **28.0 %** | ↑, serie 19.9→21.4→28.0 (+6.6 pp/500M senast) |
| Fastnade | 0 | **0/30** | ✓ stabilt |
| Zon-score | ≥1.0 | **1.26** | ✓ |

Kontext: mänskligt allmaximum för 60 s-OPEN-medel är 464.8 (0 av 7.4 M mänskliga
fönster >500); mänsklig 30-fönster-union är 40.0 % ± 1.4 ⇒ 70 %-kravet är ~21 SD
övermänskligt men nåbart (korpusens totalunion 87.6 %). Boten är alltså redan
övermänsklig i fart och ~halvvägs till mänsklig totaltäckning; **täckningen är enda
återstående sim-kriteriet för de ursprungliga måtten.**

**Gate-hoppens mognadsstege (ägaramendment 2026-08-01, BRIEF §2):** sex kritiska
trickhopp ska nå nivå 3 (≥5 försök, **≥90 %** lyckade — ägarsatt tröskel) i sim
FÖRE MVD-tester: ring↔quad ×4 över hexagonens NV/SO-ledger utan att ramla i
MH-gropen, RA-tagningen (klättring till 256,-704,304), SNG-mega (-720,80,160).
**Analyst-granskad status: nivå 0 på samtliga sex.** Kärnfynd: policyn spelar
aldrig på plattformstopparna (0 s på ringens nivå av 30 min; cirklar i gropen
under). Detektor: `rl/jump_gates.py`, godkänd som instrument efter två
underkännande-rundor (se Arbetssätt). Rjump pent→window: uppskjuten (kräver V3).

## Hur vi tränar (arkitektur + belöningstrappa)

- Sample Factory 2.1.1 APPO, 48 workers × 8 envs, batch 4096, H100, ~50 k FPS.
  LSTM-minne; obs = raycast mot BSP + kinetik; handlingar = kontinuerlig Gaussisk
  yaw/pitch + diskreta knappar. 15 workers kör 100m-korridorrepetition (bevarar
  Gate 1-extremfartsregistret). Venv-patchar dokumenterade i `sim/STACK.md`;
  träning körs med SF_STDDEV_MAX=1.0; evals är greedy.
- Belöning (`rl/rewards_gate2.py`): fartgradient (linjär→exp över 320), massivt
  kollisionsimpulsstraff, voxelnovelty 1.5/voxel fartskalad per episod (betalas
  endast i räknade zoner — "dykfixen"), **V1b cellsällsynthet** (novelty ×0.5–4.0
  efter botens egen 256u-cellhistorik, EMA över episoder — självrefererande, ingen
  korpusdata i rewarden), **V1a klätterbonus** (0.08/u vid landning rise≥24) och
  **V2 gapbonus** (span≥150 ∧ golvdjup>56 via 3-punkts raycast, ×2 vid djup>141 —
  korpuskalibrerade trösklar). Alla vikter är CLI-flaggor (PBT-förberedelse; PBT
  får INTE aktiveras utan explicit ägarbeslut). V3 = raketsim för rjumps, sist.
- Effektkedjan är mätt: sällsynthetsviktningen bröt täckningsplatån ~12 % →
  gårdscirkuiter (ring/quad/mega ~50 % av tiden, 716–750 UPS), window-camping
  16.5→3.3 %, SNG-enrumsfällan 4/10→0-2/10, första äkta gap-hoppen (0→5/dump).

## Arbetssätt som håller (lärdomar med ärr)

1. **Bevisregeln + analystveto:** inga hopp-claims till ägaren utan att
   dm3-analysten (subagent, `analyst.md`/`.claude/agents/dm3-analyst.md`; kör
   general-purpose med analyst.md-preamble om agenttypen saknas i sessionen)
   verifierat dem. Vetot fällde v1-detektorn (korridorpassager räknades som
   hoppförsök) OCH v2:s enda kvarvarande RA-försök (klättring åt fel håll).
   Detektorer kalibreras mot mänsklig ground truth (4 000 RA-pickups, tusentals
   ledge-hopp).
2. **Policykollaps är normalt:** två belöningsklippor (5290→41, 3073→109) hanterades
   med SF:s `best_*.pth`-återställning + karantänflytt (mv, aldrig rm) + omstart;
   stabilisator entropi 0.01→0.003 höll (inga klippor på >2 G frames sedan dess).
   `--keep_checkpoints=8` — rotationen åt upp friska checkpoints två gånger.
3. **Mätning före åtgärd, en variabel i taget, triggrar i förväg journalförda** i
   `PROGRESS.md` (checkpoint-disciplinen är det som gör kontextkompaktion
   överlevbar — skriv INNAN långa jobb, siffror inte adjektiv, date-verifierade
   tidsstämplar). Allt pushas: `git push origin master:main` (lokal branch heter
   master; repot är github.com/Xerialen/rex-ml).
4. **Drift:** träning i tmux `rexml:jobs`; monitor-task tailar
   `pipeline/out/rl/train_dir/gate2_v2/console.log` med 30-min-hjärtslag +
   krasch/stillastånds-larm. Evals/dumpar körs på CPU i bakgrund (kostar ~20 %
   tränings-FPS, accepterat). Korpora är skrivskyddade och oersättliga; rm/dd/
   git clean NEKAS; `vendor/` röres aldrig; disk ~168 GB fri är enda knappa resursen.
5. **Rapportformat till ägaren (stående direktiv, se memory):** geografi med
   zonnamn (ägaren kan kartan), gate-hoppens nivåer + n=30-måtten i varje
   uppdatering, och 3D-artefakten uppdaterad (tools/rex3d/; artefakt-URL
   c32e9f16-…; metrics-historik `evidence/gate_metrics_history.json` driver
   trendpilarna, `evidence/jump_gates_latest.json` hoppanelen).

## Öppna frontlinjer (i prioritetsordning)

1. **Täckning 28→70 %:** takt +6.6 pp/500M senast (accelererande efter
   SNG-fällebrottet). Största återstående massor (analystrankade): östra
   YA-komplexet 14.7 % av universum (bästa skörd 10.6 vox/s), pent-sänkan 14.6 %,
   RA-låg/NG 7.9 %. Trösklar: <+3 pp/500M ⇒ PBT-fråga till ägaren och/eller
   `--qw_rarity_lo 0.25`; fart <500 ⇒ rebalansera fart/novelty.
2. **Gate-hopp 0→3:** kräver plattformstoppspel som inte uppstått organiskt.
   Kandidater (journalförda, ej beslutade): spawn-bias mot plattformarna
   (curriculum-verktyg, ratificerat), riktad rarity mot toppnivåvoxlar.
3. **Serverbevis:** när sim-kriterierna håller — dm3-variant av
   `rl/run_gate1_evidence.sh`, ≥30 körningar, MVD-inspelningar, evidenssida,
   tele-regeln ur `evidence/tele_speed_analysis.md`. Sim saknar entities
   (ren pmove) — tele/hiss-beteende skiljer sig på servern; PolicyDrive är
   kartagnostisk och obs-paritet är bevisad, men serverkörningarna är sanningen.
4. **V3 raketsim** (rjump pent→window m.fl.): extrahera knockback ur mvdsv,
   validera bit-exakt mot QWD-rjumpsampel, +attack i handlingsrummet.
5. **Skulder:** rex-ml-rtx-push blockerad på PAT-scope; zon-28-mislabel i
   gate2_zones.json; bothost msec-trunkering (12 vs 13); fas 3-destillering till
   0.5 ms/tick efter gates.

## Nyckelfiler

`CLAUDE.md` grundlag · `BRIEF.md` spec/gates · `PROGRESS.md` journal (sanningen om
läget) · `rl/` miljö+belöningar+eval+detektorer · `sim/` libqwsim · `evidence/`
alla mätartefakter + analystrapporter (`analyst_review_vertical_rewards.md`,
`analyst_sng_coverage.md`, `analyst_jumpgate_review.md`) · `tools/rex3d/`
artefaktbygget · `evidence/repro/` analystens verifieringsscript ·
träningskommandot: se PROGRESS-posten 2026-08-01 03:58 (+ viktflaggor 10:02).
