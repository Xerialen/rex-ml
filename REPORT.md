# rex-ml — REPORT (2026-07-28)

Hybrid, risk-aware, hierarchical movement architecture for RTX. Every number below is
measured on this machine; the command that produced it is named. Nothing here is an estimate.

## Verdict up front

| BRIEF requirement | status | evidence |
|---|---|---|
| Step 1 — SE(2) transform + trim/maneuver segmentation | **done** | 27,934,383 ticks, 2,171,131 segments |
| Step 2a — demonstration density, widen or not | **done, decided NO** | train≈val error ⇒ model-limited |
| Step 2b — ground/bhop policy | **done, with a caveat** | 67.0 % held-out quadrant agreement |
| Step 2c — rocket-jump DMPs | **done** | 9.5 u median held-out landing error |
| Step 3 — MeshA* extended cells + CVaR | **done** | 1,058 µs mean — over budget, as predicted |
| Step 4 — automaton + Tracking Guard | **done** | 26.7 µs/tick, 19× headroom; 64/64 recover |
| Step 5 — headless self-play harness + RTX baseline | **done** | 420 s live match measured |
| — CPU/tick < 0.5 ms | **proven** | 26.7 µs measured |
| — Tracking Guard never leaves the bot stuck | **proven** | 64/64 seeds recover ≤ 400 ticks |
| — win-rate vs RTX / CVaR autotune | **not yet run** | policy not yet wired into the Rust bot |

