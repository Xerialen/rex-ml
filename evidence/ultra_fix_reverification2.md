# Omverifiering 2 av skeptikerfixarna — fotrelativt gapdjup m.m. (wf_5769fa30-a6d-15 @ 0765fd6)

**Datum:** 2026-08-03. **Granskare:** belöningshack-skeptikern (runda 2b, adversariell).
**Underlag:** `git diff 936d264..0765fd6` läst i sin helhet; testsviten omkörd; fixteamets
fan-probe (`probe_fix2_verify.py`) omkörd oförändrad; fyra EGNA prober mot RIKTIGA
qwsim/dm3 (sessionens scratchpad: `probe_cornerclip_econ.py`, `probe_cornerclip_reach.py`,
`probe_pogo_term.py`, `probe_void_fraction.py`). Ingen kod ändrad.

## VERDICT: UNDERKÄND

Platthopps-farmen (runda 2:s fällning) är **stängd på riktigt** — verifierat i kod, i
testsvit och på riktiga qwsim (0 utbetalningar på platta/steg-banor i 840-fanen, egna
qr-prober betalar depth 0.0 ⇒ 0). Men **hörnklipps-residualen som fixteamet själva
flaggade är ingen residual — den är takeoff-miljöns nya dominanta jämvikt**, och den är
**policy-nåbar från EXAKT kanonisk spawn** med en luftstrafe-intensitet policyn redan
uppvisar. Uppmätt per-episod (terminering aktiv): klipp 18,85 total (varav bonus 9,08)
på 0,66 s mot gropfallets 9,24 på 1,2 s — 2× per episod, 3,7× per frame — och vägen
från klippet till äkta korsning går genom en belöningsdal. Samma felmodsklass som
fällde runda 1 och 2: miljön selekterar för ett beteende som inte är korsningen.
Exakt fix (sidovillkoret, mätkalibrerad) ges i §4; den är liten och avgränsad.

---

## 1. Fixpåståendena mot kod och mätning (alla verifierade)

| # | Påstående | Verifikat | Status |
|---|---|---|---|
| A | `effective_depth` fotrelativt: `min(takeoff_z, landing_z) − 24 − min(golv-z under banan)` | `env_gate2.py:290-312` (golv-z = prov-z − frac·512; foot_z via `ORIGIN_FLOOR_OFFSET=24`, `rewards_gate2.py:87-89`); exakt originalskeptikerns föreskrift ur `ultra_fix_reverification.md` §3.1 | ✅ |
| A′ | Platthopp betalar 0 | Fan-probens 840 trials omkörda av mig: 52 utbetalningar, SAMTLIGA med depth 256,0 (äkta gropvoid) — inga 67,8-artefakter; egna prober: platta/steg-banor (qr-SO ±60, rq-SO-b +55) ger depth 0,0 ⇒ bonus 0; helvarvstestet `test_flat_hop_full_loop_...` i sviten | ✅ |
| A″ | Teststubben omkalibrerad (maskeringsklassen från runda 2 borta) | `GroundKeepBackend.set_pit()` lägger gropen i banans MITTPARTI medan avstamp/landning står på golvytan — stubben kan inte längre dölja origo-offset-klassen; platthoppsregression explicit (`test_flat_hop_pays_no_gap_bonus_and_no_n_gap`) | ✅ |
| C | Terminering vid första landningen i takeoff-envs | `env_gate2.py:365-371,385`; fan: 0/840 uteblivna termineringar; walkoff terminerar också (avsett); `landed` i info | ✅ |
| C′ | Termineringens randfall | Settling kan inte sätta `_landed_done` (reset går via `b.step`, aldrig `core.step`); 0/300 resets luftburna efter reset (inget tick-1-fantomavslut); pogo-kringgående UTESLUTET på riktiga qwsim: med hoppknapp HÅLLEN rapporteras `onground=True` på landningsticken (mvdsv kräver knappsläpp, `jump_held`) ⇒ terminering + `landing()`-avräkning fyrar (`probe_pogo_term.py`: done @ t=88, landed=True); icke-takeoff-envs opåverkade (test i sviten) | ✅ |
| D | Fartband 350–450 | Levererat band över 300 resets: 350,7–449,9, 300/300 grundade; defaults i `Gate2Config`, `sf_env.py`, `train_gate2.py` konsekventa | ✅ |
| — | Testsvit | **64 passed in 1.77 s** i föreskriven miljö | ✅ |

**Nya kryphål i effective_depth sökta, ej funna:** (i) landa på upphöjt objekt drar INTE
upp fotnivån (`min(takeoff_z, landing_z)` tar det lägre); (ii) ledge→golv-hopp inom
−24-fönstret mäter djup relativt det LÄGRE ändläget ⇒ bara äkta trenchdjup betalar;
(iii) frac 1.0 (inget golv inom 512) klassas djupt — korrekt över gropen, ofarligt i
takeoff-envs. Skönhetsfläck utan hål: takeoff-z registreras på första LUFTBURNA ticken
(z redan +3,4 över marknivån) ⇒ eff_depth överskattas med ≤3,4 u — marginalen platt(≤27)
mot tröskel(56) sväljer det.

