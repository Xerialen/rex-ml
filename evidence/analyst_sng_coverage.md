# DM3-analytikern: SNG-fällan, täckningens geografi och 70 %-kravets realism

Datum: 2026-08-01. Analytiker: dm3-analyst. Kohort: hela MVD-korpusen via
`~/dm3-extract/store-dm3/trajectory_samples` (907 977 350 rader, 2 785 dm3-demon,
4on4). Alla mätningar i detta dokument är gjorda med duckdb 1.5.5 direkt mot
parquet-storen; skripten kördes i sessionens scratchpad (`regions.py`,
`sng_exits.py`, `sng_exits2.py`, `sng_report.py`, `windows.py`, `coverage.py`) —
alla parametrar som krävs för reproduktion står angivna nedan.

Viktig datanot: kolumnen `h` i trajectory_samples är **höjd över golvet** (0 =
markkontakt), INTE fart. All fart nedan är beräknad ur positionsdifferenser
(`sqrt(dx²+dy²)/dt`, endast par med 5 ≤ dt ≤ 50 ms respektive dt ≤ 150 ms för
passager). Vyvinklar (`vya`) är i Quake-enheter (65536 = 360°).

---

## Uppdrag 1 — Hur människor LÄMNAR SNG-rummet

### Fråga och omfattning
Agenten (gate2_v2) fastnar i 2–4/10 episoder som startar vid SNG: 60 s orbit i
~460 UPS utan att lämna rummet. Vad gör människor efter ankomst till samma rum?

### Metod (reproducerbar)
Rumsdefinition härledd ur golvhöjdskartan över voxelrastret
(`pipeline/out/gate2/voxel_classes.npz`) + gate2-zonerna sng/sng-2..5/mega-sng:

```
I_RUMMET := -1000 <= x <= -336 AND 0 <= y <= 784 AND -128 <= z <= 400
```

Passage = två på varandra följande sampel för samma (demo_key, slot) med
dt ≤ 150 ms och 3D-steg ≤ 250 u där I_RUMMET växlar. Livsbrott (död/tele/
trackglapp) = dt > 400 ms eller 3D-steg > 250 u. Destination = position +2 s
efter exit (ASOF-join, krav på sampel inom [t+1,5 s, t+2,1 s]); teknik-lookback
= position/vinkel 0,6 s före exit. 2 626 av 2 785 demon har rumsbesök.

### Fynd (observerat)

**Volym:** 249 791 rumsintervall, 245 682 kontinuerliga entries, 229 458 exits.

**Vistelsetid efter ankomst (intervall med kontinuerlig entry, n = 245 682):**

| p25 | median | p75 | p90 | p99 | max |
|---|---|---|---|---|---|
| 1,4 s | **2,6 s** | 5,3 s | 7,5 s | 17,3 s | 194,8 s |

- Andel vistelser > 30 s: **0,21 %**. Andel > 60 s: **0,024 %** (1 på ~4 200).
- 7,3 % av entries slutar med livsbrott inne i rummet (död/tele), resten går ut.
- Mänsklig fart inne i rummet (n = 35,4 M sampelpar): median 338 UPS, p75 411,
  p95 489. Agentens 460-orbit är alltså *snabbare än mänsklig p75 i rummet* —
  problemet är inte fart utan att människor behandlar rummet som **transit
  (2,6 s)**, inte som vistelseyta.

**Exitvägar (n = 229 073 med lookback; portalkoordinater = rumsgränsen):**