**The mission's definition of done is not met.** Self-play now runs and the RTX baseline is
measured, but the baseline is RTX's *own* controller — the step 2b policy is not yet wired
into the game module, so there is no win-rate comparison to report. That remaining work is
bounded and named in [To finish the mission](#to-finish-the-mission).

An earlier revision of this report claimed step 5 was blocked because `mvdsv` and `pak0.pak`
were absent. That was wrong: the search behind it was depth-limited and case-sensitive, and a
working lab install was present at `~/mlx/qwserver/serverdir`. Corrected below.

## The architecture constraint: confirmed in both directions

BRIEF derived that "MeshA* with velocity-extended cells + CVaR does NOT fit in 0.5 ms per
frame" and asked for it to be proven or refuted early. Both halves are now measured.

| path | measured | budget | verdict |
|---|---|---|---|
| CVaR banded planner, dm3, 200 queries | **1,058 µs** mean / 2,188 µs p90 / 3,074 µs max | 500 µs | **2.1× over** |
| per-tick path (DMP + MLP + guard) | **26.7 µs** worst case | 500 µs | **19× under** |

So the design stands: the planner runs on a replan trigger and amortises; the per-tick path
carries only DMP integration, one MLP forward, and the guard. With four bots per frame the
per-tick path costs ~107 µs, still inside budget.

Reproduce:
```bash
RTX_TEST_BSP=/home/benjamin-adm/mvdinput-r80/dm3.bsp \
  cargo test -p rtx-nav --release cvar::tests::bench -- --nocapture
cargo test -p rtx-nav --release automaton::tests::bench -- --nocapture
```

## Step 1 — data extraction

Source is `~/dm3-extract/store-dm3`, chosen in `AUDIT.md` over re-parsing 161 GB of `.mvd`
(MVD is a server entity stream and carries no usercmds at any parse cost).

- **27,934,383 ticks** — exactly the audit's join count — 481 demos, **109.64 h**, 481 tracks.
- 2,171,131 segments: 421,568 `trim_ground`, 205,157 `trim_air`, 81,010 `maneuver_jump`,
  **1,759 `maneuver_rocket_jump`**, 91,513 `maneuver_external`.
- SE(2) invariance verified to **1.6e-4** relative across 27 features under three
  (θ, translation) pairs; the body-frame wishvel round-trip is exact to 2e-13.
- 1.53 GB on disk, 166 s wall.

Two findings that changed the implementation:

**`replay_ticks.onground` is unusable.** 46.2 % of ticks are flagged airborne while `vz == 0`
and z is unchanged — the player is standing on a floor. Segmenting on the raw column shatters
every ground run into 69,742 "airborne" runs of median length 3. Ground contact is derived
from vertical dynamics instead (`onground OR (vz == 0 AND NOT vz_prev > 0)`, the second clause
excluding the free-fall apex). Two physics checks: gravity recovered as `−dvz/dt` over 248,649
impulse-free air→air transitions has median **785.7 u/s²** against 800 in `movevars`, and over
681,237 ground→ground transitions it is **0.0**.

**Weapon fire alone does not identify a rocket jump.** Against a null that rolls the fire train
+499 ticks inside each track, `fire ≤ 12 ticks` gives only **1.41× lift** — mostly coincidence.
Adding "the blast pushes up" and "the player is aiming down > 20°" reaches **5.33× lift**
(~81 % precision). The cause is structural: only one slot per demo carries usercmds, so an
opponent's rocket, a lift and a teleporter are indistinguishable. Unattributable impulses are
labelled `maneuver_external`, never `rocket_jump`.

Independent ballistic confirmation, no statistics involved — a QW jump starts at `vz = 270`, so
its apex is `270²/2g = 45.6` units:

| label | air phases | median apex | median airtime |
|---|---|---|---|
| `maneuver_jump` | 81,010 | **+40.0 u** | 653 ms |
| `maneuver_rocket_jump` | 1,712 | **+220.3 u** | 1,119 ms |

## The pmove simulator, and a correction to step 1

`pipeline/qwphys.py` is a vectorised QW `PlayerMove`, validated against 6.19 M recorded
transitions: **median error 0.000 u/s in air** (64.6 % within 1 u/s), 0.678 u/s on ground.
The p90 tail (~22 u/s) is collision, which no collision-free model can capture.

Fitting the air-branch acceleration constant against data selects **10.0**, i.e.
`movevars.accelerate` — settling whether vanilla QW `PM_AirMove` passes `accelerate` or
`airaccelerate`.

Two bugs it caught:

1. **Quake's `(forward, right)` basis is left-handed** (det = −1), so a world rotation does not
   act on body coordinates as the same rotation. The wrong version cost 33 u/s of median ground
   error; correct, 0.68. The failure is silent — it preserves velocity magnitudes and only bends
   direction.
2. **Step 1's tick alignment was described backwards.** `replay_ticks[i]` is the **pre-move**
   state and `usercmd[i]` drives i → i+1. The jump measurement (`dvz = 270 − g·dt`) is
   consistent with both readings and could not discriminate; velocity prediction does, decisively.
   The step 1 feature table pairs state *i* with action *i* and was therefore already correct —
   only the prose was wrong.

## Step 2a — density, and the widening decision

1,712 rocket-jump trajectories (train 1,447 / val 121 / test 144).

*Spatially* the density is hopeless: on a 256-unit grid, of 414 (start, goal) pairs only **19
reach 20 demonstrations** and 48 % have exactly one. A DMP *library* indexed by map location is
not viable.

*In task space* — where `W = A·φ(task) + b` actually lives — coverage is fine: condition number
**2.6** on the task covariance, no degenerate direction, 5–8 demonstrations per regression
parameter.

**Decision: do not widen from the all-maps staging.** The trigger was set in advance ("widen only
if held-out error is sample-limited") and the step 2c result settles it: train and val error are
identical (46.5 vs 46.3 u), so the error is model-limited. 4.1× more data cannot help.

## Step 2b — locomotion policy

Dataset: 27.1 M locomotion ticks (rocket jumps, water and `maneuver_external` carved out —
the last because those ticks are an opponent's rocket moving the player, and imitating them
teaches the policy to reproduce being shot). Goal-conditioned by hindsight relabelling on the
recorder's own future position, which is what the step 3 planner will hand down.

Held-out results, in the order they were measured:

| model | fmove MAE | smove MAE | dyaw MAE | jump acc | **move quadrant** |
|---|---|---|---|---|---|
| TD3+BC | 129.7 | 163.4 | 3.93° | 95.8 % | 23.8 % |
| plain BC | 119.6 | 156.2 | 0.57° | 96.4 % | 24.5 % |
| **BC, discrete heads** | **108.9** | — | **0.56°** | **96.5 %** | **67.0 %** |

Three things happened here and all three are worth stating.

**TD3+BC diverged twice before it trained at all.** First the reward was raw closing speed —
unbounded, with the goal never an absorbing state, so the critic had nothing to anchor to and Q
ran 219 → 3,185 → 19,877. Normalising to the *fraction* of outstanding distance closed bounds
the undiscounted return by ~1. Q then still climbed, so the bootstrap target is clipped to its
analytic bound `1/(1−γ)`, which cannot bias a correct Q.

**TD3+BC then lost to plain BC on every held-out metric.** The critic saturates at that bound,
which makes `λ = α/|Q| ≈ 0.12` and leaves the actor ~88 % behaviour cloning anyway — while the
Q term degrades `dyaw` sevenfold. BRIEF permits the BC fallback "if you can show demonstration
density justifies it": 23.3 M training transitions for a 14→4 mapping does.

**Both were at chance on the thing that matters, and the fix was a loss function.** Move-quadrant
agreement of ~25 % is exactly chance for four quadrants. `forwardmove`/`sidemove` are not
continuous — they are keyboard axes, zero in 46 %/44 % of ticks and ±508 (22.5 %/16.3 %), ±400,
±320 otherwise. MSE regression collapses to the conditional mean near zero, and the *sign* of a
near-zero prediction is noise. Replacing each axis with a 3-way sign classifier took quadrant
agreement from 24.5 % to **67.0 %**, with `dyaw` and jump unchanged.

## Step 2c — rocket-jump DMPs

Ijspeert/Schaal DMP, 3 DOF in the blast-tick body frame, 12 basis functions. Per-demonstration
weights in closed form; across demonstrations a ridge map `W = A·φ + b`.

**The textbook scaling term is a trap here.** The standard forcing term carries `(g − y₀)`. A
rocket jump straight up has `|g − y₀| ≈ 0` horizontally, so the weights divide by ~0 and explode:
median landing error **5,528 u** against a 4.08 u per-demonstration reconstruction ceiling.
Unscaled forcing fixes it.

Two evaluation regimes, because they answer different questions:

| regime | train | val | test |
|---|---|---|---|
| **A. goal given** — landing error | 9.1 u | **9.5 u** | 10.3 u |
| A — within 32 u (the guard threshold) | 98 % | **94 %** | 97 % |
| A — path deviation from the human | 43.2 u | 41.7 u | 42.7 u |
| **B. goal predicted** — landing error | 190 u | 201 u | 209 u |

**Regime B fails completely, and that is an architectural finding.** Where a rocket jump lands
is *not* a function of the state at the blast — the human steers during flight. So the planner
cannot use a learned "where will I end up" model; it must name the target and let the DMP produce
the path to it. That is precisely BRIEF's step 3 → step 4 split, so the architecture holds.

Path deviation plateaus at ~42 u across basis counts (12 vs 20) and feature richness (linear 9-dim
vs quadratic 45-dim), with train ≈ val throughout. The residual is human in-flight decision-making,
not a deficit more data or more basis functions would close.

## Step 3 — risk-aware planner

Branch `rex-ml/step3-cvar`, commit `b7a515f`. `crates/rtx-nav/src/navmesh/cvar.rs` plus
`NavGraph::find_path_banded_cvar`.

**Half of step 3 already existed.** rtx-nav's `find_path_banded` already searches
`(cell, speed band)` states and refuses links the entry speed cannot satisfy — exactly the
velocity-extended cells BRIEF specifies. The missing half was risk.

Per-link loss is a two-point distribution, so CVaR has a closed form
`CVaR_β = d · min(1, p/β)`: β → 0 gives the worst case, β = 1 the mean. **β is the risk
threshold**, and the only quantity game state has to move.

`p_fail` for a rocket jump is **measured, not guessed: 0.06**, from step 2c's 94 % of held-out
jumps landing within 32 units.

Stated approximation: CVaR is sub-additive, so summing per-link CVaR *upper-bounds* the route's
true CVaR. Optimising the bound gives a conservative route — the right direction for a safety
term — and keeps the cost additive so A* stays optimal with respect to it.

**The first measurement was worthless and did not look it.** `NavGraph::build(bsp)` yields only
base links — zero rocket jumps — so the risk model was inert: `refused = 0`, β changed nothing.
With `add_double_jumps` + `add_rocket_jumps` the graph is 4,630 cells / 36,230 links including
**1,364 rocket jumps**, and the model bites: **107 of 198 routes change** between β = 1.0 and
β = 0.05, and **37 become unreachable at 30 HP** as lethal legs are refused. The neutral-to-averse
cost difference is 5 µs (0.5 %), below measurement noise — risk awareness is effectively free.

## Step 4 — integration

`crates/rtx-nav/src/automaton.rs`. `Mlp` (14→256→256→4, allocation-free), `Dmp` (12 basis × 3 DOF,
same basis placement as the Python fit so exported weights mean the same thing), `TrackingGuard`
(32 units, latching), `ManeuverAutomaton` (Locomotion / Maneuver / Fallback).

| component | ns/tick |
|---|---|
| MLP forward | 28,209 |
| DMP step | 67 |
| guard check | ~0 |
| **full tick, worst case** | **26,687 = 26.7 µs** |
| budget | 500,000 = 500 µs |

**A real deadlock, caught by its own test.** The guard latches. With the divergence edge evaluated
first, the `(Fallback, not diverged)` recovery arm was unreachable: while latched every `check`
returns Diverged, so `rearm` is never called, so the latch never clears — a braked bot sits on a
known cell forever, exactly the failure the guard exists to prevent. Fallback now owns the latch
and is evaluated first, on the physical settled condition (braked, on ground, near a known cell).
`fallback_never_leaves_the_bot_stuck` drives 64 entry speeds through a pmove-like brake integration
and requires recovery within 400 ticks: **64/64 recover**.

## Step 5 — validation

The harness is staged and self-play runs. `rtx/playground/` (gitignored) symlinks the owner's
existing private lab install at `~/mlx/qwserver/serverdir` — `mvdsv` 1.20-dev and
`id1/maps/dm3.bsp` — so the licensed data stays single-sourced and its `PROVENANCE.md` hash
(`d3af9f9cfb14041d…`) still verifies through the link. `playground/qw/qwprogs.so` is this
tree's own `target/release/librtx.so`.

Two of `AGENTS.md`'s stated requirements turned out to be wrong, both measured:

1. **A headless server needs no `pak0.pak`/`PAK1.PAK`** when the map is a loose `.bsp`. mvdsv
   boots, loads the module and spawns dm3 without them.
2. **`rtx_bot_alone 1` is load-bearing.** With `0`, the navmesh never builds and no bots spawn
   — and the symptom (`navmesh=none, cells=0, bots=0`) is indistinguishable from a broken
   install. It cost a 75-second run that collected nothing before I spotted it.

`crates/rex-selfplay` speaks the length-framed msgpack control protocol, polls `Status` at 5 Hz
and reports frags, the speed distribution, airborne fraction and stall events. The speed
distribution is there because frag counts cannot tell you whether a bot is bunny-hopping; the
stall counter is the live counterpart to the `fallback_never_leaves_the_bot_stuck` unit test.

### RTX baseline on dm3, measured live

Live navmesh: **4,634 cells, 36,956 links, 2,021 rocket-jump links** — more RJ links than the
1,364 my offline benchmark built, because the live build sees the `rtx_bot_rocketjump` cvar set
before `map`.

| | 2 bots, 120 s | 4 bots, **420 s** |
|---|---|---|
| samples / alive-bot samples | 569 / 1,129 | 1,966 / 7,794 |
| airborne fraction | 50.5 % | 37.2 % |
| speed p50 | 332.7 u/s | 283.4 u/s |
| speed p90 | 487.9 | 474.5 |
| speed max | 549.1 | **702.7** |
| **frags** | 0 | **7** (2 / 3 / 2 / 0) |
| **stall events** | 2 | **23** |

That is the win-rate baseline to beat: **7 frags in 7 minutes across 4 bots, with 23 stalls.**
The stall count is what the Tracking Guard is for — 0.8 stalls per bot-minute in the stock
controller is the number a guarded controller has to improve on.

### The calibration gap against the human corpus

| quantity | human corpus (step 1) | RTX bot (420 s) |
|---|---|---|
| median ground-trim entry speed | 313 u/s | 283 u/s |
| median air-trim entry speed | 362 u/s | — |
| **fastest air-trim exit** | **1,746 u/s** | **703 u/s** |
| airborne fraction | 28.4 % | 37.2 % |

The bot's *median* speed is human-like; its *peak* is 2.5× below human. It is airborne more
often than a human yet never converts that into speed — which is exactly the deficit a
strafejump policy trained on `trim_air` should close, and exactly the kind of evidence the
corpus exists to provide.

Reproduce:
```bash
cd rtx/playground && ./mvdsv -game qw -port 27600 +exec server.cfg   # in tmux; it must outlive the shell
./target/release/rex-selfplay 27700 420 base420.jsonl
```

## To finish the mission

1. **Export the trained policy into `automaton::Mlp` and wire it into `rtx-game`'s bot control
   path.** The discrete-head actor is `pipeline/out/policy/actor_disc.pt`; the Rust side needs a
   3-logit head per move axis rather than the current 4-output tanh, and `S_SCALE` must be
   reproduced exactly. This is the only thing standing between the measured baseline and a
   win-rate number.
3. **Retune `hp_to_seconds`.** At 0.05 the risk term reorders routes (107/198) but barely changes
   how many rocket jumps get used (105 → 102). That weight is step 5's autotune target.
4. **Optimise the MLP forward if a frame ever needs it.** 28 µs for 70 k MACs is ~2.3 GFLOP/s,
   well below what SIMD would give. There is no reason to do this until a measurement demands it.

## Artefacts

| path | contents |
|---|---|
| `AUDIT.md` | corpus audit and source decision |
| `PROGRESS.md` | dated log, every milestone with its measurements |
| `pipeline/` | steps 1–2c: transform, segmentation, pmove sim, policy, DMPs |
| `pipeline/out/step1_{ticks,segments,state_runs}/` | 27.9 M ticks, 2.17 M segments, 1.53 GB |
| `pipeline/out/validate_25.md` | step 1 measurement report |
| `pipeline/out/density_2a.md` | step 2a density and the widening decision |
| `pipeline/out/dmp/{model.npz,eval.json}` | step 2c weights and evaluation |
| `pipeline/out/policy/actor_disc.pt` | step 2b policy (discrete heads) |
| `rtx/` branch `rex-ml/step3-cvar` @ `b7a515f` | steps 3–4, 123 tests passing, rustfmt-clean |