## 2. FÄLLANDE: hörnklippet är dominant farm, inte svag gradient

### 2.1 Omfattning (fan-proben reproducerad)
Min omkörning gav **exakt fixteamets siffror**: 52/840 utbetalningar, samtliga
icke-korsningar, samtliga depth 256,0 (äkta void under banan — per-sampel bekräftat,
`probe_cornercut_samples.py`-metoden). Träffarna ligger på **rq-sidans två states**
(rq-SO, rq-SO-b); qr-states betalar inget klipp i fanen. En träff ligger på yaw_off
**−15** (rq-SO-b, bonus 7,67) — 9° från spawnerns jitterkant, inte "±35–80".

### 2.2 Policy-nåbarhet från KANONISK spawn (fanens blinda fläck)
Fan-proben strafear inte i luften — den underskattar nåbarheten. Egna mätningar
(`probe_cornerclip_reach.py`, riktiga qwsim, spawnerns exakta states, yaw_off 0):

- **Luftstrafe dyaw 0,15 (= 3°/tick) + side-knapp**, rakt från kanonisk spawn rq-SO:
  bonus 7,25 / 8,16 / 9,08 @ 350/400/450 — landning samma sidas rim (d_tgt 571–573).
  Policyn strafear redan 1,7–2,9°/tick (132–226°/s, Fas 1-mätt): klippet ligger EN
  liten, konstant strafejustering från nuvarande beteende.
- **Markvridning 4 tick × −20° före hoppet** (rq-SO-b, yaw_off 0): bonus 6,63–6,77.

### 2.3 Ekonomi per EPISOD med terminering aktiv (en utbetalning, sedan död)

| Strategi (fart i bandet) | Bonus | r_total/episod | Episodlängd | r/frame |
|---|---|---|---|---|
| Hörnklipp, kanonisk spawn + 0,15-strafe @450 | 9,08 | **18,85** | 51 tick (0,66 s) | **0,37/tick** |
| Hörnklipp, bästa fan-vinkel @450 | 11,70 | 19,05 | 51 tick | 0,37/tick |
| Gropfall (rakt korsningsförsök) @450 | 0 | 9,24 | 92 tick (1,2 s) | 0,10/tick |
| Gropfall @350 | 0 | 2,83 | 92 tick | 0,03/tick |
| Hopp på stället/kort hopp | 0 | ~1–2 | ~50 tick | ~0,03/tick |
| Fullbordad korsning (referens; kräver ~700 u/s rakbana i sim) | 15,00 | 119,3 | 51 tick | 2,3/tick |

Fullbordad korsning är bäst — men nuvarande policy fullbordar 0/144, och i bandet
350–450 utan skickligt luftstrafe-uppbygge existerar ingen fullbordande bana (positiv-
kontrollen behövde ≥700). Vid faktisk skicklighetsnivå är hörnklippet **argmax i varje
episod, med 2× gropfallets return och 3,7× dess frame-rate**, nåbart via en gradient-
kontinuerlig deformation av nuvarande beteende (öka högerstrafen något). Vägen klipp→
korsning går däremot genom dalen "mellanvinklar = gropfall" (return halveras innan
någon korsning är möjlig) — PPO korsar inte den dalen självmant. Dessutom **förgiftar
klippet n_gap** (n_gap=1 per klipp i mina prober): kurriculum-/rapportmåttet "gap-
korsningar" räknar rimhopp som lyckanden. Detta är (a), inte (b).

### 2.4 Varför (b)-tolkningen ("nyttig tidig formning") inte håller
Klippet lär "hoppa vid kanten och landa tryggt" men ankrar heading/strafe BORT från
målplattformen, terminerar episoden med full utbetalning och släcker därmed allt
inkrementellt tryck mot andra sidan. Den enda formningen som kvarstår är den mot
klippet självt.

## 3. Kartfri fix är uppmätt OMÖJLIG — därför sidovillkoret

Först prövades den snyggare fixen (kräv att voiden täcker banan/kordan):
`probe_void_fraction.py` mätte void-andel under HELA flygbanan (alla 16 buffertprov):
**klipp 0,88–1,00** (diagonalen över gropens hörn är nästan helt över void) mot
**korsning 0,81–1,00**. Ingen separation — klippet är geometriskt en äkta void-bana
som råkar börja och sluta på samma rim. Det som skiljer är inte banan utan **vart man
kommer**: därför måste villkoret vara målprogression/landningssida, precis som
fixteamet själva anade.

## 4. EXAKT FIX (krav för godkännande) — alternativ (c), mätkalibrerad