| portal | läge (gräns, spann, z) | andel | med. fart | luft-andel | med Δyaw 0,6s | teknik |
|---|---|---|---|---|---|---|
| S-korridoren (mot spawn1/RA-låg/t2-tele) | y=0; x −1000..−820; z −64..64 | **39,4 %** | 336 | 46 % | 29° | rak löpning + fall (Δz −89 u sista 0,6 s) |
| N-övre korridoren | y=784; x −960..−832; z 64..192 | **25,7 %** | 431 | 57 % | 42° | upphopp: 14,2 % steg >24 u sista 0,6 s (norra hyllan, gate2-zon `sng-5`) |
| E-nedre-syd-dörren | x=−336; y 192..320; z −64..0 | **15,1 %** | 329 | 0,6 % | 129° | markbunden, **skarp krök** (dörrpost, gate2-zon `sng-3`-hörnet) |
| E-övre-syd-ledgen (mot quad/lifts) | x=−336; y 256..560; z 64..192 | **11,8 %** | **470** | **80 %** | 72° | **hoppexit** — snabbaste porten; ägarens sng→quad-rutt startar här (`sng_to_quad_route.json`, start (−519, 494, 120)) |
| E-nedre-norr-dörren | x=−336; y 704..784; z −64..0 | **5,0 %** | 363 | 1,7 % | 98° | markbunden, krök |
| E-övre-norr-ledgen | x=−336; y 600..784; z 64..192 | **3,1 %** | 395 | 61 % | 29° | hopp/ledge |

**Destination +2 s (närmaste ruttgrafnod):**
- S-korridoren → spawn5 34 %, ring 29 %, spawn1 28 % (korridoren mynnar i
  västhubben RA-låg/t2-telen; ring-andelen är till stor del tele-kedjan
  `tele_sng_in → tele_sng_out` vid (224,−320)).
- N-övre → 94 % kvar i sng-Voronoi (korridoren löper längs rummets norrkant på
  z≈96 innan den viker öster mot quad-övervåningen).
- E-övre-syd → spawn6 62 %, mega_sng/ring/quad — dvs. mot quad-gårn/lifts.
- E-nedre-dörrarna → gården öster om rummet (spawn6/sng-gräns).

**Entryvägar (samma portaler):** N-övre 95 665, S-korridoren 86 920,
E-nedre-syd 29 906, E-övre-norr 25 614 (människor **släpper sig ner** i rummet
från lifts-ledgen: 25 614 entries mot 7 067 exits där — asymmetrin visar att
E-övre-norr är en in-väg, inte ut-väg), E-övre-syd 4 966, E-nedre-norr 2 607.

### Taktisk tolkning
Människor går in i SNG-rummet för SNG/mega och lämnar inom 2–3 s via närmaste
portal i färdriktningen. Två portaler kräver ingen teknik alls (E-nedre-dörrarna:
markbunden rak löpning + en krök på ~100–130°), en kräver bara ett fall
(S-korridoren, 39 % av alla exits), och de tre snabba/övre kräver ett hopp.
Ingen exit kräver simning, tele eller hiss. Den värdemässigt bästa exiten för en
täckningsagent är **S-korridoren** (störst andel, leder till västhubben som
kedjar vidare till RA-låg/ring/tele = nya regioner), följd av **E-övre-syd-
ledgen** (hoppexit i 470 UPS rakt mot quad-gården).

### Validering
- Flödesbalans: 245 682 entries ≈ 229 458 exits + 7,3 % livsbrott inne — konsistent.
- Portalpositionerna är empiriska kluster (64 u-binning av passagepunkter), inte
  antaganden; 1 ensam passage föll utanför klustren ("ovrigt").
- Känslighet: dörrbanden i y/z är skarpa i histogrammen (nollrader mellan
  portalerna), så rumsboxens exakta kanter påverkar inte andelarna nämnvärt.
- Konfidens: **Hög** (multipla ytor: passager, intervall, destinationer stämmer
  inbördes och mot ägarens inspelade sng→quad-rutt).

---

## Uppdrag 2 — De återstående ~50 procentenheternas geografi

