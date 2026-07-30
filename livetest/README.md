# livetest — local rtx live-test rig

**This is not `rtx-testflow/1`.** The lab suite could not be fetched (see *Transport* below), so
this directory reproduces the two tiers that are honestly reproducible from what is on this
machine, using the repo's own control channel and the repo's own measurement definitions.
Envelopes carry the schema id **`rex-drills/1`** so they can never be mistaken for, or pooled
with, suite results.

## Transport — why the suite is absent

`git clone xerial@lanister:projects/quakeworld/rtx` fails with
`Could not resolve hostname lanister`. Verified, in order:

- no `lanister` entry in `/etc/hosts`; `getent hosts lanister` fails
- `ssh -G lanister` shows no config alias — the hostname stays literal, so there is no
  `Host lanister` stanza redirecting it to an IP
- no mDNS resolver installed (`lanister.local` also fails)
- the reachable remote `github.com/qw-ctf/rtx` has **only `main`** (`5df7da8`) — no `testsuite`
  branch, so it is not a substitute source
- filesystem-wide search found no `testflow.py`, `t4.py`, `combat_lock.py`, or `testsuite/` dir

Consequently `testsuite/README.md` and `testsuite/schema/SCHEMA.md` — the stated contract — were
never read, and `testflow.py selftest` was never run. Nothing here should be treated as satisfying
that contract.

## What ran

| Tier | What it asserts | Result |
|---|---|---|
| **T0** preflight | Every precondition a live movement tier depends on | 20/20 passed |
| **T1** movement drills (run 1, as pre-registered) | 150 declarative dm3 routes, 20 s timeout floor, telemetry off | **failed** — 93/150 arrived; see `evidence/t1_full.json` |
| **T1** movement drills (run 2, corrected rig) | Same 150 routes, 60 s floor, telemetry on | see `evidence/t1_corrected.json` |
| **T1-H** human-time drills | 17 hand-recorded routes; the bot must match the recorder's own time | **failed** — 4/80; see below |

## T1-H — beat the human's recorded time

The owner supplied hand-recorded `.qwd` demos of dm3 routes and set the gate: *"treat them as input
for start and end points and how long it takes me to get there, and loop until the bots reach the
same time or better."* That replaced the 100m speed bar as the optimisation target, and it is a
better target — it is the mission's own gate (route completion time) with a human reference instead
of an arbitrary number.

`../demos/demo_runs.py` turns each demo into a timed start→goal run. Three things there are worth
knowing because each one was a bug first:

- **A teleport is not a respawn.** Both move the player further in one frame than physics allows, so
  distance cannot separate them. Speed can: a teleporter shows ~450 u/s in and exactly ~300 u/s out
  (QW sets the exit speed), a respawn shows 0 on both sides. Splitting on distance alone dropped the
  whole `ya-to-tele-to-window-to-rl` drill as "never arrived".
- **A teleport is not distance travelled either.** Counting the 1 491-unit hop as path put the
  recorder at a mean 930 u/s. Hops over 300 u are excluded on both sides — the same threshold is now
  applied in `corridor_metrics`' `path_len`, so the two mean speeds are comparable.
- **Clock forward, not backward.** Timing from the last standstill *before the arrival* silently
  retimed `spawn-lift-to-pent-to-pentmega` from its midpoint, because the recorder pauses at Pent.
  The clock now starts at first motion and mid-route pauses are counted and reported (`pauses`).

The bot's goal is set to the recorder's **own arrival point**, not the item origin: the human counted
as arrived within 128 u of RL while the bot's arrival test is 24 u xy / 48 u z, so without that they
would be running to different places.

### No rocket jumps except on one drill

The owner's rule: the bot may rocket-jump only on `rj-pent-to-lifts-to-window-to-quad`. This is not a
cvar you can just set — `rtx_bot_rocketjump` is read **only when the navmesh is built**
(`nav_build.rs:201`), so setting it to 0 on a live server looks obedient while all 2 021 rocket-jump
links stay in the graph. It needs a map reload, and the effect is visible in the link count:

| regime | cells | links | rj_links |
|---|---|---|---|
| A — `rtx_bot_rocketjump 0` | 4 634 | 34 935 | **0** |
| B — default | 4 634 | 36 956 | 2 021 |

It mattered: the bot had been rocket-jumping on at least four routes where the human does not, and
removing that cost it 3.9–9.2 s on those. An earlier reported "the bot beats the human on 2 of 7" was
partly an artifact of it using a move the human never used. Under the same rules it wins on one.

Three routes got *faster* without rocket-jump links, which is its own finding: the planner was
choosing rocket jumps that were slower than running.

### The gap is mostly detour, not speed

Baseline, 16 routes × 5 reps in regime A (`evidence/t1_norj_baseline.raw.json`), total gap
**−99.3 s**. Splitting each drill into "time lost running further" and "time lost running slower":

| | seconds |
|---|---|
| detour | **−70.8 (71 %)** |
| speed | −28.5 (29 %) |

