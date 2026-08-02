# DELVIS GODKÄND — nivå 2-claimet ("lyckas ibland") UNDERKÄNNS: dumpens enda "lyckade" SO-event är en runtomrutt via ytterkantsgolvet med luftburen maskgraze, inte en gapkorsning; SO-RAMLA-eventet (ep4) GODKÄNNS som första verifierade genuina hexagon-gateFÖRSÖKET (korrekt bokföring: ring→quad SO 1 försök / 0 lyckade / 1 ramla ⇒ nivå 1)

## Vetogranskning av genombrottsclaimet, traj_63G @6.35G

Analyst, 2026-08-02. Detektor: `rl/jump_gates.py` v6.1 (oförändrad).
Data: `~/dumps/traj_63G.json` (10 ep × 2310 sampel à 26 ms, slumpade spawns,
policy gate2_v2 @6.35G). Repro: `evidence/repro/breakthrough_63G_extract.py`
(instrumenterad kopia av `_ring_quad_events`, assert-paritet mot driftdetektorn:
SO {2,1,1,0}, axial {2,1,1,0} — claimets siffror reproducerade exakt) med
eventdump `evidence/repro/breakthrough_63G_events.json`, samt
`evidence/repro/breakthrough_63G_ra_check.py` (RA-noteringen).
Humanjämförelse: `evidence/repro/human_ledge_v61_final.json` (768 gate-event;
584 lyckade, 151 ramla).

## Domslut per event

### Event 1 — "ring→quad SO lyckat", ep1, transit sampel 187–249 (1.61 s): UNDERKÄND

Banan korsar ALDRIG SO-gapet (d_ring 330–555 i ledgebandet |perp| 100–300).
Uppmätt förlopp (se traj_pts i eventdumpen):

- Sampel 187–198: lämnar ring på SO-sidan, luftburen, driver ut ur bandet
  (perp −211 → −295) och vidare förbi bandgränsen.
- Sampel 204–207: **grundad på ytterkantsgolv z=56 vid perp −335…−357,
  d_ring 455–488** — dvs. gapets d_ring-intervall passeras PÅ GOLV utanför
  ledgebandet (dumpens egen zonetikett för detta golv: "vid mega"-gången,
  ep8 spawnar på exakt (912,−48.5,56) med den etiketten; gate2-zonklass
  "constrained-misc").
- Sampel 208–232: bunnyhop längs ytterkanten (perp ner till −430, d_ring upp
  till 711), landar igen på z=56 vid (942,−124)…(945,−57).
- Sampel 240–249: slutannalkande mot quad söderifrån; **samtliga 7 masksampel
  (242–248) är LUFTBURNA** graze-sampel över quadsidans ledge (d_quad 260–318,
  d_ring 671–700 — enbart på gapets BORTRE sida). All sidomassa (45.6 u·s)
  kommer härifrån. 0 grundade masksampel i transiten.

Ankomsten i sig är äkta plattformsvistelse (landning z=56 sampel 265,
9 grundade quadsampel 266–274, vistelse 0.78 s) — det är alltså ingen
touch-and-fall, men det som ankommer är en perimeterrutt runt gropen, inte en
ledgekorsning. Mot de 584 lyckade humaneventen: massa 45.6 u·s < p10 för
SO-lyckade (50.9, p50 112.3), maskkontakttid 0.18 s mot human p50 0.41 s
(n_mask 7×26 ms mot 8×51 ms; transittid saknas i humanartefakten), och
0 grundade masksampel (22.7 % av humana SO-lyckade har också 0 — skalärerna
ensamma fäller inte eventet; det är **topologin** som fäller det: gapet
passerades inte). Detta är exakt granskningsvillkorets uteslutningsfall
("runt … med maskgraze"), fast via ytterkanten i stället för axeln.

Spawn-artefaktkontroll: ep1 spawnar "vid quad" (496,559.5,56) vid sampel 0;
eventet börjar 4.9 s in med grundad ringvistelse (14 grundade sampel 164–177).
Ingen spawn-artefakt.

### Event 2 — "ring→quad SO ramla", ep4, transit sampel 1099–1142 (1.12 s): GODKÄND (genuint gapförsök)

- Källvistelse: ring 1049–1098 (1.27 s, 10 grundade sampel); eventet ligger
  28,6 s in i episoden (spawn "vid ringen" sampel 0) — ingen spawn-artefakt.
- Avfärd: **3 grundade masksampel (1099–1101) på SO-ledgens golv z=56**
  (perp −258…−273) — förankringen är äkta ledgevistelse, inte graze.
- Korsning: spåret ligger i bandet hela vägen (perp −258…−295), upphopp med
  apex z 99.8 vid d_ring ≈ 305, in över gapzonen (masken tar korrekt slut vid
  d_ring 305 < gapstart 330), faller under plattformsnivå vid d_ring 419 och
  når gropdjup (z −101) vid **d_ring 544.8 — 10 u från gapets bortre kant
  (555)**. Gapet passerades nästan i sin helhet; för lite fart/för tidigt
  upphopp.
- Mot humanramla (n=151): 3 grundade masksampel (human p10 2, p50 8),
  massa 110.0 u·s (p10 36, p50 132), min_d_all 403.3 (p50 333, p90 434),
  förankrad (human 100 %). Inom humanfördelningen på samtliga mått.

