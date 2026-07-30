# Results — local rtx live test, 2026-07-28

Schema `rex-drills/1`. **Not** `rtx-testflow/1` — the lab suite was unreachable, so these are
reconstructions of T0 and T1 only. See [README.md](README.md) for why, and for every deviation.

Build under test: `playground/qw/qwprogs.so`, md5 `29bc1259ecddb6b449bc3b77c275eeac`, byte-identical
to `target/release/librtx.so`. Branch `rex-ml/step3-cvar` @ `f4d607c` (dirty — `rex-drills` is new).
Map `dm3.bsp` md5 `e48f522b498c5b43583303527e7df1fe`. Engine `mvdsv` md5 `5775a2af1fdc0b9f77a90c3bf660fabb`.

## T0 — preflight: **passed, 20/20**

Navmesh reproduces the recorded baseline exactly: **4,634 cells / 36,956 links / 2,021 rocket-jump
links**. All five stock movevars confirmed (gravity 800, maxspeed 320, accelerate 10, friction 4,
stopspeed 100). Read-only verbs answer (45 items, 2,021 RJ links, cell + route queries). A puppet
`Teleport` lands 1.00 u from the requested point.

## T1 — movement drills: **failed**

150 declared dm3 routes from `~/route-sheet-search/routes.json`, run three times.

| run | timeout floor | telemetry | arrived | stalled | timed out | rate |
|---|---|---|---|---|---|---|
| 1 — as pre-registered | 20 s | off | 93/150 | 16 | 41 | 62.0 % |
| 2 — corrected rig | 60 s | on | 104/150 | 34 | 12 | 69.3 % |
| 3 — replication of 2 | 60 s | on | 115/150 | 24 | 11 | 76.7 % |

Completion time for arrivals (run 3 conditions): p50 **13.8 s**, p90 **25.3 s**, max 25.4 s — well
inside the 60 s budget, so the threshold is no longer the binding constraint. Peak speed p50
**509 u/s**, max **630 u/s**.

### The headline is reproducibility, not the rate

Runs 2 and 3 are replications under identical conditions, and they disagree on 31 of 150 drills:

| | drills |
|---|---|
| arrived in both | 94 |
| failed in both | 25 |
| **flipped** | **31 (21 %)** |

Across all three runs, only 66/150 passed every time and 15/150 failed every time; **69 drills
(46 %) changed outcome at least once**. A single pass/fail run therefore cannot grade an individual
drill. Grading them needs repetitions and a rate with a confidence interval — exactly what the brief
already requires of route times (median over ≥30 runs, 95 % CI excluding zero). Two consequences:

- The apparent 62 % → 69 % → 77 % improvement is **not** established as real. Run 1 differs in
  conditions, and between runs 2 and 3 the flips were asymmetric (21 fail→pass vs 10 pass→fail),
  which is suggestive of drift but not significant at n = 31.
- An earlier reading of mine — that failures concentrated on the *Pent Mega* destination (11 failed
  / 4 arrived in run 1) — **did not replicate** (2 failures in run 2). That was noise, and it is
  retracted here rather than quietly dropped.

### One finding that is fully deterministic: SNG Mega is a trap

Every drill *starting* at SNG Mega failed in all three runs, with the same outcome:

```
r112-SNG_Mega->RA          timeout timeout timeout
r113-SNG_Mega->YA          timeout timeout timeout
r114-SNG_Mega->RL          timeout timeout timeout
r115-SNG_Mega->Quad        timeout timeout timeout
r116-SNG_Mega->Pent        timeout timeout timeout
r117-SNG_Mega->Ring        timeout timeout timeout
r118-SNG_Mega->Hill_Mega   timeout timeout timeout
r119-SNG_Mega->LG          timeout timeout timeout
r141-SNG_Mega->Pent_Mega   timeout timeout timeout
```

9/9 drills, 27/27 observations. By start region, no other origin exceeds 2/10 hard failures. The
mechanism, from the evidence:

- The start cell is **264** at `(-736, 96, 184)`, the cell nearest the SNG Mega pickup.
- For a goal 1,274 u away the planner returns a **2-leg, 64-unit route** — a partial plan, i.e. no
  path found.
- The bot fires **`displacement` watchdogs on `Walk` links**, resolved by `force_jump`, 15 times in
  60 s. It moves just enough to stay above the server's 16 u / 4 s stall threshold, which is why the
  outcome is `timeout` and not `GotoStall`.
