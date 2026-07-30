# rex-ml — MISSION (v2, 2026-07-28). Standing mandate: do not stop between steps.

## The goal
Beat RTX. Build a hybrid, risk-aware, hierarchical movement architecture giving human
movement quality + superhuman efficiency. **Hard budget: < 0.5 ms CPU per frame.**

**Definition of done for the whole mission:** a bot that beats the current RTX baseline
in headless DM3 self-play by a statistically meaningful margin, with per-tick CPU proven
under 0.5 ms, and a Tracking Guard that demonstrably never leaves the bot stuck.

## STANDING MANDATE — read this twice
You are NOT waiting for instructions between steps. Work continuously through steps 2->5.
When a step is done, append to PROGRESS.md and **immediately start the next one**.

Stop and ask ONLY if: (a) an action would delete or overwrite data, (b) a job needs
>20 GB disk or >4h wall-clock, (c) a measurement contradicts the architecture badly enough
that continuing would waste days, or (d) you need a human judgement call that no measurement
can settle. Everything else: decide it yourself, write down the assumption, keep moving.

"I finished what was asked and await your call" is a FAILURE MODE here. The ask is the
whole mission, not the current step.

## Established facts (measured — do not re-derive, do not contradict without new evidence)
- **RTX is RUST.** `~/rex-ml/rtx` = `qw-ctf/rtx` main @ 5df7da8. Crates: `rtx-nav` (navmesh+A*),
  `rtx-game`, `navview`, `rjmcp`. There is no C code to modify — the original brief was wrong.
- **Data source is `~/dm3-extract/store-dm3`.** NOT the .mvd corpus — MVD is a server entity
  stream and carries no usercmds at any parse cost. See AUDIT.md.
- **Step 1 is DONE** (`~/rex-ml/pipeline/out/`): 27,934,383 ticks x 47 cols; 2,171,131 segments;
  205,157 trim_air + 421,568 trim_ground; 1,759 maneuver_rocket_jump; splits train 24.25M /
  val 1.75M / test 1.93M. SE(2) invariance 1.6e-4; gravity 785.7 vs 800 u/s².
- **Only 487 demos carry usercmds** (one slot each — the recorder). Opponent state exists as
  trajectories only, never as control signals. Protocol limit, not a data gap.
- Env: `~/rex-ml/.venv` (uv, py3.12), torch 2.13.0+cu130, H100 NVL 96 GB. No sudo.
- Disk is the only scarce resource: ~186 GB free. Corpora are write-protected and irreplaceable.
  `rm`/`rmdir`/`shred`/`dd`/`git clean` are DENIED — ask instead of retrying.

## Architecture constraint (derived — prove or refute it with measurement)
MeshA* with velocity-extended cells + CVaR does NOT fit in 0.5 ms per tick. Run the planner
on a replan trigger and amortise it. The per-tick path may contain only: DMP integration,
MLP forward, tracking guard. **Measure this early** — if it refutes the design, say so loudly.

## STEP 2 — local control policies
**2a. First action: measure demonstration density per start/goal region** for the 1,759 rocket
jumps. That count may be too thin for DMP regression on W. If it is, widen from the all-maps
staging (`~/qw-corpus-build/task10-42926d4/staging`, 4.1x more replay_ticks, identical schema)
rather than re-parsing anything. Decide this yourself on the measurement.
**2b. Ground (bhop/strafe):** compact fast MLP for continuous control. Use TD3+BC to bound
out-of-distribution error; fall back to plain BC only if you can show demonstration density
justifies it. Report held-out action error, not training loss.
**2c. Air (rocket jumps):** linear regression on the segmented maneuvers to extract DMP weights W.
Encode as Transformation System + Canonical System. Prove landing accuracy on held-out jumps.

## STEP 3 — planner (in rtx-nav)
MeshA* over **extended cells** = navmesh cell x quantised velocity vector, so the planner
never proposes a jump the bot lacks speed for. Integrate **CVaR** into the cost function:
high risk threshold (safe routes) when the bot leads or has health; low threshold (short,
dangerous, rocket-jump routes) when behind. Report search time and node counts.

## STEP 4 — integration
Maneuver automaton linking the discrete MeshA* route to continuous control: exact transitions
DMP <-> policy. **Tracking Guard:** continuously measure tracking error between desired and
actual position; if it exceeds **32 units**, immediately disengage neural control and DMPs,
and hand to an analytic fallback that brakes and navigates to the nearest known navmesh polygon.

## STEP 5 — validation
Headless DM3 self-play vs previous bot versions, thousands of iterations. Prove CPU/tick
< 0.5 ms. Prove the Tracking Guard prevents stalls. Auto-tune CVaR weights on win-rate.
Write the final report to ~/rex-ml/REPORT.md.

## Working rules
- Append to PROGRESS.md after every milestone: what you did, what you MEASURED, what's next.
- Long jobs go in tmux window `jobs` (`tmux send-keys -t rexml:jobs`), never blocking your context.
- State disk cost before any job writing >5 GB.
- Report measurements, never claims. "Done" requires evidence.
- Human corpus data is calibration evidence only — never feed raw trajectories/usercmds
  straight into bot code.
- Keep the rtx working tree on a branch; don't push anywhere.
