# BRIEF step 1 — validation on 25 demos

source: `/home/benjamin-adm/dm3-extract/store-dm3` (replay_ticks x usercmds on demo_key/slot/cmd_ordinal)
demo_keys: 60..2192 (deterministic, ORDER BY demo_key LIMIT 25)

## Volume

| rows | tracks | demos | wall-clock | load s | transform s | segment s |
|---|---|---|---|---|---|---|
| 1,008,237 | 25 | 25 | 4.09 h | 1.0 | 0.3 | 6.1 |

usercmd frametime: 14 ms: 521,963 (51.8%), 13 ms: 363,491 (36.1%), 17 ms: 23,482 (2.3%), 16 ms: 20,690 (2.1%)
mean tickrate: 68.6 Hz

## Ground contact: the `onground` column vs the derived signal

| signal | ticks | share |
|---|---|---|
| `onground = true` (store column) | 225,980 | 22.41 % |
| `vz == 0` | 691,259 | 68.56 % |
| derived ground, raw | 691,675 | 68.60 % |
| derived ground, debounced | 689,251 | 68.36 % |
| water (waterlevel > 0) | 25,729 | 2.55 % |

`onground = false` but derived ground: **465,742 ticks (46.19 % of all)** — the column misses this much ground contact.
`onground = true` but derived air: 2,471 ticks (0.245 %) — slope contacts where vz != 0.

gravity recovered from 248,649 impulse-free air->air transitions: median **785.7** u/s^2 (movevars says 800), mean 640.0, p1/p99 -814/1692

same test over 681,237 ground->ground transitions: median 0.0 u/s^2 — i.e. supported, gravity cancelled. This is the check that the derived signal is physical.

### Run lengths (contiguous state)

| state | runs | ticks | mean | p50 | p90 | max |
|---|---|---|---|---|---|---|
| ground | 8,327 | 689,251 | 82.8 | 18 | 209 | 2950 |
| air | 13,724 | 293,257 | 21.4 | 9 | 50 | 551 |
| water | 6,889 | 25,729 | 3.7 | 1 | 8 | 323 |

For contrast, segmenting on the raw `onground` column gives 69,742 airborne runs with median length 3 ticks vs 13,724 / 9 derived — the column shatters every ground run into stair-step noise.

## Events

| event | count | per minute |
|---|---|---|
| fire_edge | 5,292 | 21.6 |
| jump_edge | 4,445 | 18.1 |
| takeoff | 7,081 | 28.9 |
| land | 7,304 | 29.8 |
| impulse | 31,060 | 126.7 |

Takeoff vertical impulse `dvz` at the ground->air transition (n = 7,081):

| bucket | n | share |
|---|---|---|
| < 50 (walked off) | 3,189 | 45.0 % |
| 50–200 | 238 | 3.4 % |
| 200–340 (jump = +270) | 3,496 | 49.4 % |
| 340–600 | 129 | 1.8 % |
| > 600 | 29 | 0.4 % |

mean dvz inside the jump bucket: **256.5** u/s. PM_JumpButton adds 270 and PM_AirMove then applies one frame of gravity, so the expected value is 270 - 800*15.6ms = **257.5**. Agreement to 1.0 u/s confirms the tick alignment: `replay_ticks[i]` is the post-move state of usercmd i, and dvz[i] is the effect of usercmd i+1.

impulse magnitude |(dv_xy, grav_res)| on the 31,060 flagged transitions: p50 45, p90 237, p99 579 u/s. Physics bound for an honest air tick is 0 vertical and 4.2 horizontal.

### Does weapon fire actually explain the impulses?

Attribution is only meaningful if a blast follows the player's *own* attack at a specific latency. Latency here is (impulse tick - most recent fire edge), measured on impulses above the rocket threshold, against a null that shifts the fire train by +499 ticks inside each track.

| latency (ticks) | impulses with a fire that recent | null (fire train shifted) | lift |
|---|---|---|---|
| 0–3 | 259 (5.3 %) | 131 (2.7 %) | 1.98x |
| 4–7 | 156 (3.2 %) | 107 (2.2 %) | 1.46x |
| 8–15 | 238 (4.9 %) | 210 (4.3 %) | 1.13x |
| 16–31 | 317 (6.5 %) | 335 (6.9 %) | 0.95x |
| 32–63 | 409 (8.4 %) | 403 (8.3 %) | 1.01x |

total impulses above threshold: 4,857

## Segments

| kind | segments | ticks | % of ticks | mean ticks | p50 | mean dur ms | mean speed0 | mean dspeed |
|---|---|---|---|---|---|---|---|---|
| trim_ground | 15,006 | 357,089 | 35.42 % | 23.8 | 16 | 337 | 306 | -2 |
| trim_air | 7,731 | 183,394 | 18.19 % | 23.7 | 19 | 342 | 328 | -2 |
| maneuver_jump | 2,949 | 5,812 | 0.58 % | 2.0 | 2 | 31 | 393 | -0 |
| maneuver_rocket_jump | 74 | 208 | 0.02 % | 2.8 | 3 | 45 | 343 | +11 |
| maneuver_external | 4,212 | 16,235 | 1.61 % | 3.9 | 4 | 60 | 349 | -68 |
| maneuver_fall | 8,991 | 17,921 | 1.78 % | 2.0 | 2 | 29 | 199 | -0 |
| maneuver_land | 7,304 | 13,210 | 1.31 % | 1.8 | 2 | 28 | 269 | +2 |
| other_ground | 18,632 | 318,952 | 31.63 % | 17.1 | 8 | 256 | 263 | +23 |
| other_air | 11,374 | 69,687 | 6.91 % | 6.1 | 4 | 93 | 233 | -9 |
| water | 6,889 | 25,729 | 2.55 % | 3.7 | 1 | 52 | 153 | -1 |
| **total** | **83,162** | **1,008,237** | **100.00 %** | | | | | |

