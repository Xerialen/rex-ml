# rex-ml — problembeskrivning och datakälls-audit

*2026-07-30 · status per race_v9 · skriven för granskning utanför projektet.*

---

## 1. Uppdraget

Bygga ett ML-tränat rörelselager för QuakeWorld-botten på DM3, som A/B-alternativ till den
analytiska RTX-botten. **Striden hålls identisk** — endast rörelselagret byts, så varje uppmätt
skillnad är kausalt hänförbar till rörelsen. Mätbara mål:

1. **Snabbare rutter** än RTX-baslinjen över en fast DM3-ruttuppsättning, median över ≥ 30
   körningar per rutt, 95 % KI som utesluter noll.
2. **Aldrig fast**: noll fastkörningar; Tracking Guard kopplar ur vid > 32 u spårfel och den
   analytiska reserven tar över.

Hård invariant: **p99 CPU per servertick < 0,5 ms** (DMP-integration + MLP-framåtpass +
tracking guard). Fusk-regel från ägaren: **rakethopp är otillåtna** på alla rutter utom det
uttryckligen undantagna rjump-to-window-at-pent (som ännu inte modellerats).

## 2. Kärnproblemet i dag: policyn är en linjeföljare

Tre träningsgenerationer har nu mätts under det strikta protokollet (48 samplade episoder per
ingång, ankomst + mediantid + väggskrap + hölje + manöverkrav):

| generation | träningsgeometri | strict-resultat | nyckelmätning |
|---|---|---|---|
| race_v7 | navmeshplaner | 0/7 | sngspawn a/b 89,6/91,7 % — men window/ralow/ring tog omvägar som ingen människa tar (hölje 250–355 u mot band 40–84) |
| race_v8 | människolinjer (human_k 6) | 0/8 | 76,7 % på sina egna träningslinjer, **0 % på navmeshgeometrin** — och v7 spegelvänt 0/48 på människolinjer |
| race_v9 | blandat: människolinjer + navmesh i samma batch, spawn-filter, strict-probe var 100:e iter | 0/8 | ring 87,5 %/tunnel 89,6 % med 0 % skrap och manöver 100 % på bästa ingång — men helruttstarterna förblir ~0 % |

**Diagnosen är mätt, inte gissad** (`evidence/sngspawn_regression.json`): policyn observerar
banan via lookahead-punkter och lär sig följa exakt den kurvgeometri den tränats på. Byts
linjen byts allt. Entropikollaps och fartöverskjutning prövades som hypoteser och **avfärdades**
med siffror (v8 har högre styrentropi än v7 och är långsammare). Även blandad geometri (v9)
räckte inte för generalisering från ruttstarterna; förbättringen kom i stället i ruttens senare
delar (ingång 2–3) där linjerna sammanfaller.

Konsekvensen är ett **arkitektur-/protokollbeslut som står öppet**:

> Ska det strikta provet betygsätta policyn på navmeshens plangeometri, eller på
> människolinjen — den geometri botten faktiskt skulle skeppas med som styrreferens?

Navmeshplanerna har själva uppmätta omvägar (window-planens max_x = 1952 mot människornas
aldrig-över-1678; planlängd 2002 u mot människans 1185 u), så att betygsätta på dem betyder
att policyn följer en bana som höljesgrinden sedan fäller. Att betygsätta på människolinjen
är ärligt om och endast om det är den linje som skeppas. Beslutet ligger hos ägaren.

### Vad som bevisligen fungerar nu

- **Manövergrinden** (`pipeline/ratop_gate.py`): kant-till-kant-hoppet vid RA-toppen utförs i
  100 % av ankomna episoder på ring/ralow/tunnel (v7 gick runt — höljet kunde inte fälla det,
  manövergrinden kan). Den fällde också direkt sng_to_quad-försöket som nådde Quad utan
  dubbelhoppet (100 % ankomst, manöver 0 % → ej godkänd).
- **Höljesgrinden** med anslutningsregel: fäller banor utanför människounionen, friar äkta.
- **RJ-golvprobsvetten**: skiljer trappklättring från rakethopp bimodalt utan överlapp.
- **Bevisdisciplinen**: varje runda spelas in tick för tick och publiceras innan den
  rapporteras (ägarens stående regel).

