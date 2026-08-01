# Analytikergranskning: jump_gates-detektorns utfall (VETO-review)

**Granskare:** DM3-analytikern (analyst.md)
**Datum:** 2026-08-01
**Granskat:** `rl/jump_gates.py` mot `evidence/jump_gates_latest.json` (30 greedy-episoder à 60 s, ckpt ~3.45G, path = var 2:a tick = 26 ms)
**Metod:** Instrumenterad återkörning av detektorns exakta logik på bottens trajektorier
(`scratchpad/vet_jumpgates.py`, utdata `scratchpad/vet_jumpgates_out.json`) samt mänskliga
referensmätningar ur store-dm3 (908 M-samplekorpusen, mvd/4on4/dm3, 77 Hz):
samma detektorkod körd på 60 slumpade demos (`scratchpad/human_detector.py`), z-bandsbeläggning
och radialprofiler kring plattformarna, samt spelarposition vid 4 000 riktiga RA- och
4 000 SNG-mega-pickups (item_events `taken` joinat mot trajectory_samples, ±80 ms).

Alla siffror nedan är uppmätta, inte uppskattade.

---

## Verdikt per claim

### 1. quad→ring NV "5 försök/0 lyckade/5 retreat" och quad→ring SO "7 försök/4 ramla/3 retreat" — **UNDERKÄND**

De 12 registrerade segmenten är inte ledge-transitförsök mot ringplattformen. Uppmätt:

- **Alla 12 startar i samma fysiska korridor** direkt SV om quad-cirkelns rand
  (ledge-första-punkt x 685–791, y 85–437, z 56–99). Golvet där är kontinuerligt
  (z = 56 exakt, med ramp upp till 99,8) — detektorns "ledge" är här vanligt
  plattformsplan som råkar ligga utanför PLAT_R = 260.
- **Ingen av de 12 närmar sig ringen.** Minsta 2D-avstånd till ringcentrum under
  segmenten: 388–563 u (målregionens rand ligger på 260). Transitsträckan är 784 u
  mellan centra; botten kommer aldrig ens halvvägs.
- **Mänsklig referens visar att cirkelranden går mitt i golvet:** mänsklig trafik på
  plattformsnivå (z 40–130) *ökar* utanför r = 260 (quad: 7,5 M samples i bandet
  240–280 u mot 3,4 M i 40–80; ring: 9,4 M i 280–320). Att korsa r = 260 är normal
  förflyttning på sammanhängande golv, inte ett hoppförsök.
- **"Ramla"-utfallen (4 st) ser ut som bottens ordinarie grop-rutt, inte misslyckade
  ledge-hopp:** efter fallen fortsätter botten mot MH i gropen (min 2D-avstånd till MH
  46–167 u inom 2 s; ep19 når 46 u från MH och därefter 246 u från ringcentrum —
  dvs. quad→grop→ring-nedre-cirkulationen som även syns i episodernas ruttloggar).
- **NV/SO-klassningen är instabil:** 3 av 12 events har första ledgepunkten på motsatt
  sida om ring→quad-axeln jämfört med sin etikett (t.ex. ep28-event i0=167 klassat SO
  med ledge-start (701.9, 224.7) = +39,9 u på NV-sidan). 10 av 12 startar inom ±125 u
  vinkelrätt från axeln där tecknet på kryssprodukten är brus.

### 2. ring→quad NV+SO "0 försök" — **GODKÄND som siffra, UNDERKÄND som asymmetri-tolkning**

Detektorbias är uteslutet: samma kod på 60 mänskliga demos registrerar alla fyra
gaterna rikligt (ring→quad 6 915 försök, quad→ring 8 698; båda riktningarna, båda
sidorna). Asymmetrin i botutfallet är **beteende**, men den korrekta beskrivningen är
starkare än "försöker aldrig ring→quad":

- Botten har **0 samples på plattformsnivå (z > −20) i ringregionen** under samtliga
  30 × 60 s. Den tillbringar i stället 140,8 s i gropen (z ≤ −100) under/vid ringen.
  Ruttloggarnas "vid ringen" är gropnivå. Även quad-plattformsnivå är marginell: 11,2 s.
- Detektorn tilldelar `cur='ring'` nere i gropen (2D-cirkel utan z-villkor): 234
  kandidattransiter "ring→quad ramla" filtrerades bort enbart av onto_ledge-villkoret.
  Rätt slutsats blev rätt av delvis fel skäl.
