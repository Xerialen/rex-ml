# LÅST — v7.2-omlåsning av humanbaslinjen efter retreat-kvalifikationskravet (analyst-review 9): lyckat 580 + ramla 133 OFÖRÄNDRADE (identiska event, verifierat per event), retreat 37→22 (7/7 SO + 15/30 NV) — de 15 fällda är samtliga ring→quad NV med min dPit 260–305 och blir axial-retreat; SLUTLIG baslinje: 735 gate-event = 580 lyckat + 133 ramla + 22 retreat

## v7.2-baslinje (analyst, 2026-08-02)

Detektor: `rl/jump_gates.py` v7.2 (koordinatorns implementation av mitt
kvalifikationskrav ur `evidence/analyst_nv_retreat_review.md`, oförändrad av
mig; diff verifierad: retreat kräver transit-min-dPit < PIT_EXPOSURE_R=260,
annars `progressed=False` ⇒ fall till axialspåret via raw-progression).
41/41 test. Ersätter `evidence/analyst_v71_baseline.md` som
regressionsbaslinje; v7.1-dokumentet behålls som historik.

## SLUTLIG LÅST REGRESSIONSBASLINJE (v7.2, 24-demoskohorten, dt 0.051)

**735 gate-event:**

| gate | lyckat | ramla | retreat | försök |
|---|---|---|---|---|
| ring→quad NV | 208 | 13 | 10 | 231 |
| ring→quad SO | 232 | 43 | 5 | 280 |
| quad→ring NV | 84 | 13 | 5 | 102 |
| quad→ring SO | 56 | 64 | 2 | 122 |
| **totalt** | **580** (292 NV / 288 SO) | **133** (26 NV / 107 SO) | **22** (15 NV / 7 SO) | **735** |

Axial (informationsspår): 809 = 497 lyckat / 291 ramla / 21 retreat
(v7.1: 794 = 497/291/6 — de 15 fällda gate-retreaterna hamnar här).

Human-lyckandegrader per gate (uppdaterade försöksnämnare, för
botjämförelser): ring→quad NV **90 %** (208/231), ring→quad SO 83 %,
quad→ring NV 82 %, quad→ring SO 46 %.

## Verifiering av prognosen ur analyst-review 9 (alla träffar exakt)

- **lyckat: 580 → 580, ramla: 133 → 133** — inte bara samma antal utan
  IDENTISKA event (per-event-jämförelse i repron: True/True).
- **retreat: 37 → 22** = 7/7 SO (ring→quad 5 + quad→ring 2) + 15/30 NV
  (ring→quad 10 + quad→ring 5) — exakt prognosens fördelning.
- **De 15 fällda:** samtliga ring→quad NV; min dPit 260–305 (alla >= 260);
  samtliga blir `axial ring→quad` retreat (raw-progression < 450 fanns i
  alla 15, som förutsett).
- **Behållna retreater:** max min-dPit 252 (alla < 260) — 8 u marginal till
  tröskeln; genuin-envelopen (lyckat/ramla <= 192) intakt.
- Botregressionen (koordinatorns omkörning, av mig verifierad):
  probe_ledge_66G ⇒ NV-gate 0, axial 9 (8 ramla + 1 retreat);
  probe_ra_66G ⇒ NV-gate 0, axial 2 (1 ramla + 1 retreat);
  traj_63G SO 2/1/1 intakt; traj_66G oförändrad (axial 4 ramla).

## Kvarstående övervakningspunkter (ärvda från v7.1, punkt 1 STÄNGD)

1. ~~Retreat saknar gropexponeringskrav~~ — STÄNGD av v7.2 (denna omlåsning).
2. Bhop-underdetektion vid 26 ms (kvarstår).
3. Plattformscirkeln (r 260), gropcirkeln (r 260) och maskens t-fönster är
   modeller, inte BSP (kvarstår; gropcirkeln nu även kalibrerad mot
   korridor-envelopen 192 i analyst_nv_retreat_review.md).

## Repro

```
cd ~/rex-ml
PYTHONPATH=. .venv/bin/python evidence/repro/human_ledge_v72_baseline.py
  # ⇒ 227 assert-verifierade segment; gate 580/133/22 (735); axial 497/291/21;
  #   fällda 15 = ring→quad NV, dPit 260-305, -> axial retreat
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/traj_63G.json         # SO 2/1/1, axial 2
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ledge_66G.json  # gate 0, axial 9
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ra_66G.json     # gate 0, axial 2
PYTHONPATH=. sim/.venv-sf/bin/python -m pytest rl/tests/ -q                         # 41 passed
```

Dubbelspårning v7.1/v7.2 i samma transitloop
(`evidence/repro/human_ledge_v72_baseline.py` → `.json`, 1544 eventposter),
v7.2-spåret assertat mot detektorn på alla 227 segment.

Konfidens: hög. Baslinjen LÅST för framtida omvalideringar av denna kohort.