## 3. Grindarna och deras härledning

Alla trösklar är **korpushärledda, aldrig påhittade**:

| grind | konstruktion | värden |
|---|---|---|
| Ankomst | andel episoder i målboxen (24 u plan / 48 u höjd) | krav 100 % — **känd skuld:** 48/48 belägger bara ≥ 92,6 % (Wilson); formuleringen bör bytas till Wilson-undre-gräns |
| Mediantid | mot kohortens gate_s (no-combat-median) per rutt | t.ex. window 2,75 s, sng_to_quad 6,04 s |
| Väggskrap | andel rörelsetick < 1 u lateral frigång; band = människornas p95 per rutt | band 4,6–24,1 % |
| Hölje | per körning max-avstånd till människobanornas union (leave-one-out p95, förtätad 16 u, anslutningsregel: mätning från första sampel innanför bandet, aldrig-ansluter → ∞) | band 23,6–108,4 u; sng_to_quad 289,5 u är **oanvändbart** (4 körningar) — manövergrinden bär den rutten |
| Manöver | luftsegment vars avstamp OCH nästa markkontakt ligger inom 96 u av människans ankare, med ≥ 96 u tomrum under flykten | ring/ralow/quad/tunnel→ratop + sng_to_quad (två giltiga landningsankare pga mittavsatsens apex-problem) |

## 4. Datakällorna — auditens kärna

### 4.1 Råa demokorpusar (källmaterialet)

| källa | storlek | innehåll |
|---|---|---|
| `~/qw-corpus-build` | 281 GB | byggyta/mellanprodukter för korpusextraktionen |
| `~/mvd-corpus` | 161 GB | MVD-demon (serverinspelningar, huvudsakligen 4on4) |
| `~/qwd-corpus` | 56 GB | QWD-demon (klientinspelningar) |

**Styrkor:** enorm volym av verkligt mänskligt spel på riktiga servrar; MVD ger alla spelare
samtidigt. **Svagheter:** okuraterat (strid, AFK, specialregler); formatvariation (FTE-
utökningar som vår strikta parser avvisar); ingen enskild källa är "movement-only".
Skrivskyddade och oersättliga — all bearbetning sker till separata store-kataloger.

#### MVD kontra QWD i den extraherade storen — uppmätt 2026-07-30

| egenskap | MVD (serverdemo) | QWD (klientdemo) |
|---|---|---|
| andel av trajectory_samples | **843,9 M rader (93 %)** | 64,1 M rader (7 %) |
| demos / spelar-slots | 2 273 / 17 818 (≈ 7,8 spelare per demo = 4on4) | 512 / 3 118 |
| samplingstakt (median, p5–p95 per demo+slot) | **29,0 sampel/s** (19,5–72,4) | 13,2 sampel/s (6,5–67,6) |
| hastighet i samplen (`velocity_present`) | **0 %** — endast positioner | 43,3 % |
| usercmds (knapptryck/intention) | **saknas helt** | 29,9 M rader (endast inspelaren) |

**MVD:s fördelar:** volymen (nästan all statistik — höljesband, ruttgraf, heatmap — vilar på
MVD-delen); alla spelare i matchen samtidigt, vilket ger 4on4-flödet och livssegmentering; drygt
dubbla samplingstakten mot QWD-delen. **MVD:s nackdelar:** inga hastigheter (vz för RJ-analys
måste härledas ur positionsdifferenser, därav golvprobs-vetten som är dt-oberoende) och inga
usercmds (intentionen — hopptryck, styrning — är osynlig i MVD-delen). **QWD-delens
nackdelar:** liten (7 %), glesare sampling med större spridning, och usercmds finns bara för
den spelare som spelade in.

