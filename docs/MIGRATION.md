# Migrering vmonster (H100, 64 kärnor) → pinnacle (4090, ~8-16 kärnor, 64 GB)

Skriven 2026-08-01 (deadline: maskinen otillgänglig efter 2026-08-02).
Syfte: att en färsk kontext på pinnacle kan återuppta utan förlust.

## MÅSTE flyttas/säkras (i prioritetsordning)

| Vad | Storlek | Status | Anteckning |
|---|---|---|---|
| rex-ml-repot | ~grunt | ✓ pushat kontinuerligt | github.com/Xerialen/rex-ml (main; lokal branch `master`) |
| gate2_v2-checkpoints | 196 M (hela) | **train_dir/ är GITIGNORERAD** | snapshot i `pipeline/out/rl/gate2_snapshot_20260801/` (senaste + best, 44 M, committad). Slutsnapshot görs som SISTA åtgärd före flytt. |
| mvd-corpus | **161 G** | ~96 % på HF (Xerial/qw-demos-mined-db, 55.7 G zst, 49 183 av ~50 952 demos per index 2026-07-16) | flytta DIFFEN (~1.8k demos + post-16-juli) eller ladda upp den (kräver ägar-token) |
| qwd-corpus | **56 G** | bundlen (31.2 G) på HF; resten ~25 G BARA lokalt | flytta delta eller hela |
| dm3-extract/store-dm3 | 8.5 G | INTE på HF (parquet/staging-v1 tomt — uploaden fullföljdes aldrig) | flytta eller ladda upp; analystens arbetsmaterial |
| ~/mlx/qwserver | 335 M | flyttbar (tar) | RIKTIGA mvdsv-servern — krävs för Gate 2-serverbevis (bevisregeln) |
| ~/mvd_analyzer | liten (git-klon) | omklonas | analystens verktyg |
| ~/rex-ml-rtx | ? | push blockerad (PAT-scope) | bothost-repot — lös PAT eller tar:a |

## Miljöuppsättning på pinnacle

1. Klona repot; bygg `sim/` (libqwsim) enligt `sim/README`/byggscript — kräver
   dm3.bsp/100m.bsp på plats (följer med qwserver-tar:en, sökväg i
   `rl/dump_trajectories.py` BSP-konstanten + testsuite-config `basedir`).
2. Venv: `uv pip install --python sim/.venv-sf/bin/python ...` (INTE pip);
   Sample Factory 2.1.1 + patchar enligt `sim/STACK.md` (SF_STDDEV_MIN/MAX i
   action_distributions.py; learner.py weights_only=False). Träning körs med
   `SF_STDDEV_MAX=1.0`.
3. Återuppta träning: kopiera snapshot-checkpointen till
   `pipeline/out/rl/train_dir/gate2_v2/checkpoint_p0/` (behåll namnmönstret),
   kör kommandot ur PROGRESS-posten 2026-08-01 17:34 MEN skala ner:
   `--num_workers` ≈ kärnor−2 (t.ex. 12), `--num_envs_per_worker=8` behålls.
   Väntad FPS ~6-12 k (CPU-flaskhals; 4090:n räcker gott för learnern).
4. tmux-session `rexml`, fönster `jobs`; monitor på gate2_v2/console.log
   (30-min-hjärtslag + krasch/stillastånd — se PROGRESS 2026-08-01).

## Vad som ändras strategiskt efter flytt

- Frame-hungrig träning blir 5-8× dyrare ⇒ H100-dygnen (1-2 aug) prioriterade
  täckning + klätterincitament. På pinnacle: kortare finjusteringar, evals,
  serverbevis (realtid, CPU-lätt), analys, ev. destillering.
- Serverbevisen (30×60 s realtid + MVD-inspelning) går utmärkt på pinnacle
  förutsatt qwserver-tar:en + testsuite-config (`basedir` =
  `~/mlx/qwserver/serverdir`, se memory testsuite-config-basedir).
- Analystens tunga duckdb-frågor tål färre kärnor (längre, men funkar) —
  förutsatt att store-dm3 följer med.

## Sista-åtgärder-checklista (körs strax före avstängning)

1. Stoppa träningen snyggt (TERM till PGID), vänta ut sista checkpoint-skrivning.
2. Uppdatera `pipeline/out/rl/gate2_snapshot_<datum>/` med SENASTE + best + config.
3. `git add -A && git commit && git push origin master:main`; verifiera rent träd.
4. Verifiera att korpora-kopiorna (ägarens destination) är kompletta (du -s + stickprov).
5. tar:a qwserver + ev. rex-ml-rtx; flytta.
6. Sista PROGRESS-post: exakt frames, senaste mätvärden, var allt ligger.
