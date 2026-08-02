# A) v5.1-DRIFT: UNDERKÄND (JUSTERA) — trots att mitt formella villkor 744/0/0 passerar; B) EP5-CLAIMET: UNDERKÄND

Analyst, 2026-08-02. Detektor: `rl/jump_gates.py` v5.1 (oförändrad av mig).
Repro: `evidence/repro/vet_v51_events.py` (instrumenterat spår, assert-verifierat
mot detektorn per episod), `evidence/repro/human_ledge_v51_validation.py` (+.json;
227 assert-verifierade segment, dt=0.051).

## Sammanfattning

Implementationen följer mina båda justeringar korrekt, och slutvillkoret ur
`analyst_v5_validation.md` håller exakt på humankohorten: **744 behållna
v4-gate-event, 0 sidoflippar, 0 insläppta grazers** (genuina band-ramla 65/67,
band-lyckade 646/646). Men valideringen avslöjar att mitt villkor var
**underspecificerat**: det mätte bara retention av v4-event och missade den nya
eventkanal som PROGRESS_D_BAND=450 öppnar. Genom den kanalen släpper v5.1 på
botdumparna igenom två gate-bokningar som båda faller vid granskning — och
koordinatorns regressionsuppgift för traj_53G är felaktig. Jag underkänner drift
och tar ansvar för villkorsluckan: 744/0/0 var nödvändigt men inte tillräckligt.

## B) Ep5-claimet ("quad→ring SO: 1 försök, 0 lyckade, 1 ramla") — UNDERKÄND

Detektorutfallet reproducerar (quad→ring SO 1/0/1; ep8 korrekt kvar i axial;
traj_53G är dock INTE "allt 0", se A). Men eventet är inte mittgropsfall-klassen:

- **Claimets instrumentering reproducerar inte.** Påstått: 102 bandsampel, rå
  side_acc −62 901, massa 1 635 u·s, sidovärden −167→−320. Uppmätt i det
  assert-verifierade spåret (ep5, transit sampel 16–92): **63 bandsampel,
  side_acc −20 832, massa 542 u·s**, perp-extrem −459. Utfallet (gate, ramla)
  stämmer men claimunderlagets siffror är felmätta.
- **Ingen ledgeanvändning.** Transitens ENDA grundade sampel (43–51, z 56) ligger
  på |perp| 430–459 — ytterkantsgolvet, UTANFÖR ledgebandet (100–300). Samtliga
  22 in-ledge-sampel är luftburna, i en enda båge om 0,42 s. 76 % av den
  kvalificerande sidomassan kommer från sampel utanför bandet.
- **In-ledge-samplen är gropluftrum, inte ledge.** De ligger på dPit 45–119 där
  inget golv finns — belagt av att botten föll rakt igenom dem (z 99→−101 utan
  markkontakt). Mänskligt grundat ledgegolv (123 905 sampel, 24 demos) börjar
  vid dPit p1 = 134.
- **Avbrutet gaphopp, inte fallerad korsning.** Ett enda hopp från ytterkanten
  (sista grundade sampel 51, perp −459): min d(ring) 368 nås i luften rakt över
  gropen (sampel 73, dPit 45), varpå botten VÄNDER i luften (x,y-riktningsbyte)
  och faller +163 u BAKÅT mot quadsidan, ned i MH-gropen vid (751, 112).
- **Humansignaturen för klassen claimet åberopar** (67 genuina band-ramla,
  `human_ledge_v51_validation.json`): median 5 grundade in-ledge-sampel
  (p90 = 24), uthållig bandnärvaro. Ep5: 0 grundade, en båge. De 28 % mänskliga
  ramla utan grundade in-ledge-sampel är 51 ms-undersamplade bhop-kedjor —
  ep5 på 26 ms visar entydigt en enda båge utan nedslag.
- Plattformsvistelsen (sampel 5–16, 11/12 grundade) är äkta markkontakt men
  ligger i modellcirkelns yttersta rand (d(quad) 232–258 av 260) på golv som är
  kontinuerligt med spawnledgen, perp −165..−228 — botten var aldrig närmare
  plattformscentrum än 232 u. Godtagbart som källvillkor, men noterbart.

