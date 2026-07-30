# BRIEF step 1 — validation on 10 demos

source: `/home/benjamin-adm/dm3-extract/store-dm3` (replay_ticks x usercmds on demo_key/slot/cmd_ordinal)
demo_keys: 60..884 (deterministic, ORDER BY demo_key LIMIT 10)

## Volume

| rows | tracks | demos | wall-clock | load s | transform s | segment s |
|---|---|---|---|---|---|---|
| 598,306 | 10 | 10 | 2.33 h | 0.7 | 0.3 | 2.8 |

usercmd frametime: 14 ms: 308,052 (51.5%), 13 ms: 228,784 (38.2%), 17 ms: 18,878 (3.2%), 16 ms: 15,886 (2.7%)
mean tickrate: 71.4 Hz

## Ground contact: the `onground` column vs the derived signal

| signal | ticks | share |
|---|---|---|
| `onground = true` (store column) | 115,318 | 19.27 % |
| `vz == 0` | 408,958 | 68.35 % |
| derived ground, raw | 409,052 | 68.37 % |
| derived ground, debounced | 407,897 | 68.18 % |
| water (waterlevel > 0) | 12,151 | 2.03 % |

`onground = false` but derived ground: **293,652 ticks (49.08 % of all)** — the column misses this much ground contact.
`onground = true` but derived air: 1,073 ticks (0.179 %) — slope contacts where vz != 0.

gravity recovered from 151,969 impulse-free air->air transitions: median **785.7** u/s^2 (movevars says 800), mean 663.6, p1/p99 -814/1692

same test over 403,159 ground->ground transitions: median 0.0 u/s^2 — i.e. supported, gravity cancelled. This is the check that the derived signal is physical.

### Run lengths (contiguous state)

| state | runs | ticks | mean | p50 | p90 | max |
|---|---|---|---|---|---|---|
| ground | 4,918 | 407,897 | 82.9 | 22 | 201 | 2240 |
| air | 6,911 | 178,258 | 25.8 | 13 | 52 | 551 |
| water | 2,946 | 12,151 | 4.1 | 2 | 10 | 213 |

For contrast, segmenting on the raw `onground` column gives 31,279 airborne runs with median length 2 ticks vs 6,911 / 13 derived — the column shatters every ground run into stair-step noise.

## Events

| event | count | per minute |
|---|---|---|
| fire_edge | 3,091 | 22.1 |
| jump_edge | 2,728 | 19.5 |
| takeoff | 4,166 | 29.8 |
| land | 4,296 | 30.7 |
| impulse | 19,474 | 139.4 |

Takeoff vertical impulse `dvz` at the ground->air transition (n = 4,166):

| bucket | n | share |
|---|---|---|
| < 50 (walked off) | 1,778 | 42.7 % |
| 50–200 | 144 | 3.5 % |
| 200–340 (jump = +270) | 2,175 | 52.2 % |
| 340–600 | 58 | 1.4 % |
| > 600 | 11 | 0.3 % |

mean dvz inside the jump bucket: **257.9** u/s. PM_JumpButton adds 270 and PM_AirMove then applies one frame of gravity, so the expected value is 270 - 800*14.2ms = **258.7**. Agreement to 0.8 u/s confirms the tick alignment: `replay_ticks[i]` is the post-move state of usercmd i, and dvz[i] is the effect of usercmd i+1.

impulse magnitude |(dv_xy, grav_res)| on the 19,474 flagged transitions: p50 45, p90 205, p99 542 u/s. Physics bound for an honest air tick is 0 vertical and 4.2 horizontal.

### Does weapon fire actually explain the impulses?

Attribution is only meaningful if a blast follows the player's *own* attack at a specific latency. Latency here is (impulse tick - most recent fire edge), measured on impulses above the rocket threshold, against a null that shifts the fire train by +499 ticks inside each track.

| latency (ticks) | impulses with a fire that recent | null (fire train shifted) | lift |
|---|---|---|---|
| 0–3 | 125 (4.6 %) | 64 (2.4 %) | 1.95x |
| 4–7 | 64 (2.4 %) | 59 (2.2 %) | 1.08x |
| 8–15 | 140 (5.2 %) | 112 (4.1 %) | 1.25x |
| 16–31 | 199 (7.3 %) | 176 (6.5 %) | 1.13x |
| 32–63 | 220 (8.1 %) | 253 (9.3 %) | 0.87x |

total impulses above threshold: 2,708

## Segments