The `other_*` residue is 38.5 % of ticks. Of it, 36.0 % is below the 40 u/s floor where the body frame is ill-conditioned (standing, aiming, dead), and 64.0 % is moving but not steady — accelerating out of a turn or changing strafe direction. Neither is a trim, and neither is discarded: the ticks keep full features and a label.

### trim_air (7,731 segments, 183,394 ticks)

| quantity | p1 | p50 | p90 | p99 |
|---|---|---|---|---|
| entry speed (u/s) | 42 | 356 | 461 | 689 |
| speed gain over segment (u/s) | -129 | +0 | +19 | +52 |
| mean slip angle (deg) | -171.7 | +0.5 | +71.1 | +169.3 |
| |mean slip| (deg) | 0.1 | 10.5 | 112.6 | 175.7 |
| slip span within segment (deg) | 0.0 | 12.9 | 27.0 | 55.4 |
| mean turn rate (deg/s) | -252 | +0 | +119 | +275 |
| length (ticks) | 8 | 19 | 45 | 71 |
| planar distance (units) | 5 | 80 | 249 | 370 |

segments gaining > 20 u/s: 684 (8.8 %); max single-segment gain +134 u/s; fastest exit 1270 u/s (QW ground maxspeed is 320).

### trim_ground (15,006 segments, 357,089 ticks)

| quantity | p1 | p50 | p90 | p99 |
|---|---|---|---|---|
| entry speed (u/s) | 113 | 319 | 381 | 445 |
| speed gain over segment (u/s) | -232 | +3 | +83 | +154 |
| mean slip angle (deg) | -177.3 | -0.5 | +102.2 | +176.4 |
| |mean slip| (deg) | 0.2 | 44.7 | 144.1 | 179.0 |
| slip span within segment (deg) | 0.0 | 20.5 | 45.6 | 86.1 |
| mean turn rate (deg/s) | -346 | +0 | +102 | +342 |
| length (ticks) | 8 | 16 | 49 | 107 |
| planar distance (units) | 9 | 71 | 220 | 448 |

segments gaining > 20 u/s: 6,240 (41.6 %); max single-segment gain +265 u/s; fastest exit 584 u/s (QW ground maxspeed is 320).

### maneuver_rocket_jump — 74 segments, 0.30/min

peak impulse: p50 270, p90 664, max 868 u/s

the 73 distinct air phases these belong to:

| quantity | p10 | p50 | p90 | max |
|---|---|---|---|---|
| air time (ms) | 465 | 1123 | 1683 | 2504 |
| peak height above takeoff (units) | +7 | +204 | +321 | +419 |
| net height change (units) | -140 | +34 | +256 | +377 |
| peak speed (u/s) | 251 | 399 | 669 | 1270 |
| planar distance covered (units) | 41 | 254 | 515 | 1317 |

Median apex **+204 units** against 45.6 for a plain jump: 4.5x the ballistic ceiling of the jump button. These are a different population, which is the point of the label.

### maneuver_jump (plain +270) — 2,949 segments, 12.03/min

peak impulse: p50 1, p90 42, max 119 u/s

the 2,949 distinct air phases these belong to:

| quantity | p10 | p50 | p90 | max |
|---|---|---|---|---|
| air time (ms) | 494 | 653 | 1148 | 7872 |
| peak height above takeoff (units) | +34 | +40 | +40 | +419 |
| net height change (units) | -85 | -2 | +24 | +377 |
| peak speed (u/s) | 320 | 428 | 503 | 1768 |
| planar distance covered (units) | 72 | 247 | 375 | 1388 |

A QW jump is a ballistic arc from v0 = 270: apex = v0^2/2g = **45.6 units**. Measured median apex **+40** — the label is picking out plain jumps and nothing else.

## Integrity

| check | value |
|---|---|
| ticks labelled exactly once | 1,008,237 / 1,008,237 |
| contiguous chunks (breaks on gap/seq_break/bad msec) | 841 |
| ticks with no valid successor | 25 (0.00 %) |
| wire_state_present | 711,650 (70.58 %) |
| seq_break | 734 |
| non-finite in core features | {'speed_xy': 0, 'slip': 0, 'v_fwd': 0, 'v_right': 0, 'omega': 25, 'dx_loc': 25} |

`omega`/`dx_loc` non-finites are exactly the last tick of each chunk, which has no successor — masked, never interpolated.

## Thresholds used

```json
{
  "msec_min": 1,
  "msec_max": 50,
  "vz_zero_eps": 1e-06,
  "min_air_run": 2,
  "min_ground_run": 1,
  "impulse_dvz": 60.0,
  "impulse_dvxy": 40.0,
  "fire_window_before": 3,
  "fire_window_after": 1,
  "rocket_impulse_min": 120.0,
  "rocket_up_min": 0.5,
  "rocket_pitch_min": 20.0,
  "jump_dvz_lo": 200.0,
  "jump_dvz_hi": 340.0,
  "maneuver_pad": 2,
  "trim_min_len": 8,
  "trim_phi_tol": 0.2,
  "trim_omega_tol": 3.0,
  "trim_speed_rel_tol": 0.35,
  "trim_min_speed": 40.0
}
```
