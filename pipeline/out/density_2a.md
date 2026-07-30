# STEP 2a — demonstration density for rocket-jump DMPs

1,712 rocket-jump trajectories recovered from the 1,759 labelled maneuvers (the rest are maneuvers sharing an air phase, collapsed to one trajectory each).

| split | jumps |
|---|---|
| train | 1,447 |
| val | 121 |
| test | 144 |

## 1. Spatial density on dm3 (start/goal regions)

dm3 extent covered by these jumps: x [-968, 2032], y [-944, 1120], z [-392, 384]

| grid | start cells used | goal cells used | (start,goal) pairs | pairs with >=5 | pairs with >=20 | median demos/pair |
|---|---|---|---|---|---|---|
| 512 u | 26 | 27 | 145 | 48 | 23 | 2 |
| 256 u | 79 | 87 | 414 | 78 | 19 | 2 |
| 128 u | 213 | 236 | 856 | 66 | 3 | 1 |

At a 256-unit grid the distribution is heavily skewed: the top 10 (start,goal) pairs hold 407 of 1,712 jumps (24 %), while 199 pairs (48 % of pairs) have exactly one demonstration.

**Verdict on a per-location DMP library: not viable.** Only 19 of 414 pairs reach 20 demonstrations. Indexing DMPs by map location would leave most of dm3 uncovered.

## 2. Task-space density (the space DMP regression actually lives in)

Task parameters, all SE(2)-invariant, measured at the blast tick:

| parameter | p5 | p25 | p50 | p75 | p95 | span |
|---|---|---|---|---|---|---|
| entry speed (u/s) | 39 | 319 | 344 | 397 | 576 | 537 |
| blast dvz (u/s) | -180 | 99 | 258 | 260 | 658 | 838 |
| view pitch (deg) | 23 | 47 | 71 | 80 | 80 | 57 |
| goal fwd displacement (u) | -538 | -221 | -13 | 124 | 434 | 972 |
| goal right displacement (u) | -395 | -160 | -8 | 99 | 359 | 754 |
| goal dz (u) | -183 | -4 | 140 | 220 | 256 | 439 |
| duration (ms) | 91 | 810 | 1105 | 1291 | 1669 | 1578 |

Joint coverage, on the 5 task parameters standardised:

  * 3^5 = 243 cells → 131 occupied (53.9 %); median 3 demos/occupied cell; 40 % of occupied cells have >=5
  * 4^5 = 1,024 cells → 301 occupied (29.4 %); median 2 demos/occupied cell; 27 % of occupied cells have >=5
  * 5^5 = 3,125 cells → 404 occupied (12.9 %); median 1 demos/occupied cell; 19 % of occupied cells have >=5

Principal spectrum of the task covariance: 1.51, 1.05, 0.99, 0.89, 0.57 — condition number 2.6. No direction is degenerate, so a linear map on these parameters is identifiable.

## 3. The decision

BRIEF 2c specifies **linear regression on W**, not a per-location library. That model is `W = A phi(task) + b`, fitted once across all demonstrations. Its parameter count is `n_basis x n_dof x (n_task + 1)`.

  * 10 basis functions x 3 DOF x 6 task terms = 180 parameters → 1,447 train demos gives 8.0 demos per parameter
  * 15 basis functions x 3 DOF x 6 task terms = 270 parameters → 1,447 train demos gives 5.4 demos per parameter
  * 20 basis functions x 3 DOF x 6 task terms = 360 parameters → 1,447 train demos gives 4.0 demos per parameter

The regression targets are per-demonstration W vectors, so the effective sample size is the number of *demonstrations* (1,447 train), not the number of ticks. With ridge regularisation, 1,447 demonstrations supports roughly 10-15 basis functions per DOF. That is enough for a 1.1 s ballistic arc with air control — the arc is close to a parabola plus a slow strafe correction, not a high-frequency signal.

### Widening from the all-maps staging: decided NO, for now

Reasons, measured:

1. **The bottleneck is not sample count, it is basis size.** 1,447 train demonstrations against ~180-270 regression parameters is 5-8 demos per parameter. Widening 4.1x would buy ~5,900 train demos — useful, but it does not unlock a different model class.
2. **The task space is already covered without holes.** Condition number 2.6 on the task covariance and no degenerate direction.
3. **Cost is real and the payoff is unproven.** The staging is 221 GB of NDJSON.zst across all maps; extracting rocket jumps from it means decompressing all of it. That is hours of CPU to test a hypothesis that a held-out fit on the existing data can test in minutes.

**Therefore: fit 2c on the 1,712 jumps first and measure held-out landing error. Widen only if held-out error is limited by sample count** — which shows up as a train/val gap that shrinks with more data, not as a floor. This is a reversible decision with a concrete trigger, recorded here so it is not quietly forgotten.

