# JUSTERA (två trösklar; falsk-sida är löst, men v5 tappar 34 % av genuina MISSLYCKADE ledgekorsningar — in-band-progression 350→450 och massan tidsnormaliserad ≥14 u·s)

## v5-validering mot humanbaslinjen

Analyst, 2026-08-02. Detektor: `rl/jump_gates.py` v5 (oförändrad av mig).
Kohort: samma 24 demos som `evidence/repro/human_ledge_baseline.json`
(hash-ordnade demo_keys, 1 267 v4-gate-event varav 472 quad→ring).
Metod: dubbelspårning per kandidattransit (v4- och v5-kvalificering på identiska
transitgränser); v5-spåret assert-verifierat mot `_ring_quad_events` på samtliga
227 segment. Skript/data: `evidence/repro/human_ledge_v5_validation.py` (+.json),
`evidence/repro/human_ledge_v5_metrics.py` (+.json).

## Regression (oberoende omkörd)

- `probe_ledge_60G.json` → sidogates 0/0/0/0, axial 1 ramla. Stämmer.
- `traj_53G.json` → allt 0 inkl. axial. Stämmer.
- Bot-eventet (ep 8) faller på TVÅ oberoende v5-villkor: in-band-progression
  (progressionen intjänades vid z 19→−11, under bandet) och massa (in-band
  side_acc −201 < 300). Observera att båda bandgraze-samplen (509: z 52,2,
  perp −100,8; 510: z 44,8, perp −100,0) ligger I z-bandet — `onto_ledge` är
  alltså sann även för bot-eventet; det är progression+massa som exkluderar.

## Övergångsmatris v4→v5 (humankohorten)

| Riktning | v4-gate | samma sida | sidoflipp | → axial | tappad | nya |
|---|---|---|---|---|---|---|
| quad→ring | 472 | 207 | 0 | 265 (lyckat 211, ramla 54) | 0 | 0 |
| ring→quad | 795 | 515 | 0 | 280 (lyckat 239, ramla 41) | 0 | 0 |

Demoteringsorsaker (545 event): **482 (88 %) hade noll sampel i ledgebandet**,
27 hade bandnärvaro men ingen in-band-progression, 36 föll enbart på massvillkoret.

## Vad som är RÄTT i v5 (uppmätt)

1. **Falsk-sida-raten är noll.** Alla 4 "bot-lika" marginalevent ur review 5
   (v4:s ~11 %-falskrat) → axial (in-band massa 0–205). Noll sidoflippar, noll
   nya gate-event. Svagaste behållna event (massa 302–343) har 3 bandsampel,
   flera med 3/3 grundade — plausibla innerkantskorsningar, inga artefaktmönster.
2. **Axial-kategorin är semantiskt korrekt.** De 417 demoterade LYCKADE utan
   bandnärvaro korsade med median |perp| 19–40 (100 % < 100): axelnära rutt, inte
   sidoledge. (Bifynd för träningen: den mänskliga normalkorsningen ring↔quad är
   AXELNÄRA — 417 av 624 lyckade v4-korsningar; sidoledgerna är minoritetsrutt.)
3. Item-gates orörda; mognadsstegen tar aldrig axial-poster; asserts gröna.

## Fel 1 — in-band PROGRESS_D=350 är geometriskt onåbart för mittgropsfall

Gapmitten ligger d = 392 från målcentrum (plattformsavstånd 784); källplattformens
rand ligger d = 524. Kravet "d < 350 på plattformsnivån" kan alltså bara uppfyllas
av den som passerat 42 u BORTOM mitten — en genuin ledgekorsning som tappar
fotfästet före/vid mitten kan aldrig kvalificera. Uppmätt på genuina bandevent
(≥5 ledgebandsampel):