### Metod
Universum = exakt `rl/zones.py`-definitionen: 12 012 nåbara OPEN-voxlar
(REACHABLE_LEVELS=3, verifierat mot `ZoneRaster`: n_open_reachable = 12012).
Regiontilldelning: närmaste ruttgrafnod (`evidence/route_graph.json`, 3D,
z-viktad 1,5×; tele-noder borttagna). Mänsklig trafik per voxel = `n` i
`voxel_classes.npz` (898,9 M fartfiltrerade sampel). Skördstakt = unika
universumvoxlar per sekund närvaro, mätt i 1 732 giltiga slumpade 60 s-fönster
(se Uppdrag 3). "Mänsklig 30-run-täckning av regionen" = medel över 200
replikat av 30×60 s-unioner.

### Fynd: regiontabellen (sorterad efter universumandel)

| region (närmaste nod) | voxlar | % av universum | % av mänsklig trafik | skörd vox/s | mänsklig 30-run-täckn. av regionen | åtkomstkrav |
|---|---|---|---|---|---|---|
| sng (rummet) | 1 629 | **13,6** | 4,9 | 10,2 | 28,7 % | 6 portaler, se Uppdrag 1 |
| mega_hill | 1 141 | 9,5 | 6,8 | **10,6** | 41,8 % | gård — agenten är redan här |
| quad | 1 139 | 9,5 | 9,7 | 10,2 | 52,8 % | gård — agenten är redan här |
| pent | 973 | **8,1** | 2,6 | 8,1 | **28,8 %** | fall ner; retur via trappa öster (gate2-zon `ssg-ya-2`) eller hissar (exkl.) |
| ralow_ng | 950 | **7,9** | 7,0 | 9,4 | 37,1 % | golvplan, inga hinder; NG-tunnelschaktet kräver hopp |
| ssg_ya | 839 | **7,0** | 7,7 | **10,6** | 43,9 % | platt gård öster |
| mega_pent | 782 | **6,5** | 4,9 | 9,2 | **27,0 %** | fall från RL/ssg-ya; retur via östtrappan |
| ring | 656 | 5,5 | 7,8 | 7,2 | 46,4 % | gård/bro — agenten är redan här |
| ya | 648 | 5,4 | 7,3 | 8,5 | 42,3 % | platt gård öster |
| spawn4 (RL-huset/fönstret) | 485 | 4,0 | 7,0 | 6,5 | 48,9 % | dörrar + fönsterpassage (zon `window`, mänskligt tak 305 UPS) |
| spawn6 (quad-övre) | 469 | 3,9 | 3,2 | 6,0 | 42,2 % | gård/avsats — agenten är redan här |
| ratop | 449 | 3,7 | 7,6 | 5,4 | 50,0 % | ramp-/trappklättring till z 288 |
| spawn2 (gårdsgolv S) | 356 | 3,0 | 2,9 | 9,6 | 33,0 % | gård — agenten är redan här |
| mega_sng | 309 | 2,6 | 1,6 | 6,9 | 40,3 % | i SNG-rummet (hyllan z 128–192, hopp) |
| spawn3 (YA-spawnhörnet) | 274 | 2,3 | 6,7 | 5,9 | 44,8 % | platt |
| spawn1 (V-korridoren) | 263 | 2,2 | 3,8 | 8,9 | 48,1 % | korridor |
| spawn5 (SV-korridoren) | 255 | 2,1 | 3,4 | 9,7 | 44,4 % | korridor |
| lg_water | 184 | 1,5 | 2,3 | 2,0 | 66,0 % | **simning/vattennära** |
| rl | 155 | 1,3 | 2,1 | 2,8 | 27,5 % | RL-plattformen/vattenkant |
| gl_water | 56 | 0,5 | 0,7 | 1,8 | 63,7 % | **simning/vattennära** |

Nivåstruktur i universumet (avstånd över golvvoxeln): nivå 0 = 30,5 %, nivå 1 =
34,6 %, nivå 2 (64–96 u upp, kräver hopp) = **34,9 %** av alla universumvoxlar.
Människors mediantrafik på nivå 2 är 6 200 sampel/voxel (mot 28 656 på nivå 1)
— nås rutinmässigt av hoppande spel. Landningsbonusarna arbetar alltså åt rätt
håll: **frekventa hopp under löpning skördar en tredjedel av universumet som
markglidning aldrig rör.**