The control that makes this credible is inside the same data: on the three routes where the bot's
path matches the human's (ratio 0.99–1.04) the margin is only −1.0 to −2.6 s, and on the routes where
its path is 2–3.7× longer the margin is −9 to −14 s. Same bot, same speed, different distance.

### Why there are two T1 runs

Run 1 is kept exactly as recorded — it failed, and a failed result stays failed. But analysing it
showed the rig, not only the bot, was being measured, on two counts:

1. **The timeout floor set almost every budget.** 134 of 150 budgets were the 20 s floor rather
   than the distance term. The timeout population sat on systematically longer chords than the
   arrivals (p50 1,720 u vs 1,050 u), and the slowest arrival landed at 20.6 s against that 20 s
   floor — so some "timeouts" were drills cut off, not drills stuck. Confirmed directly: on re-run
   with a 60 s floor, `r021` arrived in 25.1 s.
2. **The watchdog column was empty because the events were switched off.** `BotStall` is gated
   behind `rtx_telemetry`, which defaults to `0` (`crates/rtx-game/src/control.rs:190`). Run 1
   therefore reported zero steering-watchdog firings across 150 drills, which reads as health but
   actually means *no data*. Run 2 sets `rtx_telemetry 1` and drops the resulting per-frame `Pmove`
   flood in the reader thread.

Run 2's 60 s floor is justified independently of the outcome, not tuned to it: the longest chord in
the route set is 2,844 u, so failing at 60 s implies an average speed under 47 u/s. Detecting a
genuinely stuck bot is left to the server's own `GotoStall` (4 s of zero movement) — a statement
about physics rather than about patience.

Run 2 does not overwrite run 1, and the failures are not all budget artefacts: `r016`/`r018` trip
`GotoStall`, `r019` reaches 0 units from the goal and cannot climb the last step to the LG, and
`r011` still fails to arrive with a full 60 s. Those are real movement defects.

The build under test is the rex-ml branch's game module, staged as
`playground/qw/qwprogs.so`. `mkevidence.py` records its md5 **and** checks it is byte-identical to
`target/release/librtx.so`, because the digest of the artifact the server actually `dlopen`s — not
the repo commit — is what proves the ML build ran.

### T0 — preflight

Twenty checks, each asserted separately so a failure names itself: control channel answers;
navmesh `ready` with non-zero cells / links / rocket-jump links; the five stock movevars
(`sv_gravity` 800, `sv_maxspeed` 320, `sv_accelerate` 10, `sv_friction` 4, `sv_stopspeed` 100) —
a hard precondition, since a drill run under different physics is not comparable to the step 1
corpus; the read-only verbs (`Maps`, `Items`, `Links`, `Cell`, `Route`); a live bot on the roster;
and finally that a puppet `Teleport` actually moves the body. That last one is the check that
separates "the rig works" from "the rig answers questions".

The motivation is specific: the single most expensive failure in this project was a
misconfigured rig (`rtx_bot_alone 0`) that reported `navmesh=none, cells=0, bots=0` — externally
indistinguishable from a broken build. T0 exists so a T1 failure means *movement*.

### T1 — declarative movement drills

Drills come from `~/route-sheet-search/routes.json` (150 dm3 routes, the same fixed route set the
brief gates on), converted to `drills.json`. Each drill:

1. snaps both endpoints to the nearest standable nav cell via `Cmd::Cell` — route endpoints are
   item and spawn origins, which float above the floor, and a `Goto` at one stalls under the pickup
2. `Prep`s the bot to full health and rockets, `Teleport`s it to the start, settles 600 ms so the
   first trajectory sample is a standstill rather than the previous order's momentum
3. issues `Goto`, then reads the planner's own route with `Cmd::Route` to get the **planned path
   length**, and budgets the timeout over that at a conservative 120 u/s
4. waits for `Arrived` (pass) or `GotoStall` (fail), and records every `BotStall` watchdog firing
   seen along the way

Metrics are ported verbatim from `rtx-mcp`'s `corridor_metrics` so the numbers mean the same thing
the lab's do: elapsed, peak speed, max cross-track, max heading error, max yaw step, reverse
frames, z gain.

**Only arrival is gated.** Cross-track drift and reverse frames are reported but not thresholded:
`corridor_metrics` was designed for a straight runway, and these are full map routes, so large
deviation from the chord is expected rather than a defect.

**The timeout budget is over planned path length, not straight-line distance.** Budgeting on the
chord failed long routes for being long rather than for being slow. Note the honest caveat: drill
`r004` timed out at 20 s in a first smoke run and then completed in 8.6 s on a re-run under the
same 20 s floor, so that drill's outcome is run-to-run variance, not something the budget change
fixed.

## Running it

