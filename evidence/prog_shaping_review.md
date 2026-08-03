# Expressgranskning: potentialbaserad progressions-shaping (commit 7f111c5, live k=3.0 via c6c7f18)

Roll: belöningshack-skeptiker. Granskat: `rl/env_gate2.py` (step()-blocket rad 417–431,
`_reset_state` rad 194–196, reset-settling rad 223–235), `Gate2Config.prog_shaping`,
flaggan `--qw_prog_shaping` (train_gate2.py), wiring (sf_env.py), nya tester.
Datum: 2026-08-03. Ingen kodändring gjord.

## VERDICT: GODKÄND

Teleskopargumentet håller i praktiken. φ = clamp(proj/d, 0, 1.2) är en ren funktion av
positionen (origin/u/d fryses per episod), Δφ betalas varje tick ⇒ total episodinkomst
= k·(φ_slut − φ_start) = k·φ_slut exakt, oavsett bana. Ingen pump, ingen farm.

## Punktvis

### (1) Episodläckage — OK
`_reset_state()` (rad 195–196) nollar `_prog_prev = None` och `_prog_origin = None` vid
varje reset, atomiskt med `_takeoff_target` (rad 194). `_prog_u`/`_prog_d` nollas INTE
där, men är oåtkomliga: shaping-blocket gated på `_takeoff_target is not None`, och när
origin är None räknas u/d om innan användning (rad 420–425). Reset-retryloopen (6
försök) kör `_reset_state` per försök; settling-loopen (90 ticks `b.step`) rör aldrig
prog-variablerna. Origin sätts på FÖRSTA policy-steget ⇒ φ₀ = 0 per konstruktion och
`_prog_prev is None` ⇒ ingen utbetalning tick 1. Ingen kredit läcker mellan episoder.

### (2) Landningsterminering — sista Δφ BETALAS; gropdyk kvantifierat
`_landed_done` sätts rad 414–416, shaping-blocket exekverar EFTER det i samma step()
och adderar k·(φ_landning − φ_prev) till r som returneras med done=True (rad 445–447).
Terminala Δφ:t når alltså policyn — gradienten vid landningsticken finns.

Gropdyk-netto (k=3.0, d = 573–683 u över de 4 states):
- Netto = k·φ_gropbotten. Mittgapsdyk: φ ≈ 0.4–0.5 ⇒ **~1.2–1.5**.
- Värsta fall (väggkramar-dyk: slår i bortre gropväggen, glider ner): φ begränsas av
  bortre rimkanten < 0.805 (uppmätta korsningslandningar börjar där) ⇒ **≤ ~2.4**.
  Kodkommentarens "≤ ~0.5k" är alltså optimistisk — geometriska taket är ~0.8k.
- Fullbordan: shaping k·(0.805–0.902) = 2.4–2.7 PLUS gapjackpot
  gap_base 3.0 × spancap 2.5 × deep (1+anneal ∈ [1,2]) = 7.5–15 ⇒ **9.9–17.7 totalt**.
- Dominans ≥ 4.1× per episod (9.9/2.4), båda episodtyperna terminerar vid första
  landningen med jämförbar längd ⇒ per-tick-raten dominerar likadant. Gropdyk är
  betald partiell kredit (bootstrap-syftet), inte en konkurrerande jämvikt.

### (3) Cap 1.2 / pump inom episod — OMÖJLIG
φ är tillståndsfunktion; clampen ändrar inte det (clamp av en funktion av pos är
fortfarande en funktion av pos). ΣΔφ teleskoperar exakt till φ_T − φ_1 = φ_T oavsett
antal 0↔1.2-oscillationer. Verifierat i koden (prev uppdateras ovillkorligt varje tick,
rad 429–431) och av nya testet `test_prog_shaping_telescopes_and_caps` (oscillation
0→200→100→250→400 nettar exakt k·1.0). Overshoot-vägen (gå runt gropen på marken till
φ=1.2, kantavgång) nettar max 1.2k = 3.6 utan jackpot på 3–4 s — dominerad av korsning
(9.9–17.7 på ~1 s). Teoretisk randnot: formen är F = φ(s′) − φ(s), inte Ng:s
γφ(s′) − φ(s); med γ<1 ger det en mild preferens att tjäna φ TIDIGT — här alignerat
(snabb progress), och episodinkomsten förblir exakt k·φ_slut. Ingen åtgärd.

### (4) Interaktion gap_anneal/klätterbonus — REN
Shaping adderas till r EFTER `_air_segment` och multipliceras aldrig (enda efterföljande
termen är stuck-straffet; nov_mult rör bara novelty/height, och novelty_bonus är 0 i
takeoff-envs). gap_anneal skalar endast djup-EXTRAN (×2→×1) — även fullt annealad
(jackpot 7.5) dominerar fullbordan gropdyk ~4×. Bevakningspunkt: shaping återinför
partiell betalning (≤ k·0.444 = 1.33/episod) för hörnklippet som sidovillkoret
(prog < 0.6 ⇒ eff_depth = 0) nollade — men klippet terminerar nu episoden (FIX C) så
raten är ~0.03/tick mot korsningens ~0.2/tick; 18.85/episod-farmen kan inte återuppstå.
Rekommenderad bevakning: klipp-frekvens i takeoff-workers efter k=3-aktiveringen.

### (5) Testsvit
`.venv/bin/pytest rl/tests/ -q`: **66 passed, 2 failed av 68**. Båda felen är
`ModuleNotFoundError: No module named 'gymnasium'` (rl/sf_env.py:12) i gransknings-
venven — miljöberoende importfel i två FÖREXISTERANDE tester (commiten appendade bara
till filen), inte logikfel. Båda nya prog-testerna gröna. Träningsvenven (där gymnasium
finns) berörs inte.

## Sammanfattning
Konstruktionen är farm-omöjlig by construction och koden implementerar den korrekt.
Enda avvikelserna: (a) kommentarens gropdyk-tak "~0.5k" bör vara "~0.8k" (rad 83,
kosmetiskt — dominansen håller ändå), (b) 2 miljöberoende testfel utanför commitens
ansvar. Ingen kodfix krävs.