### Prioriterad lista för en 500–700 UPS-bot (mest nya voxlar per investerad sekund)

Gårdarna som agenten redan cirkulerar (quad + mega_hill + ring + spawn2 +
spawn6) är tillsammans bara **31,4 %** av universumet — perfekt gårdstäckning
kan aldrig ge 70 %. Resterande måste komma härifrån, i ordning:

1. **SNG-komplexet (sng + mega_sng = 16,2 %)** — agenten är redan där (det är
   fällan!). Skörd 10,2 vox/s, sex portaler. Att omvandla 60 s orbit till
   2–6 s genomresa med exit via S-korridoren/E-övre-ledgen konverterar
   dödtid till både SNG-voxlar OCH väst-/gårdsvoxlar. Störst enskild vinst.
2. **Östra YA-komplexet (ssg_ya + ya + spawn3 = 14,7 %)** — högsta skörden
   (10,6 vox/s), helt platt, nås i full fart från gårdskorridorerna eller
   YA-telen. Ingen teknik krävs.
3. **Pent-sänkan (pent + mega_pent = 14,6 %)** — näst största massan men lägst
   mänsklig 30-run-täckning (27–29 %): även människor underbesöker den. Kräver
   medvetna fall ner (z −320..−96) och retur via östtrappan (`ssg-ya-2`,
   mänskligt tak 398 UPS) eftersom hissarna är exkluderade ur gaten. Utan
   denna sänka är 70 % aritmetiskt mycket svårt (31,4+16,2+14,7+7,9+övrigt
   räcker knappt).
4. **RA-låg/NG-tunneln (ralow_ng = 7,9 %)** — golvplan, 9,4 vox/s, nås direkt
   från både S-korridoren (SNG-exit 1!) och RA-gården.
5. **RL-huset/fönsterområdet (spawn4 + rl = 5,3 %)** — dörrar och trånga
   passager (fönstrets mänskliga tak 305 UPS), medelskörd.
6. **ratop (3,7 %)** — kräver klättring men människor når 50 % av den på 30
   runs; agentens vertikala belöningar täcker redan detta beteende.
7. **Vattennära zoner (lg_water + gl_water = 2,0 %)** — kräver simning; lägst
   skörd (≈2 vox/s). Att HELT ignorera dem kostar max 2 procentenheter av 70.

### Konfidens
Medel (regiontilldelningen är närmaste-nod-Voronoi, inte rumsvis polygonindelning;
gränsvoxlar kan hamna i grannregionen — andelar ±1–2 procentenheter).

---

## Uppdrag 3 — Är 70 % ens mänskligt? (realism-sanity)

### Metod (reproducerbar)
Samma universum (12 012 voxlar, `rl/zones.py` REACHABLE_LEVELS=3 replikerad
exakt via `ZoneRaster`). 3 000 slumpade ankarsampel ur hela korpusen (duckdb
`USING SAMPLE reservoir(3000 ROWS) REPEATABLE (42)`) → fönster [t0, t0+60 s]
för den spelaren (demo_key, slot). Giltigt fönster: ≥ 3 000 sampel och spann
≥ 55 s → **1 732 giltiga fönster**. Union över 30 fönster från 30 olika demon,
200 replikat (seed 7).

### Fynd

| mått | värde |
|---|---|
| Täckning per enskilt 60 s-fönster | median **3,54 %** (p25 3,03, p75 4,04, max 5,98) |
| **Mänsklig 30×60 s-union** | **40,0 % ± 1,4** (min 36,3, p5 37,5, p95 42,2, max 43,4 över 200 replikat) |
| Fönster som krävs för 19,9 % (= agentens nivå) | **8–12** |
| Fönster som krävs för 70 % | **214–235** (≈ 3,6–3,9 timmar spel) |
| Union av ALLA 1 732 fönster (28,9 h) | **87,6 %** |