**Rättelse/precisering (2026-07-30, efter korsläsning mot projektets fas 1-audit `AUDIT.md`):**
storen innehåller utöver `trajectory_samples` även `replay_ticks` (per-tick tillstånd:
position, hastighet, onground, jump_held, waterlevel vid 72–77 Hz) och `usercmds` (29,9 M
rader) för QWD-delmängden, joinbara på (demo_key, slot, cmd_ordinal). Beteendekloning är
alltså **möjlig på QWD-delmängden** — fas 1–2 tränade också BC/DAgger-policyer på exakt den —
men **strukturellt omöjlig på MVD-bulken** (93 % av volymen), eftersom MVD är en server-
entitetsström utan klientkommandon. Slutsatsen står därmed kvar i försvagad form: korpusens
*bredd* (band, ruttgraf, tider) kommer från MVD utan intention; intention finns bara i den
lilla QWD-delen och i ägarens referensdemon, och RL mot korpushärledda grindar bär huvudvägen.

### 4.2 Den extraherade korpusstoren `~/dm3-extract/store-dm3` (8,5 GB parquet)

Arbetshästen. Hive-partitionerad parquet (split × format) med bl.a. `trajectory_samples`
(**907 977 350 rader** ur **2 146 demos**: demo_key, slot, t, x/y/z, blickvinklar,
hastighet när tillgänglig), `item_events` (~186 k RA-plock användes för att verifiera
RA:s position), `frags`, `spawns`, `movement_windows`, `usercmds`.

**Styrkor:** volymen gör statistik möjlig (höljesband, ruttgraf med 3,0 M direkttransiter,
trafikheatmap på 11 s med duckdb/12 trådar); item-händelser ger exakta nodpositioner;
livssegmentering möjlig via frags/spawns. **Svagheter, i detalj:**

- **Gles sampling:** ~12+ sampel/s (13–83 ms mellan rader) mot spelets 77 tick/s. En
  vertikal impuls kan gömma sig mellan sampel — därför är RJ-vetten byggd på golvprober
  (dt-oberoende) i stället för implicerad hastighet.
- **Boxsemantik:** transittider mäts box-till-box (±64/±80 u), systematiskt snabbare än
  route-labs händelsebundna kohorttider. Får inte jämföras 1:1 mot gates.
- **Teleport-diskontinuiteter:** 776–787 u på ett intervall; äkta tele-användning är 14,5 %
  av all transitvolym och måste klassas separat (gjort i ruttgrafen).
- **Kontaminering:** strid, rakethopp (98 av 106 tunnelkandidater!), dödsartefakter (19,7 %
  av råa transiter förkastades i ruttgrafen).
- **Ingen intention:** korpusen visar var folk *var*, inte vad de *försökte* göra.

### 4.3 Ägarens referensdemon `demos/dm3-drillar/` (34 filer)

QWD-filer inspelade av ägaren, lästa med qw-demo-miners strikta QWD-v2-extraktor: origin och
hastighet ur serverns playerinfo, blickvinklar/knapptryck ur dem_cmd, **en rad per servertick
(77 Hz)** — full trohet inklusive intention.

**Styrkor:** exakta, avsiktliga, movement-only, fusk-verifierbara (RJ-analys av
`(spawn)rl-to-ratop-xer.qwd`: max vz 259 < 270 över 1 525 tick — rent). Referensen för
manöverankarna och sidans "DIN INSPELNING"-spår. **Svagheter, i detalj:**

- **n = 1 per rutt** (ibland 0): statistiska band kan inte byggas på dem.
- **Två filer oparserbara** (`rl_to_ratop.qwd` = `spawn-rl_to_ratop.qwd`, byte-identiska
  FTE-inspelningar, FTEX-mask 0x21087008) — endast `-xer`-omtagningen är användbar.
- **En dubblett:** `(hex)sng-to-quad.qwd` är kopia av `sng-to-quad.qwd`.
- **Bekräftat saknade:** quad→RA(-topp) (felmappningen rättad 2026-07-30; korpusen räcker
  där men ägarreferens saknas), YA→RA-topp (0 användbara korpuskörningar — högsta prio),
  tunnel→RA fler tagningar, sngspawn→quad utan tele, RL→RA-topp movement-only.

### 4.4 Extraherade människobanor `pipeline/out/paths/*.json`

