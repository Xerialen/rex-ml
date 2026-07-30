# pipeline — BRIEF step 1

SE(2)-invariant transform + trim/maneuver segmentation over `~/dm3-extract/store-dm3`,
the artifact `AUDIT.md` recommended reusing.

## Layout

| file | what |
|---|---|
| `config.py` | every threshold, in one place, with the measurement that set it |
| `io_store.py` | duckdb read of `replay_ticks ⋈ usercmds` on `(demo_key, slot, cmd_ordinal)` |
| `se2.py` | the transform. Pure numpy, no I/O |
| `segment.py` | derived ground contact, event detection, trims and maneuvers |
| `build_step1.py` | batched full-scale run → parquet |
| `validate_sample.py` | the measurement report (`out/validate_25.md`) |
| `analyze_rocket.py` | diagnostic that set the rocket-jump thresholds |
| `tests/test_se2.py` | invariance tests |

Run:

```bash
.venv/bin/python -m pipeline.tests.test_se2
.venv/bin/python -m pipeline.validate_sample --demos 25 --out pipeline/out/validate_25.md
.venv/bin/python -m pipeline.build_step1 --batch 40 --tag step1
```

## The transform

Group action: translate by `(a,b)` in the ground plane and rotate by `θ` about z.
Under it `x→Rx+t`, `v→Rv`, `yaw→yaw+θ`, and `z`, `pitch` are fixed.

The body frame is Quake's own horizontal view basis (`AngleVectors` with the
pitch component zeroed, which is exactly what `PM_AirMove` does):

```
e_f = ( cos yaw,  sin yaw)
e_r = ( sin yaw, -cos yaw)
```

This basis is left-handed. That is Quake's convention, and it is what makes
`wishvel_local == (forwardmove, sidemove)` exactly, with no sign correction —
verified to 2e-13 in `test_frame_matches_quake`. The consequence to remember:
a positive slip angle means the velocity points to the player's **right**.

Emitted per tick: velocity in the body frame, speed, slip angle, turn rate, view
pitch, the wish vector and its angle to the velocity (`wish_slip`, the variable
that governs strafejump acceleration), the raw move axes, the mouse deltas
`dyaw`/`dpitch`, and the transition to the next tick expressed in the frame at
this tick. Absolute `x`, `y`, `yaw` are carried in memory for bookkeeping and
are **not written** to the feature table.

`test_se2.py` checks invariance to 1.6e-4 relative across all 27 invariant
features under three different (θ, a, b), and to 2.2e-4 absolute under pure
translation — the float32 storage floor, not slack in the transform.

## Ground contact is derived, not read

`replay_ticks.onground` cannot be used as-is. Measured over 25 demos /
1 008 237 ticks: **46.2 % of all ticks are flagged `onground = false` while
`vz == 0` and z is unchanged** — the player is standing on a floor. Segmenting
on the raw column yields 69 742 "airborne" runs of median length 3 ticks; it
shatters every ground run into stair-step noise.

The derived rule is a support test on the vertical dynamics:

```
ground = onground_flag OR (vz == 0 AND NOT vz_prev > 0)
```

Gravity is the only vertical force in flight, so a free-falling tick has
`vz == 0` only at the apex — excluded by the second clause. `onground` is OR-ed
in to catch slope contacts (0.25 % of ticks, where `vz != 0` but the flag is
set), so the derived signal is a strict superset of the column.

Two checks that this is physical, not a heuristic:

* over 248 649 impulse-free air→air transitions, gravity recovered as
  `-dvz/dt` has median **785.7 u/s²** against the 800 in `movevars`;
* over 681 237 ground→ground transitions the same quantity is **0.0** — that is
  what "supported" means.

## Trims and maneuvers

Framing is the maneuver automaton (Frazzoli/Dahleh/Feron), which is what BRIEF
step 4 asks for. A **trim** is a relative equilibrium of the symmetry-reduced
dynamics: the shape variables (slip angle, turn rate) hold steady while the
world-frame motion sweeps an arc. A **maneuver** is a finite-time transition
between trims. Segment boundaries come from exactly the two signals BRIEF step 1
names — ground contact and weapon fire — plus the impulse test that separates a
rocket blast from a jump.

Speed is allowed to drift inside a trim: a strafejump gains speed while holding
its shape, so freezing speed would forbid the very primitive we want.

### Rocket-jump attribution

Fire alone does not identify a rocket jump. Only the recorder's usercmds exist
(one slot per demo, per AUDIT), so an enemy's rocket, a lift, a teleporter and a
`trigger_push` all look like the same impulse. Scored against a null that rolls
the fire train forward 499 ticks inside each track:

| rule | lift over null | events/min |
|---|---|---|
| fire ≤ 12 ticks | 1.41x | 0.56 |
| fire ≤ 3 + blast points up | 2.16x | 0.28 |
| fire ≤ 3 + up + pitch > 10° | 2.70x | 0.25 |
| **fire ≤ 3 + up + pitch > 20°** | **5.33x** | **0.20** |

5.33x is roughly 81 % precision. Recall is traded away deliberately: a
mislabelled rocket jump poisons the DMP regression in BRIEF step 2, a missed one
only costs a demonstration. Impulses that fail the test are labelled
`maneuver_external` rather than silently dropped or wrongly claimed.

The independent confirmation is ballistic, not statistical. A QW jump starts at
`vz = 270`, so its apex is `270²/2g = 45.6` units:

* air phases labelled `maneuver_jump` — median apex **+40 units**
* air phases labelled `maneuver_rocket_jump` — median apex **+204 units**, 4.5×
  the ceiling the jump button can reach

## Output

`build_step1.py` writes three parquet datasets under `out/`:

* `step1_ticks/` — one row per tick, 47 columns: invariant state, action,
  transition, derived ground state, segment label, event flags, `split`
* `step1_segments/` — one row per trim/maneuver
* `step1_state_runs/` — one row per contiguous ground/air/water run, so a
  maneuver can be related to the air phase it belongs to

## Caveats carried forward

* 29 % of ticks are replay-integrated (`wire_state_present = false`). The column
  is written through so it can be used as an ablation filter.
* `maneuver_external` is unattributable **by construction**, not by a gap in the
  classifier — the POV demo has no opponent usercmds.
* Ticks below 40 u/s are labelled `other_*`: the body frame is ill-conditioned
  when the velocity is near zero, so slip angle is meaningless there.