Takeoff-states bär redan målet (`landing_2d`). Gapkvalificeringen i takeoff-envs ska
kräva att landningen faktiskt tagit sig mot målet:

1. I `_pick_spawn` (takeoff-grenen): spara valt states mål,
   `self._takeoff_target = np.asarray(s["landing_2d"], dtype=float)`
   (sätt `self._takeoff_target = None` i `_reset_state` för övriga grenar).
2. I `_air_segment`, efter `eff_depth`-beräkningen:
   ```python
   # Sidovillkoret (skeptikerrunda 2b): gapbonus i takeoff-envs kräver
   # målprogression — hörnklipp (landning samma sidas rim) diskas
   if self.cfg.spawn_takeoff_states is not None \
           and self._takeoff_target is not None:
       u = self._takeoff_target - takeoff[:2]
       d = float(np.linalg.norm(u))
       prog = float((self.pos[:2] - takeoff[:2]) @ u) / (d * d) if d > 1e-6 else 0.0
       if prog < 0.6:
           eff_depth = 0.0        # ⇒ gap_qualifies False ⇒ bonus 0, n_gap orört
   ```
3. **Tröskelkalibrering (uppmätt, riktiga qwsim):** prog för samtliga uppmätta klipp
   0,054–0,444 (strafe-klippet 0,079; markvridningsklippet 0,281; värsta fallet
   fan −35° 0,444); prog för fullbordade korsningar 0,805–0,902. Tröskeln 0,6 har
   ≥0,16 marginal åt båda håll. Villkoret nollar också klippets n_gap-förgiftning.
4. **Verifieringskrav efter fix:** (i) omkör 840-fanen: 0 utbetalningar med
   d_tgt > 130; (ii) omkör strafe-nåbarhetsproben (`probe_cornerclip_reach.py` §2):
   0 utbetalningar; (iii) positiv kontroll: alla 4 states betalar fortfarande 15,0
   på korsningsbanan; (iv) enhetstest av sidovillkoret med stubben (klipp-geometri:
   prog < 0,6 ⇒ 0; korsning ⇒ full bonus).
5. Villkoret ska INTE appliceras i icke-takeoff-envs (där finns inget states-mål och
   ingen terminering; se §5 om rim-skim-klassen där).

En ren tröskeljustering (t.ex. GAP_MIN_SPAN eller djupkrav) godtas INTE — klippets
span (161–293) och djup (256) överlappar korsningens helt.

## 5. Kvarstående, ej fällande (loggas för nästa granskare)

- **Rim-skim-klassen i strövande envs:** gapbonusen betalar var som helst på dm3 där
  en ≥56 u-kant kan överflygas med landning ≥150 u bort på samma nivå (gropens rim är
  fallet som mätts; mega-/walkway-kanter är samma klass). Ingen terminering där, så
  kedjning är möjlig (~6,7–11,7 per ~1,5–2 s cykel om geometrin medger). Kartfri
  separation mot äkta korsning är omöjlig (§3), och i strövande envs konkurrerar
  novelty + kinetik (0,153/tick @450 = 11,8/s) om policyns tid. Rekommendation:
  aktivera `--qw_gap_anneal` för strövande envs och logga transitionscellstoppen för
  n_gap i varje träningsrapport så en ev. skim-jämvikt syns direkt.
- **Fan-probens metodik i övrigt sund** (spy på riktiga `landing()`-argument, riktiga
  qwsim-banor, positiv kontroll per state, termineringsräkning) med två anmärkningar:
  (i) ingen luftstrafe ⇒ nåbarheten underskattas — komplettera framtida fan-körningar
  med §2.2-strafevarianterna; (ii) stdout-buffring tappade de första ~39 träffraderna
  när körningen flyttades till bakgrund — skriv till fil med `-u`/explicit flush.
- Fartbandets golv levererar 350,7 (inte exakt 350,0) — uniform dragning, ofarligt.

## 6. Verifierat i denna granskning

- Hela diffen 936d264..0765fd6 läst (7 filer; jump_gates/vendor/korpora orörda).
- Testsviten: 64 passed (1,77 s), föreskriven miljö.
- Fan-proben omkörd oförändrad: 52/840, alla depth 256,0, FIX C 0 missar — fixteamets
  siffror reproducerade exakt.
- Egna prober på riktiga qwsim/dm3: ekonomi per episod (8 klipp-, 12 gropfalls-,
  3 korsningskonfigurationer, fulla `core.step`-returer); nåbarhet (markvridning,
  äkta side-strafe, jitterlägen); pogo-/settling-/tick-1-randfall för termineringen;
  void-andel under 9 banor (fixdesign-underlag); 300 reset-stabilitetsdrag.
- INTE verifierat (utanför räckvidd): rim-skim-farmens faktiska takt i strövande envs
  utanför gropens rim (klassen belagd, ej karterad över hela dm3); APPO-checkpoint-
  kompatibilitet under träning.
