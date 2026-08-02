# JUSTERA (en regel: "förankrat fall" för ramla-utfall — annars GODKÄND; nuvarande v6-semantik behåller bara 19–38 % av genuina misslyckanden)

## v6-validering + beslut om SO-gapsemantiken

Analyst, 2026-08-02. Detektor: `rl/jump_gates.py` v6 (oförändrad av mig).
Kohort: samma 24 demos (1 267 v4-gate-event). Repro:
`evidence/repro/human_ledge_v6_validation.py` (+.json; 227 assert-verifierade
segment mot detektorn, dt=0.051) samt inline-valideringar dokumenterade nedan.

## Verifiering av implementationen (krav a–c ur analyst_v51_verdict.md)

- **(a) Ledgemask:** korrekt byggd. 261 stödda centers (SO 89, NV 172),
  oberoende uppmätt ur `ledge_centers()`. SO-gapet bekräftat: största lucka i
  d_ring **330→555 (226 u)**, näst största 23 u; NV kontinuerlig (maxlucka 21 u).
  Stödd-filtret gör rätt sak — ep5:s gropluftrumskolumner är borta.
- **(b) Källplattformskrav:** implementerat; fäller ep14-klassen (traj_53G
  ⇒ sidogates 0 ✓).
- **(c) Axial 450:** probe ⇒ sidogates 0 + axial 2 ✓ — uppmätt **ep5+ep8**
  (koordinatorns "(ep5+ep6)" är felskrivet; båda ramla). traj_53G ⇒ axial 3
  (ep4, ep14 retreat, ep23) ✓.

## Problemet: v6-progressionen förblindar ramla-statistiken på BÅDA sidor

Genuina band-misslyckanden (67 ur baslinjen) genom v6:

| | v6 behåller | orsak till förlust |
|---|---|---|
| NV-ramla (24) | 9 (38 %) | 15 ej_prog |
| SO-ramla (43) | 8 (19 %) | 26 ej_prog, 9 ej_mask |
| NV-lyckade (310) | 271 (87 %) | 39 ej_källgrund |
| SO-lyckade (336) | 291 (87 %) | 34 ej_källgrund, 8 ej_mask, 3 ej_massa |

Det är inte bara SO-gapet: även på kontinuerliga NV driver fallande spelare av
maskkolumnerna (in mot gropen) innan d<450 nås över mask. Semantiken "försök =
nådde landningskantens kolumn" underkänns av mätningen — gatekriteriet är
"utan att ramla", och en detektor som missar 62–81 % av misslyckandena kan inte
skilja nivå 1 från nivå 3.

## Beslutet: förankrat fall (kalibrerat i tre steg)

**Regel (v6.1):** för `ramla`-utfall räknas progression om **min d(dst) över
ALLA transitsampel < 450** (fallets framåtsträckning), MEN endast om försöket är
**golvförankrat: ≥1 GRUNDAT masksampel inom transiten** — övriga krav
(onto_ledge, massa 14 u·s, grundad källplattform) oförändrade. Lyckat/retreat
oförändrade.

Kalibreringen som tvingade fram grundat-kravet:

1. Rå förankrat fall (utan grundat-krav) testades först: human-retention NV
   19/24, SO 30/43, MEN **ep5 och traj_53G-ep23 blir gate igen** — båda har
   maskkontakt enbart som luftburen överflygning av källsidans ledgeaxel (ep5:
   11 masksampel i transiten, 0 grundade — de 4 grundade ligger på spawnsamplen
   FÖRE transiten; ep23: 5/0, z 95–100 över kolumnerna). Regeln utan
   golvförankring återöppnar exakt det hål jag underkände.
2. Med grundat-krav: **alla botregressioner bevaras** (probe ⇒ sidogates 0 +
   axial 2; traj_53G ⇒ sidogates 0 + axial 3).
3. Human-utfall (ur `human_ledge_v6_validation.json`, fält n_mask_grundade):

| | v6 | v6.1-förfinad |
|---|---|---|
| genuina ramla NV | 9/24 | **16/24** |
| genuina ramla SO | 8/43 | **26/43** |
| genuina ramla totalt | 17/67 | **42/67** — varav **42/43 (98 %) av de golvförankrade** |
| genuina lyckade | 562/646 | 562/646 (oförändrat) |
| totala gate-event | 636 | **662** |
| insläppta ej-genuina ramla | — | **1** (demo 53123 slot 9: 3 masksampel, 2 grundade, massa 16,1 u·s — plausibelt kort äkta försök) |
| grazers | 0 | 0 |

De 24 av 67 som förblir axial är, under korrekt geometri, inte golvförankrade:
9 helt utan maskkontakt (gropluftrumsflygare — mänsklig ep5-klass; gamla
bandproxyn kallade dem felaktigt genuina) och 15 med enbart luftburen
maskkontakt (51 ms-undersampling av bhop-nedslag ELLER äkta flygare — ej
särskiljbart i humandata; se osäkerhet nedan).

**Svar på semantikfrågan:** "nådde landningskantens kolumn" är INTE acceptabel
semantik (mätningen ovan). Sidogate-försök = golvförankrad ledgeanvändning +
fall med framåtsträckning <450. SO-gapet behöver därmed ingen särbehandling —
SO-ramla blir observerbara igen (26 st mot 8), och SO/NV-retention är balanserad
(60 %/67 %).

## Kvarstående osäkerheter (dokumenterade, ej blockerande)

- **Bhop-underdetektion:** grundat-flaggan kräver z-stabilitet över båda
  grannsamplen — ett 1-sampels bhop-nedslag fäller den även på 26 ms-botdata.
  En framtida bot som kedjar perfekta bhops längs ledgen kan bokas axial.
  Övervaka: om axial-ramla med hög luftburen maskkontakt ackumuleras i
  probekörningar, ersätt grundat-kravet med nedslagsdetektor
  (d²z-teckenväxling). Idag är risken teoretisk (nivå 1–2-beteende går/studsar).
- **Källplattformskravets humankostnad:** 73 genuina lyckade (11 %) tappas på
  51 ms-humandata (luftburna plattformspassager). Operativt irrelevant för
  botdumpar (26 ms); relevant enbart som bias i framtida humanbaslinjer —
  notera vid användning.
- Fysiska plattformscirkeln är fortsatt modell (r 260), inte BSP.

## Villkor för drift (v6.1)

Implementera förankrat fall enligt regeln ovan + regressionstest:
(i) golvförankrat mittgropsfall (grundade masksampel på källsidan, fall
min_d<450) ⇒ gate ramla; (ii) överflygningsfall (endast luftburna masksampel,
ep5/ep23-fixturer) ⇒ axial; (iii) probe ⇒ sidogates 0 + axial 2, traj_53G ⇒
sidogates 0 + axial 3. Omkör `human_ledge_v6_validation.py` (uppdaterad med
v6.1-regeln i dual-tracen) — krav: **662 gate / 42 av 43 golvförankrade ramla /
0 grazers / ≤1 insläpp**. Vid dessa siffror: **GODKÄND FÖR DRIFT utan
ytterligare fullvalidering** (samma villkorsform som v5→v5.1; denna gång är
även ny-event-kanalen mätt: v6:s 26 nya, förfiningens +26 utpekade ovan).

## Mätkommandon

```
cd ~/rex-ml
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ledge_60G.json
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/traj_53G.json
.venv/bin/python evidence/repro/human_ledge_v6_validation.py
```

Konfidens: **hög** (alla spår assert-verifierade mot detektorn; beslutet
kalibrerat mot 67+646-kohorterna och falsifierat i två iterationer innan
grundat-kravet låstes).
