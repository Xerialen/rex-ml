# Omverifiering 3 av fixrunda 3 — målprogressionsvillkoret (master @ ea526fc, TRÄNANDE)

**Datum:** 2026-08-03. **Granskare:** belöningshack-skeptikern (runda 3, adversariell).
**Läge:** diffen redan mergad och tränar (PID 319909, 28 takeoff-workers) — verifiering
körd PARALLELLT enligt journalförd avvikelse (ägarens tidsultimatum). Prober körda
`nice -n 15` mot MASTER med riktiga qwsim/dm3. Ingen kod ändrad.
**Underlag:** env_gate2.py/rewards_gate2.py/sf_env.py/train_gate2.py lästa; master
bit-identisk med worktreen fixagentens prober testade (diff = tom för alla tre
nyckelfiler); fixagentens prober + utdata granskade (`probe_fix3_fan.py/.out`,
`probe_fix3_reach.py/.out`); EGEN probe `probe_reverif3.py` (sessionens scratchpad),
162 avstampstrials + 16 marksonder, MED TRÄNINGENS koefficienter.

## VERDICT: GODKÄND — regimen får fortsätta

Sidovillkoret `prog >= 0.6` är korrekt implementerat, korrekt kalibrerat och stänger
hörnklippsfarmen på riktigt. Samtliga fyra attackvinklar prövades adversariellt mot
riktiga qwsim; ingen gav en enda falsk utbetalning. Avgörande styrka: villkoret är
INTE ensamt — prog-gaten och landningsnivåkravet `rise >= -24` (gap_qualifies) är
oberoende gates som båda måste passeras, och varje funnet randfall fångas av minst en.

---

## 1. Attackvinklarna, resultat

### 1.1 Overshoot-exploaten (huvudattacken) — STÄNGD
Fråga: kan bandfart 350–450 + aggressiv luftstrafe nå prog >= 0.6 och landa på något
som inte är målplattformen? **Uppmätt (104 trials: dyaw ±0.5/±1.0/±1.5 med side-knapp,
fördröjd strafe-onset 5/15 tick, diagonalstarter yaw_off ±25/±35, farter 400/450,
alla 4 states):**

- Max uppnådd prog i bandet: **0.746–0.816** — men SAMTLIGA max-prog-landningar är
  GROPGOLVET (z −200, rise −259). prog >= 0.6 är alltså nåbart i luften/gropen, men
  `rise >= −GAP_MAX_DROP` diskar varje sådan landning. **0 utbetalningar.**
- Ingen landning med rise >= −24 nådde prog >= 0.6 vid bandfart — rimmen/ledger på
  sidorna ligger alla under 0.45 (klippkalibreringen) eller är onåbara.
- Bortre rim/förlängning bortom målet: onåbart i bandet (kräver ~700+ u/s; vid den
  farten ÄR landningen en korsning till andra sidan — betald med rätta).

### 1.2 prog-formelns randfall — OFARLIGA
- d per state är 573–667 (inga kort-d-states existerar i gate_takeoff_states.json);
  d²-förstärkning irrelevant i nuvarande data.
- prog > 1 (overshoot förbi målet) är okapat men kräver längre hopp än korsningen
  själv ⇒ per definition en fullbordad korsning till bortre sidan. Ofarligt.
- Fixagentens qr-SO-kontroll (d_tgt 184.7, prog 0.84 @900): reproducerad ekvivalent
  (min qr-SO-b @900: d_tgt 66.0, prog 0.899, bonus 15.0) — det är äkta bortre-sidan-
  landningar på plattformsnivå (rise −3.3), inte exploat.

### 1.3 Mid-air-vändning — STÄNGD BY CONSTRUCTION + uppmätt
prog beräknas ur LANDNINGSPOSITIONEN (env_gate2.py:346, `self.pos[:2]` på
landningsticken), aldrig ur luftbanans max. Uppmätt (ut-och-tillbaka, switch @18,
dyaw2 2.0): landning prog 0.26–0.34, depth nollad, **bonus 0.0**, FIX C-terminering
fyrade. Ingen väg att "checka in" prog i luften existerar.

### 1.4 Bakre/sido-arcs + klätterbonusens prog-lucka — TOM
Observation ur koden: prog-villkoret nollar ENDAST `eff_depth`; klätterbonusen
(`rise >= 24` ⇒ `climb_coef × rise`) är prog-OGATED, och träningen kör
`--qw_climb_coef=0.5` (inte defaultens 0.08) ⇒ en nåbar +24-landning hade betalat
upp till 48.0 (3× korsningens 15.0) utan målkrav. **Uppmätt (52 trials, yaw_off
90–270° i 15°-steg @450, alla states): 0 landningar med rise >= 24, 0 utbetalningar**
— ingen förhöjd geometri finns inom hoppräckvidd från någon av de 4 staterna.
Luckan är verklig i koden men tom i geometrin; loggas som bevakningspunkt (§3).