- The shelf is **not** an isolated graph component: 264 ↔ 232 ↔ 194, and 194 opens onto
  153/155/157 with a rocket-jump link inbound; 165 nearby carries drops, jumps and a speedjump.

So the graph believes the shelf is connected while the bot cannot actually traverse it — walk links
along a narrow ledge at z = 184 that the player hull won't pass. That is a navmesh-vs-physics
disagreement, and it is the single most actionable defect this run found.

### Steering watchdogs

Run 2, with `rtx_telemetry 1`, recorded **755 firings across all 150 drills**:

| reason | n | | action | n | | link kind | n |
|---|---|---|---|---|---|---|---|
| displacement | 534 | | force_jump | 526 | | Walk | 435 |
| air_commit_off | 180 | | penalize+repath | 229 | | JumpGap | 193 |
| prestrafe_deficit | 20 | | | | | (off-route) | 82 |
| air_commit_timeout | 13 | | | | | SpeedJump | 33 |
| speedjump_stall | 8 | | | | | Step | 11 |

Run 1 reported zero firings — because `BotStall` is gated behind `rtx_telemetry`, which defaults to
0. That zero meant *no data* while reading as health, which is the more dangerous of the two rig
bugs found here.

## 100m corridor — the lab's one documented acceptance figure: **missed**

AGENTS.md gives a single known-good corridor with an explicit bar: `corridor_test(start=(224,
-1408, 32), end=(224, 2900, 32))` on `100m`, where "bots should hold 800+ ups on the runway". Run
10 times (`evidence/t1_100m_bar.json`, T0 for the map in `evidence/t0_100m.json`, 20/20):

| | value |
|---|---|
| arrived | **10/10** |
| met the 800 u/s bar | **0/10** |
| peak speed | min 770.3, median 771.6, max 773.6 u/s — **stdev 0.95** |
| shortfall vs bar | **26.4 u/s (3.3 %)** |
| elapsed | 8.15 – 8.23 s |
| max cross-track drift | 46 – 201 u, median 148 |
| reverse frames | 0 in every rep |

Two things follow, and the second is the more interesting:

1. **The build misses the documented bar by 3.3 %.** The bar is declared in the drill spec
   (`min_peak_speed`), so this is a spec failure, not prose beside a green result. An earlier
   arrival-only envelope for the same runs is kept as `evidence/t1_100m_arrival_only.json` and
   reports `passed` — true under that weaker criterion, which is exactly why the bar belongs in the
   spec. Drift 46–201 u matches AGENTS.md's warning to raise `max_cross_track` above its 64 u
   default for a bhopping bot; 0 reverse frames means no backtracking at all.
2. **The corridor is essentially deterministic — stdev 0.95 u/s over 10 reps** — while the dm3
   route set flips 21–46 % of drills between identical runs. Same rig, same build, same server. So
   dm3's variance is not rig noise or physics jitter: it comes from route complexity and decision
   points, and only shows up where the bot has choices to make. That makes the corridor a good
   regression probe and the dm3 set a poor one until it is run with repetitions.

## Invariant check — per-tick CPU budget

`automaton::tests::bench_per_tick_budget` **fails under `cargo test`** and passes under
`cargo test --release`:

| profile | MLP forward | DMP step | guard | full tick | vs 500 µs budget |
|---|---|---|---|---|---|
| debug | 499.9 µs | 360 ns | 37 ns | **531.3 µs** | over |
| release | 28.6 µs | 67 ns | ~0 ns | **26.6 µs** | **19× headroom** |

The invariant holds — 26.6 µs matches the previously recorded 26.7 µs. The debug number is a ~20×
penalty from missing inlining and vectorisation, not a regression. The test now always prints the
measurement and enforces the bar only when optimised, so the repo's documented default `cargo test`
no longer fails on a clean checkout. Full workspace suite: green.

## What these numbers do and do not say

- They characterise **the existing rtx controller in an ML-branch build**. The trained policy and
  `automaton.rs` are compiled in but not called from `rtx-game`'s bot control path, so this is a
  baseline, not an ML-vs-baseline comparison.
- Drills run with combat off (structurally — a puppet order returns `enemy: None`), so nothing here
  speaks to movement under fire.
- Cross-track drift and reverse-frame counts are reported but not gated: these are full map routes,
  not the straight corridors `corridor_metrics` was designed for.
