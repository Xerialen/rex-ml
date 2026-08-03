# Omverifiering av skeptikerfixarna — kantavstamps-spawnern (wf_5769fa30-a6d-15 @ 936d264)

**Datum:** 2026-08-03. **Granskare:** belöningshack-skeptikern (runda 2, adversariell).
**Underlag:** `git -C .claude/worktrees/wf_5769fa30-a6d-15 diff master`, testsviten omkörd,
egna röktester mot RIKTIGA qwsim/dm3 (probskript i sessionens scratchpad:
`probe_exploits.py`, `probe_origin.py` + två inline-farmprober). Ingen kod ändrad.

## VERDICT: UNDERKÄND

Gropdyk-jackpotten är stängd (verifierat), men **platthopps-farmen — original-
skeptikerns fynd 3 — är INTE fixad, bara dess NV-symptom borttaget.** Mekanismen
(gapdjup mätt från spelarORIGO i stället för fotnivå) betalar gapbonus för VARJE
platt hopp med span ≥ 150 var som helst på dm3:s golv, är uppmätt på riktiga
qwsim från alla 4 kvarvarande SO-states i nästan alla riktningar (261/261
bonusutbetalande fan-prober var icke-korsningar), och blir i takeoff-envs — där
fix 3 avsiktligt nollat noveltyn — den dominanta jämvikten. Policyn behöver
aldrig korsa gropen.

---

## 1. Fixpåståendena mot koden (alla 8 verifierade i KOD, inte rapport)

| # | Påstående | Kodverifikat | Status |
|---|---|---|---|
| 1 | Gapbonus kräver hoppknapp+vz>0 på avstampsticken OCH rise ≥ −24 | `env_gate2.py:344` (`jumped = bool(jb) and vel[2]>0`), `:255-269` (segment öppnas endast `counted and jumped`), `rewards_gate2.py:81,90-98` (`GAP_MAX_DROP=24`, `gap_qualifies`) | ✅ implementerat; röktest riktiga qwsim: walkoff mot gropen ⇒ `landing()` aldrig anropad, n_gap 0; gropdyk MED hopp (rise −272) ⇒ bonus 0 |
| 2 | qr-NV/qr-NV-b/rq-NV/rq-NV-b borttagna, 4 SO-states kvar | `rl/data/gate_takeoff_states.json` (4 states, alla SO), test `test_takeoff_states_lie_on_ledge_mask_...` låser antal+sida+mask+sikt | ✅; egen kordmätning rq-SO→landning: golvyta −199,5/−201,7/−224,0 vid 0.3/0.5/0.7 ⇒ SO-kordan är äkta gropexponerad |
| 3 | Takeoff-envs får VoxelNovelty(0.0) | `env_gate2.py:107-109` + test | ✅ (men se §2: nollningen gör platthopps-farmen till ENDA formbara inkomsten) |
| 4 | n_gap räknar bara kvalificerade hopp | `env_gate2.py:305-306` via `gap_qualifies` | ⚠️ implementerat som påstått, men "kvalificerad" inkluderar platta hopp (§2) — mätförgiftningen KVARSTÅR: n_gap++ per rimhopp i mina prober |
| 5 | Friktionskomp ÷0.948, levererat band = konfigurerat | `env_gate2.py:236-241` (`/(1−4·TICK_DT)`, TICK_DT 0.013) | ✅ uppmätt 60 resets riktiga qwsim: 252,5–389,8 mot konfigurerat 250–390; alla 60 grundade på ledgen |
| 6 | NaN-vakt anneal_ref | `rewards_gate2.py:131` (`max(0.0, float(ref))`) + test | ✅ |
| 7 | _spawn_speed nollas vid settlingfiasko | `env_gate2.py:222-226` (for-else) + test | ✅ |
| 8 | rarity.note() endast djupa gap (>141) | `env_gate2.py:309-311` | ✅ — med bieffekten att platthopps-farmen (grund) ALDRIG noteras ⇒ anneal-immun även med `--qw_gap_anneal` |

**Testsvit:** 61 passed in 1.45 s (`PYTHONPATH=worktree:repo .venv-sf pytest rl/tests/ -q`).
**Bitkompatibilitet:** defaults av (takeoff_workers 0, gap_anneal False, deep_anneal 1.0);
övriga spawn-grenar returnerar 3-tupler med speed=None utan extra RNG-konsumtion. ✅

## 2. FÄLLANDE EXPLOAT: platthopps-farmen (origo-offset-hålet)

**Rotorsak, uppmätt på riktiga qwsim/dm3 (`probe_origin.py`):**

- Spelarorigo står **24,0 u över golvytan** (stående på qr-SO-ledgen: pos z=56,0,
  trace rakt ned = 24,0; golvyta z=32).
- Gapdjupet i `_air_segment` mäts med trace från ORIGO i luftbufferten. Ett helt
  PLATT hopp över plant golv når origoapex ≈ golv + 24 + 45,6 ⇒ **uppmätt
  max_depth = 67,8 u > GAP_MIN_DEPTH 56** — trots noll verkligt gap.