Per rutt: upp till 24 vettade körningar (kohortkriterier ur route-lab + vet: ≥ 12 sampel/s,
3D-gap ≤ 220 u, stigning ≤ 95 u/0,5 s **om ej golvstödd** — golvproben mot dm3.bsp är
2026-07-30-revisionen som återvann 640 falskt RJ-förkastade trappklättringar på ralow och
lyfte tunnelkohorten 8 → 24 banor, band 110,7 → 64,2 u).

**Styrkor:** ruttens *hölje* — den enda källan som definierar "linjen människor faktiskt
tar", grunden för höljesgrind och human_k-träningsgeometri. **Svagheter:** ärver korpusens
gleshet; kohortstorlek varierar (sng_to_quad: 4 banor → oanvändbart band); topp-24-urvalet
biaserar mot snabba körningar; **v2-revisionen är inkopplad endast för ralow/tunnel** —
quad (423 återvunna) och ring (335) väntar på omkomponering (medveten paus för att inte
flytta målstolpar mitt i en betygsättning).

### 4.5 Navmesh/planerare (rtx-nav)

Klipphulls-baserad mesh + plannerare som ger Route.path i navmeshläget samt ingångspunkter
(`mesh_approaches`) till strict-provet.

**Styrkor:** heltäckande, deterministisk, byggd på spelets faktiska kollisionsmodell; enda
källan för "ingångar en motståndare kan komma ifrån". **Svagheter, uppmätta:**

- **Planerna tar egna omvägar**: window-planen max_x 1952 (människor ≤ 1678), plan 2002 u
  mot människans 1185 u; ralow-planen min_x −224 → policyn lärde sig väster-om-tornet.
  Rotorsaken till v7:s "genombrott" som höljesgrinden sedan fällde.
- **Modellerar inte trickhopp**: 293/293 planer till RL går in på ETT ställe; sng→quads
  263 u-tomrum saknar länk (mesh-planen är 5 946 u och kräver 984 u/s snitt — ouppnåelig).
- **Obyggbara ingångar:** `Vec3(-501.3, 265.3, 154.7) does not stand` — ingång 2 på
  sngspawn a/b kan inte instansieras; täckningshål i protokollet (varnas i rapporterna).
- **Enda ingång på window**: provet kan inte testa fler vägar än meshen modellerar.

### 4.6 Korpushärledda band (`evidence/wall_band.json`, `envelope_band.json`)

Se § 3. Styrka: inga påhittade trösklar; regressionskollade vid omderivering (identiska värden
för oförändrade kohorter). Svaghet: **höljet är ett oordnat punktmoln** — utan sekvens- eller
luftbegrepp kan det inte skilja "flög över tomrummet" från "gick runt via ramp som människor
korsat tidigare i löpet" (uppmätt: gå-runt 60,3 u mot rings band 84,3). Det var exakt därför
manövergrinden byggdes.

### 4.7 Ruttgrafen och snabbaste-referenserna (`evidence/route_graph*.json`, `fastest_refs.json`)

24 noder (14 items, 6 spawns, 4 tele-ändpunkter), 3 008 058 direkttransiter inom samma liv
(dödsbrytning via frags, hastighetsfilter, tele separat). Klassning mot ruttsetet: **16
COVERED / 90 PARTIAL / 272 MISSING / 3 TELE; 23,8 % av transitvolymen på MISSING-kanter.**
Huvudhål: hela mega_hill/vatten/pent-komplexet, rundown-riktningarna (från item), norra bron.
Dessutom: fyra av de "identifierade" rutterna (ya→rl/ratop/ssg, rl→ratop) kör människor
aldrig direkt — de är segmentkedjor via mellannoder. `fastest_refs.json`: snabbaste **vettade**
korpusexempel per par (rå tid redovisad bredvid — ofta RJ/tele; t.ex. ralow→ratop rå 0,25 s =
RJ, vettad 3,52 s).

**Styrkor:** den ärligaste bilden av vad en autonom bot behöver kunna. **Svagheter:**
transiter ≠ avsiktliga rutter (inkluderar stridsdriven rörelse); boxsemantik; grafen ärver
korpusens 4on4-bias (pent sällan uppe → LG→pent tunn).