| kind | segments | ticks | % of ticks | mean ticks | p50 | mean dur ms | mean speed0 | mean dspeed |
|---|---|---|---|---|---|---|---|---|
| trim_ground | 9,095 | 214,933 | 35.92 % | 23.6 | 17 | 328 | 308 | -1 |
| trim_air | 4,716 | 115,930 | 19.38 % | 24.6 | 19 | 344 | 332 | -3 |
| maneuver_jump | 1,821 | 3,576 | 0.60 % | 2.0 | 2 | 28 | 390 | -0 |
| maneuver_rocket_jump | 383 | 1,253 | 0.21 % | 3.3 | 3 | 52 | 337 | -35 |
| maneuver_launch | 2,098 | 8,218 | 1.37 % | 3.9 | 4 | 56 | 348 | -67 |
| maneuver_fall | 4,121 | 8,219 | 1.37 % | 2.0 | 2 | 28 | 212 | -0 |
| maneuver_land | 4,296 | 7,888 | 1.32 % | 1.8 | 2 | 26 | 273 | +2 |
| other_ground | 11,184 | 185,076 | 30.93 % | 16.5 | 8 | 234 | 266 | +22 |
| other_air | 6,025 | 41,062 | 6.86 % | 6.8 | 4 | 97 | 247 | -10 |
| water | 2,946 | 12,151 | 2.03 % | 4.1 | 2 | 56 | 156 | -2 |
| **total** | **46,685** | **598,306** | **100.00 %** | | | | | |

### trim_air (4,716 segments, 115,930 ticks)

| quantity | p1 | p50 | p90 | p99 |
|---|---|---|---|---|
| entry speed (u/s) | 42 | 364 | 457 | 686 |
| speed gain over segment (u/s) | -137 | +0 | +18 | +58 |
| mean slip angle (deg) | -173.1 | +0.6 | +76.6 | +171.4 |
| |mean slip| (deg) | 0.1 | 10.2 | 116.4 | 176.3 |
| slip span within segment (deg) | 0.0 | 13.2 | 26.8 | 51.8 |
| mean turn rate (deg/s) | -258 | +0 | +119 | +281 |
| length (ticks) | 8 | 19 | 45 | 74 |
| planar distance (units) | 5 | 82 | 249 | 359 |

segments gaining > 20 u/s: 399 (8.5 %); max single-segment gain +115 u/s; fastest exit 1270 u/s (QW ground maxspeed is 320).

### trim_ground (9,095 segments, 214,933 ticks)

| quantity | p1 | p50 | p90 | p99 |
|---|---|---|---|---|
| entry speed (u/s) | 115 | 320 | 383 | 445 |
| speed gain over segment (u/s) | -237 | +4 | +84 | +154 |
| mean slip angle (deg) | -178.1 | -0.6 | +100.7 | +177.4 |
| |mean slip| (deg) | 0.1 | 41.5 | 144.6 | 179.2 |
| slip span within segment (deg) | 0.1 | 20.7 | 45.1 | 81.7 |
| mean turn rate (deg/s) | -359 | +0 | +96 | +332 |
| length (ticks) | 8 | 17 | 47 | 101 |
| planar distance (units) | 10 | 68 | 210 | 429 |

segments gaining > 20 u/s: 3,853 (42.4 %); max single-segment gain +265 u/s; fastest exit 572 u/s (QW ground maxspeed is 320).

### maneuver_rocket_jump — 383 segments, 2.74/min

peak impulse: p50 200, p90 635, max 2081 u/s

the 327 distinct air phases these belong to:

| quantity | p10 | p50 | p90 | max |
|---|---|---|---|---|
| air time (ms) | 67 | 654 | 1322 | 4113 |
| peak height above takeoff (units) | +0 | +40 | +129 | +347 |
| net height change (units) | -143 | -1 | +55 | +256 |
| peak speed (u/s) | 115 | 370 | 759 | 1315 |
| planar distance covered (units) | 7 | 146 | 387 | 787 |

### maneuver_jump (plain +270) — 1,821 segments, 13.03/min

peak impulse: p50 0, p90 37, max 118 u/s

the 1,821 distinct air phases these belong to:

| quantity | p10 | p50 | p90 | max |
|---|---|---|---|---|
| air time (ms) | 495 | 654 | 1129 | 7872 |
| peak height above takeoff (units) | +37 | +40 | +40 | +149 |
| net height change (units) | -74 | -2 | +23 | +149 |
| peak speed (u/s) | 320 | 426 | 490 | 1270 |
| planar distance covered (units) | 62 | 249 | 361 | 1388 |

## Integrity

| check | value |
|---|---|
| ticks labelled exactly once | 598,306 / 598,306 |
| contiguous chunks (breaks on gap/seq_break/bad msec) | 453 |
| ticks with no valid successor | 10 (0.00 %) |
| wire_state_present | 443,219 (74.08 %) |
| seq_break | 395 |
| non-finite in core features | {'speed_xy': 0, 'slip': 0, 'v_fwd': 0, 'v_right': 0, 'omega': 10, 'dx_loc': 10} |

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
  "fire_window_before": 12,
  "fire_window_after": 3,
  "rocket_impulse_min": 120.0,
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
