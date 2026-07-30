# rex-ml — ALWAYS-LOADED MISSION ANCHOR

This file is re-injected into context automatically, including after autocompact.
If you are reading this after a compaction: **you are mid-mission, not starting fresh.**

## Resume ritual (do this FIRST after any compaction)
1. Read `~/rex-ml/PROGRESS.md` — the last entry tells you exactly where you are.
2. Read `~/rex-ml/BRIEF.md` — the full spec, steps 1-5.
3. Determine the current step. Continue it. Do not ask what to do.

## Standing mandate
Work continuously through BRIEF steps 2 -> 5. When a step finishes, append to PROGRESS.md
and **immediately begin the next one**. "I finished what was asked and await your call" is
a FAILURE MODE. The ask is the whole mission.

Stop and ask ONLY for: deleting/overwriting data, a job needing >20 GB or >4h, a measurement
that invalidates the architecture, or a judgement no measurement can settle. Otherwise decide
yourself, record the assumption in PROGRESS.md, keep moving.

## The terminating goal — the mission is DONE when BOTH hold

**A/B design: combat is held IDENTICAL to the RTX baseline. Only the movement layer differs,
so any measured delta is causally attributable to movement.** Do not touch `bot/combat/`,
`bot/goals.rs`, `bot/grenade.rs` or `bot/perception.rs`.

1. **Faster routes.** Candidate beats the RTX baseline on route completion time over a fixed
   DM3 route set (`~/route-sheet-search/routes.json`) — median over >= 30 runs per route,
   with a 95 % CI that excludes zero improvement. **First establish the RTX baseline times**;
   you cannot gate on beating a number you have not measured.
2. **Never stuck.** Zero stuck episodes across the validation run — the Tracking Guard
   disengages at >32 units tracking error every time and the analytic fallback recovers.

When both are measured and hold: write `~/rex-ml/REPORT.md` with the evidence, then stop.
REPORT.md existing is the ONLY signal that the mission is over.

### Hard constraint (not a gate — an invariant)
**p99 CPU per game tick < 0.5 ms** for the full per-tick path (DMP integration + MLP forward +
tracking guard); amortised planner counted separately. This was an absolute requirement in the
original brief. Any candidate that violates it is REJECTED during development, not shipped and
excused later. Measure it continuously, not once at the end.

### Measure and report, but do NOT gate on
- Rocket-jump landing accuracy on held-out demonstrations.
- Self-play win rate vs the RTX baseline. Winning DM3 depends heavily on aim and combat, which
  we are deliberately not changing — so win rate is evidence, never the finish line.

## Checkpoint discipline (this is what makes compaction survivable)
PROGRESS.md must always be current enough that a fresh context can resume from it alone.
Append after every milestone: what you did, what you MEASURED (numbers, not adjectives),
what is next, and any assumption you decided yourself. Write it BEFORE starting long jobs,
not after — a compaction mid-job must not lose the plan.

## Guardrails
- Disk is the only scarce resource (~186 GB). State cost before any job writing >5 GB.
- Corpora are irreplaceable and write-protected. `rm`/`rmdir`/`shred`/`dd`/`git clean` DENIED.
- Long jobs go in tmux window `jobs`, never blocking your own context.
- Measurements, never claims. "Done" requires evidence.