### 4.8 Kartkällan (dm3.bsp)

BSP29 direkt: rendergeometri (trianglar, `pipeline/bsp_geometry.py`), entiteter (items,
spawns, tele-brushvolymer, hissar) och golvprober för void/RJ-klassning. Styrka: exakt,
komplett, samma fil som servern kör. Svaghet: klipphull ≠ synlig geometri (renderaren läser
render-lumpen just därför).

### 4.9 Fysikkonstanter

TICK_DT = 1/77 (korrigerad från 0,014 som var korpusinspelarnas klientfrekvens — felet gjorde
alla tidiga tider 7,7 % för långa och alla checkpoints out-of-distribution), sv_maxspeed 320,
gravitation 800, hopp-vz 270 (stigning 45,5 u, hängtid 0,675 s). Verifierade mot ägarens
815-spec och oberoende källor; luftaccelerationens |v'|² = v² + 900 − (v·ŵ)² bekräftad
(analytisk strafe-jumper når 822 u/s och klarar ägarens 790-grind i korridortestet).

## 5. Beräkningsresurser

Allt tungt arbete körs **lokalt på vmonster (bisapps001)** enligt ägarens direktiv:

| resurs | spec | användning |
|---|---|---|
| GPU | NVIDIA H100 NVL, 96 GB | PPO-träning (~2,1 s/iter vid 9 rutter × 2048 miljöer), strict-prov, inspelningar |
| CPU | 64 kärnor | duckdb (12 trådar: 908 M-radersaggregat på 5–11 s), banextraktion, validering |
| RAM | 1 TB (typiskt < 2 % använt) | duckdb-minnestak 40 GB satt av försiktighet |
| Disk | 891 GB varav 168 GB fria (82 % använt) | **den enda knappa resursen** — korpusarna tar 506 GB; jobb > 5 GB kräver kostnadsangivelse före start |

Anthropic-sidan används enbart för agenternas resonerande (LLM-orkestrering); ingen mätdata
lämnar maskinen förutom det som medvetet publiceras i bevisartefakterna.

## 6. Öppna beslut och kända skulder

1. **[BESLUT KRÄVS] Betygsgeometrin** — navmeshplan eller människolinje som styrreferens i
   strict-provet (§ 2). Påverkar arkitekturval för race_v10.
2. Wilson-undre-gräns i stället för råandel som ankomstgrind (48/48 ⇒ ≥ 92,6 %, inte 100 %).
3. Obyggbara ingång 2-starter på sngspawn (täckningshål, varnas men mäts inte).
4. v2-kohortomkomponering för quad/ring (423 + 335 återvunna körningar väntar).
5. Ruttsetets täckning: 23,8 % av trafikvolymen på otäckta kanter; rundowns och
   mega_hill/vatten/pent-komplexet omodellerat; vattenfysiken parkerad av ägaren.
6. Saknade ägardemon (prioordning): YA→RA-topp, tunnel→RA ×2–3, sngspawn→quad utan tele,
   RL→RA-topp movement-only, SSG→RA-topp/SNG→quad ett par vardera; nytt quad→RA-referensdemo.
7. rjump-to-window-at-pent (det enda tillåtna rakethoppet) har inget eget spår ännu;
   korpusfiltret gör inget undantag för det.
8. p99-invarianten mäts per komponent men kontinuerlig mätning i full per-tick-kedja ska in i
   varje kommande kandidatprov (ingen kandidat hittills har varit nära att skeppas).

## 7. Bevisartefakter

- **Bevissidan (replay, tick för tick):** race_v9:s strikta prov, 36 records / 117 körningar /
  1 248 mätta episoder, validator 24/24 —
  https://claude.ai/code/artifact/77217a49-a785-452e-9f42-d12522a4e0a6
- **Ruttatlasen (3D, heatmap, ruttgraf, referenslinjer):**
  https://claude.ai/code/artifact/f2e03c40-b2ba-4f9c-b855-f56c9e1bfc19
- Evidensfiler i `evidence/` (band, regressioner, ruttgraf, RJ-audit, snabbaste referenser)
  och löpande journal i `PROGRESS.md`.