Detta är det första verifierade genuina hexagon-gateförsöket i någon botdump
(tidigare regressioner: probe_ledge_60G, traj_53G, traj_0907 = 0 sidogates).

### Event 3 — "axial quad→ring ramla", ep1, sampel 280–315: KORREKT BOKFÖRD (informationsspår)

Direkt efter event 1-ankomsten vänder boten och hoppar rakt tillbaka längs
axeln (perp −35…+7, helt i dödzonen, 0 masksampel, sidomassa 0) och landar i
gropen vid (357.5,−9.4,−101). Äkta axialt gropfall; ingen gate, ingen dom krävd.

### Event 4 — "axial quad→ring lyckat", ep8, sampel 455–476: UTFALLSARTEFAKT (i sak ramla)

"Lyckat" räknades på ETT enda fallande sampel: 476 = (479.4,64.7,40.9) med
d_ring 258.2 (1.8 u innanför PLAT_R 260) och z 40.9 (0.9 u över z-bandsgolvet
40), vertikalfart ≈ −7.7 u/sampel. Sampel 477–494 fortsätter fallet förbi
plattformskanten ner till z −200 i gropen — ingen landning på ring sker.
Substantiellt är axialspåret alltså {2 försök, 0 lyckade, 2 ramla}, inte
{2,1,1}. Påverkar inte gatenivåerna (axial är informationsspår) men ska inte
presenteras som "lyckad axialkorsning".

## Korrigerad bokföring av dumpen

| | detektor v6.1 | granskad substans |
|---|---|---|
| ring→quad SO | 2 försök, 1 lyckat, 1 ramla ⇒ nivå 2 | **1 försök, 0 lyckade, 1 ramla ⇒ nivå 1 ("försöker")** |
| axial | 2 försök, 1 lyckat, 1 ramla | 3 försök, 1 lyckat (ep1-runtomrutten), 2 ramla |

## Två detektorluckor exponerade (åtgärdsförslag, kräver humanrevalidering före ändring)

1. **Lyckat-utfallet saknar landningsbekräftelse.** `outcome="lyckat"` sätts på
   första samplet där `_plat(q)==dst` — ett fallande sampel som grazar
   plattformscylinderns nedre kant (ep8: 0.9 u/1.8 u marginal) räknas som
   ankomst. Förslag: kräv ≥1 grundat sampel på dst-plattformen inom ~0.5 s
   efter ankomstsamplet (ep1-ankomsten klarar det: 9 grundade; ep8 faller).
2. **Lyckat-utfallet saknar förankrings-/gapzonskrav.** v6.1:s förankrat
   fall-krav gäller bara ramla; för lyckat räcker luftburen maskgraze +
   massa ≥14 u·s — en perimeterrutt utanför bandet (grundad på
   ytterkantsgolvet genom hela gapintervallet) passerar som gate-lyckat.
   Förslag: kräv masksampel på BÅDA sidor om gapet (axialprojektion), eller
   att transitens grundade sampel utanför plattformarna ligger i masken (inte
   på golv utanför bandet). OBS: rakt förankringskrav på lyckat skulle fälla
   upp till 25 % av humanlyckade (andel med 0 grundade masksampel) — mät
   humanretention innan regeln ändras.

## RA-noteringen (punkt 4 — ingen dom, kontroll utförd)

RA-gatens nolla är KORREKT och beror INTE på grundat-kravet.
`evidence/repro/breakthrough_63G_ra_check.py`: i hela dumpen finns **0 sampel**
(grundade eller luftburna) som uppfyller klättring ≥ +80 över entré-z OCH
d2 < 120 SAMTIDIGT. Närhetsmätarens rubriktal kommer från OLIKA besök och
uppfyller vardera bara ett villkor: +202-klättringen (ep3, [2106,2225]) sker
på d2 ≥ 176 (klättring bort från RA), och d2 64.5-närheten (ep6, [782,897])
är en luftburen hoppbåge med zvinst +44 på låg nivå. `rl/jump_proximity.py`
aggregerar `zvinst_max` och `d2min_elev_best` över besök var för sig —
korrekt som förstadieindikator, men paret får inte läsas som ett gemensamt
sampel. Förbättringsförslag (ej fel): rapportera per besök det bästa
GEMENSAMMA paret (zvinst, d2) så att felläsningen blir omöjlig.

## Repro

```
cd ~/rex-ml
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/traj_63G.json
  # ⇒ ring→quad SO {2,1,1,0} nivå 2, axial {2,1,1} (claimet reproducerat)
PYTHONPATH=. sim/.venv-sf/bin/python evidence/repro/breakthrough_63G_extract.py ~/dumps/traj_63G.json
  # ⇒ 4 event + detektorparitet-assert; eventdetaljer i breakthrough_63G_events.json
PYTHONPATH=. sim/.venv-sf/bin/python evidence/repro/breakthrough_63G_ra_check.py ~/dumps/traj_63G.json
  # ⇒ 0 sampel med gain>=80 & d2<120 i hela dumpen
```

Konfidens: hög (banorna i sin helhet inspekterade sampel för sampel; human-
jämförelsen mot den låsta v6.1-baslinjens 768 event; detektorparitet assertad).