- Konsekvens: botten gör **inga genuina ledge-transitförsök i någon riktning**. Att
  rapportera "12 försök quad→ring, 0 ring→quad" ger ägaren en falsk bild av begynnande
  hoppmedvetenhet.

### 3. RA-tagningen "95 försök/0 lyckade" — **KORRIGERAS: pickup-kriteriet godkänt, försöksräkningen underkänd, "0 lyckade" bekräftat beteende**

- **Pickup-boxen är geometriskt riktig.** Vid 4 000 riktiga mänskliga RA-pickups:
  2D-avstånd p50 = 42,5, p99 = 61,7; dz p50 = +24,0 (spelarorigin 24 u över itemorigin
  — bekräftar z-konventionen), max +79,8 (= QW:s touch-tak pz−iz < 80). 88 % (3 523/4 000)
  faller inom boxen (2D < 60 ∧ |dz| < 56). Bortfallet är hoppgrepp med dz 56–80.
  Rekommendation: vidga dz till (−32, +80); 2D < 60 behålls.
- **"0 lyckade" är äkta beteende, inte kriteriefel.** Botten gör noll höjdvinst mot RA:
  z_max i de 95 intervallen: p50 = 43,8, p90 = 59,8, absolut max = 152 (ett intervall
  som *inträdde* på 152 uppifrån och föll). RA kräver ~304. Ingen klättring påbörjas.
- **"95 försök" är inflaterat.** Attempt-predikatet (någon punkt z < 150 inom 2D < 300)
  triggar på varje passage genom RA-nedre/NG-tunneln — botten pendlar tele↔RA-nedre
  (95 av 96 regionsbesök blev "försök"). Det mäter korridortrafik, inte klätterförsök.
  Mänsklig referens: 3 115 genuina ralow→ratop-klättringar i 1 609 demos, median 5,4 s,
  medelklättringstakt 51 u/s — förslag: kräv uppmätt uppåtprogression, t.ex.
  z_max ≥ inträdes-z + 80 inom regionen, innan "försök" räknas.

### 4. SNG-mega "2 försök/0 lyckade" — **GODKÄND med anmärkning (beteende, inte kriterium)**

- Pickup-boxen fångar 99,9 % (3 997/4 000) av riktiga mega-pickups (2D p99 = 44,6,
  dz p50 = +24, max +42,5). Kriteriet är korrekt.
- Beteendet bekräftat: 163 approach-intervall, 161 helt under hyllnivån (z −16…28;
  megan på 160). De 2 "försöken" inträdde redan högt (z_entry 162,5 resp. 115,2 —
  ankomst via övre gången, inte upphopp) och nådde aldrig närmare än 92,8 u.
  Mänsklig referens: sng→mega är rutin (5 868 transiter i 1 970 demos, median 2,1 s).
- Anmärkning: nivå 1 ("försöker") är generöst — de två intervallen är inte hoppförsök
  mot megan. Sant mognadsläge är 0/1-gräns. Föreslå attempt = (z > 100 ∧ 2D < 200)
  eller uppåtprogression från SNG-golvet.

---

## Föreslagna detektorkorrigeringar (med siffror)

1. **z-banda plattformsregionerna:** på-plattform = 2D < 260 ∧ z ∈ (40, 130).
   Tar bort grop-som-plattform-artefakten (234 fantomkandidater ring→quad; 140,8 s
   "vid ringen" som i verkligheten är grop).
2. **Progressionskrav för transitförsök:** registrera försök endast om segmentet når
   2D-avstånd < 350 till destinationens centrum på z > −20 (dagens 12 events: 388–563
   — samtliga faller bort; mänskliga lyckade passager når per definition < 260).
3. **Sidoklassning:** klassa på ledgepunkten med störst vinkelrät distans från axeln,
   med dödzon |perp| < 100 → "obestämd". (3/12 nuvarande etiketter motsäger sin egen
   ledge-startpunkt.)
4. **RA-attempt:** kräv z_max ≥ z_entry + 80 inom approach-regionen (mänsklig klättring
   ger +280 på median 5,4 s). **RA-pickup dz:** (−32, +80) i stället för ±56.
5. **Mognadsnivå 3 är onåbar som definierad:** samma detektor ger eliten 8–44 %
   "lyckandegrad" per försök (quad→ring NV 8 %, SO 19 %, ring→quad NV 44 %, SO 22 %,
   60 demos) eftersom försöksdefinitionen fångar strid/meander vid randen. Efter fix
   1–3: ommät den mänskliga lyckandegraden och sätt nivå 3 relativt den (t.ex. ≥5
   lyckade ∧ andel ≥ mänsklig median), annars kan ingen agent — inte ens människor —
   någonsin passera gaten.