- **Misslyckade (ramla), n=67: v5 behåller 44 (66 %), tappar 27 till axial** —
  trots bandnärvaro upp till 63 sampel (3,2 s) och |in-band-massa| upp till
  46 099 (t.ex. demo 20173 slot 5: quad→ring SO, massa −46 099, 33 bandsampel →
  axial). Deras min_d i ledgebandet: p10/p50/p90 = 361/408/523.
- Lyckade, n=646: 100 % behålls (opåverkade).
- Andel av de 67 misslyckade som klarar in-band-progression per tröskel:
  350 → 66 %, **450 → 97 %**, 500 → 100 %.

**Justering: in-band-progressionströskel 450** (behåller kravet ≈74 u framsteg
från källranden; 500 vore i praktiken inget progressionskrav, randen ligger på
524). Effekt på kohorten: misslyckad-retention 66 %→97 %, lyckade 100 % oförändrat,
retreat 10/10 oförändrat, **0 av 39 grazers (massa<275) släpps in**, +1 gränsfall
(demo 50073 slot 6: 4 bandsampel, massa −411, min_d_band 389 — plausibelt genuint
kort försök). Misslyckade försök är precis vad nivå 1 ("försöker") och
ramla-statistiken ("utan att ramla") ska mäta — 34 % bortfall där är inte
acceptabelt för drift.

## Fel 2 — SIDE_MIN_ACC=300 är fel kalibrerad: 1,8 u marginal och dt-beroende

In-band |side_acc| på humandata (51 ms/sampel):

- Behållna gate-event: **min 301,8**, p1/p5/p10/p50 = 349/740/1768/9260.
- Grazers (demoterade enbart på massa): **max 234,6** (n_band ≤ 2).

Tröskeln 300 ligger i gapet (234,6; 301,8] men 1,8 u från genuint minimum — och
summan är samplingsberoende: botdumpar (26 ms) ger ~2× fler sampel per tidsenhet,
så en bandgraze med samma varaktighet/perp som människornas 234-grazer summerar
~470 på botdata och passerar 300. Detta blir kritiskt i kombination med fel
1-fixen: med progressionströskel 450 kvalificerar bot-ep 8:s grazesampel
progressionsmässigt (d 380–393 < 450), och då är massvillkoret ENSAM spärr mot
axialhopp som tangerar bandet — med 300 är marginalen ~1 grazesample (201 + ~100).

**Justering: tidsnormalisera massan: |side_acc| · dt ≥ 14 u·s**
(humangap 12,0–15,4 u·s; ≡ summa ≥ ~540 vid 26 ms botdata, ≥ ~275 vid 51 ms
humandata). Validerat: 722/722 nuvarande behållna kvar (min 15,4 u·s), 0/39
grazers in, bot-ep 8 = 5,2 u·s — exkluderad med 2,7× marginal i stället för 1,5×.
Näst bäst om dt-normalisering inte önskas: behåll 300 för botdumpar och acceptera
den tunna marginalen — men då måste fel 1-fixen åtföljas av regressionstest med
förlängd bandgraze (≥3 sampel à |perp| 100–110).

## Samlade siffror med BÅDA justeringarna (prog 450 + massa 14 u·s)

- Kohortretention: 744/1267 v4-event som sidogate (v5: 722) — de +22 är
  band-starka misslyckade försök som hörde hemma där.
- Genuina bandkorsningar: lyckade 646/646 (100 %), misslyckade 65/67 (97 %).
- Falskklassade sidoetiketter: 0 (grazers 0/39, marginalevent 0/4, sidoflippar 0,
  bot-regressionsfallen oförändrat gröna: probe → sidogates 0 + axial 1 ramla).

## Domslut

**JUSTERA** enligt ovan (två tröskelvärden, ingen strukturell ändring). Med
justeringarna implementerade och regressionstest för (a) mittgropsfall från
ledgen (min_d_band ∈ [350, 450)) och (b) förlängd bandgraze på 26 ms-data är
detektorn redo för drift — jag godkänner då utan ny fullvalidering, förutsatt
att omkörningen av `human_ledge_v5_validation.py` ger 744/0/0 enligt ovan.