- Kalibreringskommentaren i `rewards_gate2.py` ("platt bunnyhopp når apex ~44 u ⇒
  golvdjup>56 utesluter alla platta hopp") räknar fotapex och missar origo-offseten.
  Tröskeln 56 utesluter i verkligheten INGENTING.

**Konsekvens (fan-probe `probe_exploits.py`, 4 states × yaw-offset −85..+85 × fart
250/320/390, riktiga qwsim):** **261 bonusutbetalningar, varav 261 icke-korsningar.**
Samtliga med rise −3,3, depth 67,6, bonus 3,03–5,07 — landning på ledge-/rumsnivå
z=56, inklusive riktningar RAKT BORT från gropen. Kraven i fix 1 biter inte:
hoppknapp trycks (äkta hopp), rise −3,3 ≥ −24, span 151–254 ≥ 150. n_gap++ varje
gång. Grunt djup ⇒ `note()` aldrig ⇒ annealen (även påslagen) rör aldrig farmen.

**Inkomstkalkyl (uppmätt + Fas 1-belagd förmåga):**

| Strategi | Per händelse | Cykel | Takt | Groprisk |
|---|---|---|---|---|
| Platthopp @250/320/390 (uppmätt) | 3,25 / 4,16 / 5,07 | flygtid 50 tick (0,65 s) + 1–2 marktick | **~5–7,5/s** vid kedjad bhop | **noll** |
| Dito, min 40-raders dumskript (väggar, ingen luftstrafe) | 3,65–4,19 | 1 hopp per ~3 s | 1,2–1,7/s | noll |
| Äkta korsning, perfekt policy | djuparc ≈ 3×(253/150)×2 ≈ 10,1 | ≥1,3–2 s + anlopp | ~5–7/s | full |
| Äkta korsning, NUVARANDE policy (Fas 1: 1/4 lyckas) | 10,1 × 0,25 | per försök ~3 s | **~0,2–0,8/s** | full |

Kedjeförmågan är inte hypotetisk: Fas 1 mäter policyns luftstrafe till 132–226
deg/s (1,7–2,9°/tick) och "obruten bhop-kedja" i 5/5 event — mer än nog för att
carva loopar över rummets öppna golv. Platthopps-farmen ≥ äkta korsningen på
VARJE skicklighetsnivå, är riskfri, kräver ingen gropexponering och förfalskar
n_gap. I takeoff-envs, där noveltyn nollats (fix 3) och gapbonusen enligt
kommentaren är det policyn "tränar UTESLUTANDE på", är farmen den strikt
dominanta jämvikten — fixpaketet har därmed byggt en miljö som aktivt selekterar
för exakt det beteende det skulle förhindra.

**Varför detta är samma underkännande som förra rundan:** originalskeptikerns
fynd 3 pekade ut platthoppet (NV-sidans 16u-steg) och föreskrev den EXAKTA fixen
"golv-z under banan < landing_z − 56, dvs djup relativt LANDNINGSGOLVET".
Fixteamet behandlade det som ett DATA-problem (raderade NV-states) i stället för
ett belöningsdefinitions-problem. Geometrin som betalar är inte NV-specifik —
den är varje plant golv på kartan, via origo-offseten, även på SO-sidan.

## 3. EXAKT FIX (krav för godkännande)

1. **Djup relativt fotnivå, inte flygbana** (originalskeptikerns föreskrift):
   i `_air_segment`, räkna golv-z per traceprov: `floor_z_i = buf_i.z − frac_i·512`,
   och definiera `effective_depth = min(takeoff_z, landing_z) − 24 − min(floor_z_i)`
   (24 = uppmätt origo→golvyta-offset). Gap kräver `effective_depth > 56`, djup
   `> 141`. Platt hopp: golvet = fotnivån ⇒ effective_depth ≈ 0 ⇒ diskat.
   Gropkorsningen: fot 32 − golv −224 ⇒ 256 ⇒ deep ✅ (verifierat mot kordmätningen).
   Enbart en tröskelhöjning (t.ex. 80) godtas INTE — den lämnar 16–24u-stegen
   betalbara och bevarar origo-förvirringen.
2. `test_air_bonus_thresholds_from_corpus`-familjen måste omkalibreras mot
   fotrelativa djup (dagens teststub sätter golvet 200 u ned och maskerar hålet —
   samma maskeringsklass som friktionsstubben skeptikern fällde förra rundan).
3. Omkör fan-proben efter fix: kravet är **0 utbetalningar** i yaw-fanen utom på
   banor vars traceprov faktiskt korsar gropvolymen.
4. (Sekundärt, kvarstår från förra rundan:) terminera takeoff-episoden vid första
   landningen — med djupfixen betalar efterlivet 0, men 12s-taket spenderar ändå
   ~80 % av takeoff-framarna på post-försöks-strövande som motivtexten säger
   sig ha eliminerat.

## 4. Verifierat i denna granskning

- Hela diffen läst mot master (14 filer; rl/jump_gates.py, vendor/, korpora orörda).
- Testsviten: 61 passed (1,45 s) i föreskriven miljö.
- Riktiga qwsim/dm3: levererat fartband 60 resets (252,5–389,8 ✅ claim 5);
  origo-offset 24,0 u; platthoppsdjup 67,8 u; gropkordans golvyta −199,5..−224;
  walkoff utan hopp ⇒ ingen `landing()`, n_gap 0 (claim 1a ✅); gropdyk med hopp
  ⇒ bonus 0 (claim 1b ✅); yaw-fan 4 states × 35 offsets × 3 farter ⇒ 261
  platthoppsutbetalningar (fällande); två kedjefarm-episoder genom riktiga
  `core.step` (n_gap-förgiftning + inkomsttakt).
- Kod: alla 8 fixpåståenden lokaliserade och lästa (tabell §1); NV-borttagningen,
  for-else-vakten, NaN-vakten, note()-asymmetrin, sf_env-workergrenen,
  train_gate2-flaggorna.
- INTE verifierat (utanför räckvidd): APPO-checkpointkompatibilitet under träning;
  deep-corner-cut med enstaka hopp hittades ej i fanen (gropkanten verkar indragen
  nog vid ≤390 u/s) — irrelevant så länge shallow-farmen betalar.