### Tolkning och validering
- **70 %-kravet är djupt övermänskligt relativt mänskligt SPEL:** mänsklig
  30-run-union ligger på 40 %, och 70 % är ~21 standardavvikelser över den
  mänskliga medelunionen. En människa behöver ~7–8× mer tid (3,6–3,9 h) för 70 %.
- Kravet är dock inte fysiskt orimligt: 87,6 % av universumet nås av mänskligt
  spel totalt sett, och de 12,4 % som aldrig träffas i fönstren är glesa
  luftvoxlar, inte otillgängliga rum. 70 % är alltså **nåbart för en agent som
  systematiskt jagar täckning** — beteendet som krävs finns bara inte i mänskligt
  4on4 (människor optimerar strid/kontroll, inte täckning; detta är en
  confounder, inte ett fysiskt tak).
- Generositetsnot åt människorna: fönstren innehåller respawn-teleporter
  (dör man flyttas man gratis till ny del av kartan). Agenten får inga
  respawns i sina 60 s-runs — jämförelsen överskattar alltså mänsklig
  "ärlig" rörelsetäckning något.
- Kalibrering av agentens läge: 19,9 % = mänsklig 8–12-fönsterunion. Agentens
  30 runs producerar i dag ungefär en tredjedel av mänskligt spels rumsliga
  spridning per run.
- Konfidens: **Hög** för siffrorna (identiskt universum, stort N), **Medel** för
  tolkningen "nåbart för agent" (extrapolation bortom observerat beteende).

### Ägarrapporteringsfakta
Om/när Gate 2 rapporteras: ange att täckningskravet 70 % motsvarar ~1,75×
den mänskliga 30-runs-unionen (40,0 %) och ~80 % av vad hela korpusens
mänskliga spel någonsin besöker (87,6 %). Kravet står — men detta är
kalibreringen av hur övermänskligt det är.

---

## De 5 viktigaste fynden

1. **Människor lämnar SNG-rummet på 2,6 s (median); >60 s vistelse är 1 på
   4 200.** Agentens 60 s-orbit är inte "långsam människa" utan ett beteende
   som i praktiken inte existerar i korpusen. Farten är inte problemet
   (agent 460 > mänsklig p75 411 i rummet) — exitbeslutet saknas.
2. **Exitfördelning: S-korridoren 39 % (fall, rak löpning, leder till
   västhubben/t2-telen), N-övre korridoren 26 % (upphopp till norra hyllan),
   E-dörrarna 20 % (markbundna, kräver bara en 100–130°-krök), E-övre-ledgen
   15 % (hoppexit i 470 UPS mot quad).** Ingen exit kräver sim/tele/hiss.
   Portalkoordinaterna står i rapporten — direkt användbara för exitriktad
   novelty/bonus.
3. **Gårdarna agenten cirkulerar är bara 31,4 % av universumet** — 70 % kan
   aldrig nås där. De tre stora saknade massorna är SNG-komplexet (16,2 %),
   östra YA-komplexet (14,7 %, platt, högsta skörden 10,6 vox/s) och
   pent-sänkan (14,6 %, kräver fall ner + trappretur; även människor
   underbesöker den: 27–29 %).
4. **34,9 % av universumvoxlarna ligger 64–96 u över golvet (nivå 2)** och nås
   bara med hopp under löpning — landningsbonusarna arbetar åt rätt håll och
   bör bibehållas/förstärkas som täckningsmekanism.
5. **70 %-kravet är ~21 SD över mänsklig 30×60s-union (40,0 % ± 1,4).**
   Människor behöver 214–235 fönster (~3,7 h) för 70 %; hela korpusens spel
   når 87,6 % totalt. Kravet är fysiskt nåbart men kräver täckningssökande
   beteende som mänskligt 4on4-spel aldrig uppvisar — viktigt kalibreringsfaktum
   för ägarrapporten. Agentens 19,9 % = mänsklig 8–12-fönsternivå.