### 1.5 "Aldrig hoppa"-farmen — GEOMETRISKT OMÖJLIG
Med träningens höjdterm (`height_coef=1.5`) betalar grundad rundstrykning ~1.17/tick
FÄRSKT, avklingande till **0.183/tick** när CellRarity-EMA:n mättats (10-pass-mätning,
konvergens efter 2 pass). Men: ALLA 6 markkontroller (dyaw 0.25/0.4/0.6, rak 0/4)
lämnade ledgen vid tick ~67 — spawnen ligger 7–15 u från kanten med 350–450 u/s
injicerat MOT gropen; ingen icke-hoppande styrning håller sig kvar. Takeoff-episoder
självtermineras inom ~0.9–1.2 s oavsett beteende. Ingen 924-ticks-inkomstfarm finns.

## 2. Fixagentens verifiering — validerad, med en funnen metodiklucka

- **Fan-proben (840 trials) och strafe-nåbarhetsproben:** metodiskt korrekta — spyn
  på `landing()` ser depth EFTER prog-nollningen (dvs. det som faktiskt betalas),
  n_gap/FIX C avläses ur kärnan, riktiga qwsim-banor, positiv kontroll per state.
  Deras 0-resultat reproducerades och BREDDADES av mina 162 trials (starkare strafe,
  fördröjd onset, bakre arcs) — fortfarande 0.
- **Funnen lucka:** probernas Gate2Config använde DEFAULTS (climb 0.08, height 0.0,
  rarity av) medan träningen kör 0.5/1.5/på — deras ekonomitabeller underskattar
  per-tick-inkomsterna och kunde inte se klätterbonus-luckan (§1.4). Jag omprobade
  med träningens koefficienter; slutsatserna står, men **framtida prober SKA använda
  träningens flaggvärden** (annars är ekonomijämförelserna fel skala).
- Master == worktreen probernas kördes mot (bit-identiskt, verifierat med diff).
- **Testsvit: 66 passed (1.48 s)** i föreskriven miljö, körd mot master.

## 3. Ekonomi (träningskoefficienter, steady-state efter EMA-mättnad)

| Beteende @bandfart | r_total/episod | r/tick | Betalar gapbonus? |
|---|---|---|---|
| Gropfall rakt @450 (färsk env) | 152 | 1.65 | Nej (rise −259) |
| Markstrykning (bästa kontroll, mättad EMA) | 12.3 (faller av @67 tick) | 0.183 | Nej |
| Mid-air-vändning | 82–85 | ~0.9 | Nej |
| Hörnklipp (alla varianter) | — | — | **Nej — 0 träffar** |
| Korsning @700 (referens, onåbar i bandet) | 271 | 5.31 | Ja, 15.0 |

Ingen nåbar strategi i bandet betalar gapbonus; ingen dominerar på falsk inkomst.
Fortsatt gäller (från runda 2): korsning är onåbar vid 350–450 utan uppbyggd
luftstrafefart — regimens gradient mot korsningen bärs av att ALLT annat nu betalar
i storleksordningen 10–150/episod mot korsningens 271+ (fartexponentialen dominerar).

## 4. Bevakningspunkter (EJ fällande, loggas för nästa granskare)

1. **Klätterbonusens prog-lucka** (§1.4): tom i dagens 4 states men öppnas om nya
   takeoff-states med förhöjd geometri inom hoppräckhåll läggs till. Rekommendation:
   nolla även klätterbonusen under prog-tröskeln i takeoff-envs, eller verifiera
   arcs vid varje states-ändring.
2. **`s.get("landing_2d")`-fallbacken** (env_gate2.py:147): en takeoff-state UTAN
   landing_2d gör target None ⇒ sidovillkoret tyst avstängt för den staten ⇒
   hörnklippsfarmen återuppstår lokalt. Dagens 4 states har alla fältet. Rekommenderat:
   hård assert vid laddning + enhetstest.
3. **Kodkommentaren "tränar UTESLUTANDE på gapbonusens signal"** (env_gate2.py:112)
   är inte längre sann under `--qw_height_coef=1.5` — höjd/fart betalar per tick även
   i takeoff-envs (uppmätt 0.18–1.65/tick). Ofarmbart p.g.a. geometrin (§1.5) men
   kommentaren bör rättas vid nästa beröring.
4. Rim-skim-klassen i STRÖVANDE envs (runda 2b §5) kvarstår oförändrad — utanför
   denna rundas omfång; `--qw_gap_anneal` är aktiv i träningen som rekommenderat.

## 5. Verifierat i denna granskning

- prog-implementationen (env_gate2.py:32-36, 142-151, 185-188, 327-349) läst mot
  runda 2b-föreskriften: exakt följd, inklusive n_gap-avgiftningen och
  endast-takeoff-scopet (strövande envs oförändrade — target None i alla grenar).
- Kalibreringsmarginalen bekräftad i praktiken: högsta icke-korsnings-prog med
  giltig landningsnivå låg under 0.45; gropgolvslandningar (prog upp till 0.82)
  fångas av rise-gaten. Tröskeln 0.6 sitter i ett uppmätt tomt band.
- Träningsprocessen kör mergad master (PID 319909, start 17:51, 28 takeoff-workers,
  flaggor lästa ur processlistan).
- INTE verifierat (utanför räckvidd): rim-skim i strövande envs över hela dm3;
  APPO-inlärningsdynamiken (om policyn faktiskt hittar korsningen är en
  träningsfråga, ingen hackfråga).
