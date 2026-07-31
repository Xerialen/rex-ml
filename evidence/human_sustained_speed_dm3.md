# Mänsklig uthållen fart på dm3 (4on4) — 60s-fönster, var, hur, tak
*Analystrapport 2026-07-31 (dm3-analytikern, mvd_analyzer + store-dm3). Beställd som
underlag för Gate 2:s 500-krav och 400-platåns diagnos.*

## Kohort och metod
- Store: dm3-extract/store-dm3/trajectory_samples (3 777 dm3-demos) → strikt 4on4-filter
  → 2 110 MVD-demos (~5 563 sp-tim). KRITISKT: endast 851 demos har BSP-referee-h
  (höjd-över-golv); no-h-demos kontaminerar toppen med friflygspår (verifierat, se
  Validering). Huvudkohort = 851 demos, ~2 270 sp-tim, 428 M giltiga OPEN-tickar.
- Fartmetrik = gate2-pipelinens (centraldiff, 3-sampel-median, warp/tele-regeln
  >250u ⇒ exkludera [t, t+500ms]); zonklass via voxel_classes.npz. Sanity: OPEN
  per-tick p50/p95/p99 = 339/500/581 ≈ publicerade 334,8/496,2/580,4.
- Skript (scratchpad/dm3win/): pass1_hv.py, stage2_windows.py, stage3_where_how.py.

## 1. Uthållna 60s-snitt (glidande, 1s-steg, endast OPEN-tickar)
- 7 616 053 fönsterpositioner. **>500: 0 fönster** (villkor A och A+avsikt).
  >450: 43 st (5,8e-6). Bästa-fönster-per-spelare-demo (n=6 806):
  p50 380 | p90 406 | p95 414 | p99 431 | p99,9 452 | **max 464,8**.
- Topp-3: 464,8 Hto (4on4_rrk_vs_tco[dm3]20260109-1520.mvd, 654-714s, g=800-fit);
  458,2 XantoM (4on4_red_vs_dk[dm3]20231111-1813.mvd); 458,1 ToT_slime
  (4on4_d2_vs_tot[dm3]20251023-1954.mvd).
- Lös nämnare (OPEN-andel ≥25 %): max 514,6 — denominator-selektion, inte uthållet.

## 2. Var (>450/>500-tickar)
Volym: hill/mega-gården 21,8 % av alla >500, quad/ring-övre 13,7 %, YA-gården 13,2 %,
window 9,0 %, bron 7,9 %, ytterring-öst 7,5 %. Täthet (fartkorridorer): östra
korridoren RL↔window **71-75 %** av trafiken >450, window ~50-60 %, RA→YA-diagonalen
(störst volym), ring/quad-övre, SNG-östgolv ~47-48 %. RA-hallen: mest trafik, 7 %.

## 3. Hur (68 711 runs ≥3s över 400; h-validerade)
- 39 104 runs snitt ≥500: duration p50 3,8s, ≥8s: 348 st, **max 25,9s @ 535**
  (5h4DDoW, 4on4_red_vs_blue[dm3]220123-0626.mvd 163-189s, window↔RL, luft 0,96).
- Teknik ≥450: **luftandel p50 0,93** (p10 0,84); hoppkadens ~1,0/s; landningar
  median **−13,5 u/s** (p90 +10 — de bästa landar förlustfritt); dz svagt negativ
  (drop-preferens); corr(Δv,Δz)≈0 — farten byggs i LUFTSTRAFE, inte ramper;
  tick-max 700-1 555 = raketknuffar. Kontrast: runs 400-450 har luftandel p50 0,21
  — **över ~450 finns bara luftvägen.**

## 4. Takbedömning
- 500-kravet överstiger ALL demonstrerad mänsklig prestation med ~8 % (max 464,8;
  och gaten kräver det i VARJE episod — 464,8 var 1 fönster av 7,4 M).
- Policyns 415-platå ligger redan på mänsklig p95-p96 av bästa-fönster.
- MEN: farten i sig är demonstrerad (25,9s @ 535 inkl rumsövergångar, standardfysik).
  Det ingen människa visat är 60s KONTINUITET — de avbryts av strid/items/död.
  Taket för ren rörelseavsikt: **~500-535** via 93-97 % luftandel + förlustfria
  landningar (+raketassist för skurar). Gaten är INTE påvisbart olöslig.
- Landningsförlusterna är kvantifierbar valuta: −13,5 u/s median × ~1 hopp/s
  ≈ 15-20 u/s på snittet — elimineras de är gapet 415→450 nästan slutet.

## Validering
- Kontaminering verifierad: ovaliderad helkohort gav 4-5 falska ">500-fönster"
  (max 595) — alla ur count(h)=0-demos med icke-spelarfysik (27s flygning,
  kamerasnäpp). Alla topptal ovan h-validerade + g-fit 799-803.
- Osäkerhet (Medium): no-h-halvan (1 259 demos) kan gömma legitima fönster
  465-505, inget verifierbart.

**Slutsats (High): 500 i 60s-OPEN-snitt är övermänskligt (~8 % över max) men inom
fysikens tak för ren rörelseavsikt (~500-535). Vägen dit är luftteknik: ≥0,93
luftandel, ~1 hopp/s, förlustfria landningar — i fartkorridorerna (RL↔window,
RA→YA, ring/quad-övre, hill/mega).**