```sh
# server (must be in tmux — a plain foreground shell call is killed with the tool call)
tmux send-keys -t rexml:drills "cd ~/rex-ml/rtx/playground && \
  ./mvdsv -game qw -port 27600 +exec server.cfg" Enter

cd ~/rex-ml/livetest
../rtx/target/release/rex-drills 27700 preflight evidence/t0_preflight.raw.json
python3 mkevidence.py evidence/t0_preflight.raw.json evidence/t0_preflight.json

../rtx/target/release/rex-drills 27700 drills drills.json evidence/t1_full.raw.json   # add N to cap
python3 mkevidence.py evidence/t1_full.raw.json evidence/t1_full.json

python3 dashboard/build_dashboard.py --evidence-dir evidence --output dashboard.html
```

`rtx_bot_alone 1` in `server.cfg` is load-bearing: with `0` the navmesh never builds and no bots
spawn. A headless server needs no `pak0.pak` when the `.bsp` is loose.

## Deviations from the README's assumptions

- **No suite.** T0/T1 here are reconstructions, not the lab's tiers. T2 (600 s pacifist
  free-play) is constructible from `rex-selfplay`, which already measures speed distribution,
  airborne fraction and stalls; T3/T4 are not, for the reasons below.
- **T3/T4 not attempted.** T3 needs a stock `main` reference build and a dedicated mvdsv+KTX rig;
  T4 additionally needs frogbots and the KTX `bots/` data dir. KTX is present at
  `~/mlx/qwserver/serverdir/ktx`, but the runner that seats frogbots via a spectator client is
  part of the missing suite.
- **`100m` was measured after all (correction).** At the time of the dm3 runs the only loose map was
  `dm3.bsp`, so the documented `100m` corridor was reported here as unmeasurable. `100m.bsp` was
  staged into `~/mlx/qwserver/serverdir/id1/maps/` at 08:30 the same morning, and the corridor has
  since been run — 10 reps, see `evidence/t1_100m_bar.json` and [RESULTS.md](RESULTS.md). It
  **misses** the documented `800+ ups` bar at ~772 u/s.
- **`100m` needs exactly one bot.** The map has a single `info_player_start` and no
  `info_player_deathmatch` at all. With `rtx_bot_count 4` all four bots spawn on that one spot,
  telefrag each other in a loop, exhaust the entity pool (`ED_Alloc: no free edicts [512]`) and kill
  the server. `qw/server_100m.cfg` sets `rtx_bot_count 1`; a corridor drill needs one bot anyway.
- **`verb_items` was a map-specific assertion (fixed).** T0 required a non-empty item list, which
  failed on `100m` — a bare runway with no pickups — while nothing was wrong. The check now asserts
  only that the verb answers, and reports the count.
- **No screenshot.** No headless browser exists on this machine (no chromium/chrome/firefox, no
  `wkhtmltoimage`, no `playwright`) and pip installs are disallowed, so `dashboard.html` is
  delivered as a file rather than an image.
- **Combat isolation is structural, not a setting.** T1 sets `rtx_bot_pacifist 1` and parks the
  other three bots, and both are in fact redundant: a bot under a puppet order returns from
  `bot_objective` early with `enemy: None` and item chasing suppressed
  (`crates/rtx-game/src/bot/mod.rs:922`), *before* the pacifist branch is evaluated — and `Hold` is
  itself a puppet order, so the parked bots are equally unaffected. The isolation therefore comes
  from the control protocol's design, which is stronger than a cvar. The consequence stands either
  way: **T1 says nothing about movement under fire.** The cvar is still recorded in each envelope's
  `conditions` because it was set.
- **The repo is dirty.** `rex-drills` itself is a new uncommitted binary on branch
  `rex-ml/step3-cvar`; the envelopes report `dirty: true` rather than hiding it.
- **`cargo test` was failing on this tree, and it was the benchmark's fault, not the bot's.**
  `automaton::tests::bench_per_tick_budget` asserts the brief's hard 0.5 ms per-tick budget, but
  `cargo test` defaults to the debug profile, where the same code measures **531 µs** — a ~20x
  penalty on the MLP's inner loops from no inlining and no vectorisation. Under `--release` it is
  **26.6 µs, 19x headroom**, matching the previously recorded 26.7 µs. So the invariant holds; the
  test was measuring the wrong build. It now always prints the measurement and enforces the bar only
  when optimised. Anyone checking that invariant must use `cargo test --release`.
- **A stale artefact is left in `evidence/`.** `t1_diag_failures.raw.json` holds a vacuous 0-drill
  run: I passed `max_drills=0`, which truncated the spec to empty, and the runner reported a result
  over zero drills instead of refusing. The runner now exits 2 on an empty spec. The file itself
  could not be removed — `rm` is denied by policy in this environment — so it is called out here
  instead. No envelope was built from it, and `build_dashboard.py` ignores `*.raw.json`.
- **The ML movement layer is not actually wired in.** `automaton.rs` and the trained policy exist
  in `rtx-nav` but are not called from `rtx-game`'s bot control path, so T0/T1 here measure the
  existing rtx controller in an ML-branch build. This is the honest reading of these numbers and
  the reason they are a baseline, not a comparison.