Rätt bokföring: axial/okvalificerad gropkorsning (som ep8). Beteendemässigt är
ep5 ett steg UPP från ep8 — ansats från SO-sidan, 283 u verklig progression,
riktigt avstamp — men det är inte en SO-ledgekorsning.

## A) v5.1-driftgranskningen — UNDERKÄND (JUSTERA)

1. **Falsk regressionsuppgift:** "traj_53G ⇒ allt 0, axiala 0" stämmer inte.
   Uppmätt: **ring→quad NV 1 retreat** (ep 14, transit sampel 2087–2215).
   Eventet faller vid granskning: källplattformsvistelsen är helt luftburen
   (0 av 41 sampel grundade — bhop-passage genom ringcylindern), 83 % av massan
   från |perp|>300 (upp till +636; loop ut till dPit 791, nära hexgränsen 800),
   0 grundade in-ledge-sampel, progression med 5 u marginal (d 445 < 450), och
   återvändo +134 u. En gårdsloop i NV-ytan, inte ett korsningsförsök.
2. **Ny-event-kanalen är omätt i mitt villkor:** på humankohorten ger v5.1
   **105 gate-event utan v4-motsvarighet** (+14 % utöver 744), alla med
   min_d_band i [350, 450). Blandad sammansättning: genuina partiella försök
   (t.ex. demo 22382 slot 4: 46/46 grundade in-ledge-sampel, retreat) OCH
   gårdsloop-/överflygningsklassen (flera med 0 grundade in-ledge). På
   botdumparna är kanalens utfall 2/2 falska (ep5, ep14).
3. **Grundorsaken är geometriproxyn, inte trösklarna:** perp-bandet 100–300 på
   z 40–130 inkluderar gropens LUFTRUM (gropcentrum ligger själv på perp −150),
   och massan ackumulerar obegränsat från |perp|>300. Att strama trösklarna
   räcker inte: ep5/ep14:s in-ledge-massa ensam (128/230 u·s) överstiger ändå
   14 u·s.

### Krav för drift (v6)

a. **Ledgemask i stället för perp-band:** ledgenärvaro, sidomassa och
   progression räknas endast i sampel vars 2D-position ligger i den uppmätta
   ledgevoxelmängden (probens 1031 stödda OPEN-centers, |perp| 100–300,
   z 48–112) — förutsatt att mängden är stödfiltrerad; annars generera stödda
   ledgeceller ur BSP:n. Detta eliminerar gropluftrum (ep5) och gårdsband
   (ep14) i ett slag; trösklarna 450/14 kan då stå kvar oförändrade.
b. **Källplattformen kräver ≥1 grundat sampel** i vistelsen före lämningen
   (ep14: 0/41; ep5: 11/12 OK; ep8: 8 OK). Obs: på 51 ms-humandata kan kravet
   kosta bhop-passager — validera retention innan det appliceras på humandata;
   för botdumpar (26 ms) är det säkert.
c. Omvalidering efter a+b: `human_ledge_v51_validation.py` (uppdaterad mask) —
   krav: bibehållen retention av 65/67-klassen och 646/646, PLUS att de nya
   105 renodlas (gårdsloopklassen med 0 grundade in-ledge → axial), PLUS
   botregression: probe_ledge_60G ⇒ sidogates 0, axial 2 (ep5+ep8);
   traj_53G ⇒ sidogates 0.

## Mätkommandon

```
cd ~/rex-ml
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ledge_60G.json
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/traj_53G.json   # OBS: ring→quad NV = 1
PYTHONPATH=. sim/.venv-sf/bin/python evidence/repro/vet_v51_events.py ~/dumps/probe_ledge_60G.json 5
PYTHONPATH=. sim/.venv-sf/bin/python evidence/repro/vet_v51_events.py ~/dumps/traj_53G.json
.venv/bin/python evidence/repro/human_ledge_v51_validation.py
```

Konfidens: **hög** för båda domsluten (ballistik, grundad-flaggor, massdekompo-
sition och humanjämförelse pekar samstämmigt; alla spår assert-verifierade mot
detektorn). Osäkerhet redovisad: fysiska plattforms-/ledgegränser är modellerade
(cirkel/band), inte BSP-verifierade — därav krav a.