6. Mindre: bottdumpens z är golvnivå (bot står på 56,0 = itemhöjd) medan korpusens z är
   spelarorigin (golv + 24). Skillnaden (24 u) är ofarlig för alla nuvarande trösklar
   men bör dokumenteras i detektorn.

---

## Slutsats

**Ingen av gate-hopp-claimerna får presenteras för ägaren i nuvarande form.**
Det enda som håller är de negativa resultaten: botten tar aldrig RA (bekräftat, hög
konfidens — den påbörjar inte ens klättringen), når aldrig SNG-megan (bekräftat), och
gör inga genuina ring↔quad-ledgetransiter i någon riktning (bekräftat — 0 s på
ringplattformsnivå över 30 minuter). De positiva talen ("12 försök", "95 försök",
nivå 1 på fyra gater) är detektorartefakter: cirkelränder mitt i sammanhängande golv,
attempt-predikat som räknar passager, och en sidoklassning som är brus nära axeln.
Sann mognadsstatus enligt ägarens stege är **nivå 0 på samtliga sex gater** tills
detektorn korrigerats (punkt 1–5) och ommätning gjorts.

Konfidens: Hög. Samtliga slutsatser stöds av minst två oberoende ytor (bottens råspår +
mänsklig korpus genom identisk detektorkod, itemevents + trajectory_samples).

**Reproduktion:**
`scratchpad/vet_jumpgates.py` (bot, exakt detektorlogik, full segmentlogg),
`scratchpad/human_detector.py 60` (människa, seed via hash(demo_key)),
pickup-join: item_events taken × trajectory_samples ±80 ms, n = 4 000 per item.

---

## Appendix: Re-review av korrigerad detektor (2026-08-01, andra passet)

Koordinatorn implementerade punkt 1–5 i `rl/jump_gates.py`; nya utfall på samma dump:
alla ring↔quad-gater 0 försök, SNG-mega 0 försök, RA 1 försök/0 lyckade (nivå 1).

**(a) Kodgranskning: implementationen följer specen.** z-band (40,130) i `_plat`,
progressionskrav d(dst)<350 på ledgepunkter (lyckat ⇒ progressed per definition — OK),
normerad sidodödzon ±100 u, klätterkrav z ≥ z_entry+80, pickup-dz (−32,+80). Två
restnoteringar utan påverkan på dagens siffror: (i) om alla ledgepunkter ligger i
dödzonen blir side_acc = 0 → etiketten defaultar till "SO"; bör bli "obestämd" den dag
events åter registreras. (ii) `low` sätts av valfri punkt i intervallet, inte entrén —
ofarligt nu, men ett högt inträde som droppar och studsar +80 över entré-z kan i
teorin räknas.

**(b) Det kvarvarande RA-försöket är en falsk positiv.** Uppmätt (ep29, i 0–71, 1,85 s,
spawn "vid RA-toppen"-zonen): botten går från (432,−848,56) norrut och klättrar sedan
**trappan västerut mot tele** — klättervillkoret triggas vid (205.6,−528,136) medan
2D-avståndet till RA *ökar* (min 157,3 u vid i=41, därefter 157→299 under själva
klättringen; utträde på z=152 mot tele, helt i linje med ruttloggen RA-toppen↔tele).
Äkta höjdvinst (+96), fel riktning: ingen klätterstart mot armorn. En mänsklig
RA-klättring når per nödvändighet 2D < ~50.
**Korrigering:** kräv dessutom `d2_min < 120` i intervallet för RA-försök (dagens
intervall: 157,3 → bortfiltrerat ⇒ RA 0 försök, nivå 0). Mänskliga klättrare passerar
trivialt (pickup-d2 p99 = 61,7).

**(c) Verdikt:**
- Nollorna (ring↔quad 4 × 0, SNG-mega 0): **GODKÄNDA** att presenteras som
  analyst-granskade. De speglar uppmätt beteende korrekt.
- "RA-tagningen nivå 1 (försöker)": **UNDERKÄND** — den enda försökssignalen är en
  tele-trappa i fel riktning. Presentera **nivå 0 på samtliga sex gater**, alternativt
  inför d2_min-filtret ovan och kör om (ger 0/0 mekaniskt).
- Detektorn i övrigt: godkänd som mätinstrument för fortsatt curriculum-spårning,
  med påminnelsen att nivå 3-definitionen (100 % av ≥5) fortfarande ska rekalibreras
  mot mänsklig lyckandegrad när botten väl börjar registrera riktiga försök.
