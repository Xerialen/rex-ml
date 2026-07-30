# AUDIT — demo-derived data already on vmonster (2026-07-27)

Purpose: decide whether BRIEF step 1 can be built on existing artifacts instead of
re-parsing 161 GB of `.mvd`. All numbers below are measured (duckdb v1.5.4 over the
parquet stores, `zstd -dc` over the CSV/JSON bundles), not estimated.

## Summary table

| Artifact | Size | Format | Per-tick usercmds (buttons + mouse) | Player state (pos/vel/angles/health/ground) | Tickrate | DM3-filtered | Verdict |
|---|---|---|---|---|---|---|---|
| `~/dm3-extract/store-dm3` | 27 GB | Parquet, hive-partitioned (`format=/map=/mode=/split=`) | **YES** — `usercmds`: `forwardmove, sidemove, upmove, buttons, impulse, pitch, yaw, msec, cmd_time, cmd_ordinal` | **YES** — `replay_ticks`: `x,y,z, vx,vy,vz, onground, jump_held, waterlevel, seq_break, residual`; health via `trajectory_samples.h` | 13–14 ms/tick (mode 14 ms, 63 % of deltas) ≈ 72–77 Hz | **YES** (`map=dm3` only, 3 777 demo ids) | **REUSE — primary source** |
| `~/qw-corpus-build/task10-42926d4/staging` | 221 GB | NDJSON.zst (staging, **not** written to parquet — `parquet_write` stage was SIGTERMed 2026-07-18) | YES — same schema, all maps | YES — same schema, all maps | same | **NO** (all maps) | **Reserve** — superset, use if we outgrow DM3 |
| `~/qwd-miner-movement-bundle` | 30 GB | `raw/`: 7 945 per-demo CSV.zst; `v2-raw/`: 8 240 JSON.zst | Partial — `dem_cmd` rows have `msec, forwardmove, sidemove, upmove, buttons, pitch, yaw` | **NO** — `playerinfo` rows have `x,y,z, vx,vy,vz` but **no `onground`, no health, no `jump_held`** | ~13 ms | **NO** (all maps; `map` = BSP title, e.g. "The Bad Place") | Reject — missing ground_contact |
| `~/qwd-corpus` | 56 GB | 8 240 raw `.qwd` (client POV demos) + `qwd_dump.py` | Source only — requires parsing | Source only | n/a | NO (~1 411 dm3 by filename) | Reject — this is the input the above was built from |
| `~/mvd-corpus` | 161 GB | 50 952 raw `.mvd` (server multi-view) + `manifest.tsv`, `demo-index.tsv` | **Structurally impossible** — MVD is a server-side entity stream; it carries no client usercmds | Positions/velocities only, via entity deltas | n/a | NO (2 182 dm3 of 50 953) | Reject — cannot yield usercmds at any parse cost |

## The one join that matters

`store-dm3/replay_ticks` ⋈ `store-dm3/usercmds` on `(demo_key, slot, cmd_ordinal)`:

```
joined_rows   27,934,383      (98.28 % of 28,423,944 replay_ticks)
demos                 481
wall-clock hours   109.64      (sum of usercmd msec)
onground=true   5,822,699      20.8 %
buttons&1 (attack)  2,651,311   9.5 %
buttons&2 (jump)    1,849,357   6.6 %
wire_state_present 20,588,049  73.7 %  (rest is replay-integrated, residual avg 1.03 units)
seq_break              17,232   0.06 %
```

This gives **109.6 hours of DM3 movement at ~77 Hz with both the control signal and the
resulting state on the same row** — exactly the CSKnow-style symbolic tuple BRIEF step 1 asks for.

## Findings behind the verdicts

**Provenance is clean.** `dm3-extract/driver.sh` filters `task10-42926d4/staging` by
`dm3_ids.txt` (3 777 ids, matched on the `demo_id` field), then `driver_v2.sh` runs the
upstream `write_parquet.py` writer. So `store-dm3` is not an independent re-derivation —
it is the same parser output, narrowed to DM3 and materialised as parquet. The full-corpus
staging still holds 116 807 832 replay_ticks (all maps) if we ever need to widen.

**Only POV demos carry usercmds.** `replay_ticks` and `usercmds` cover 487 demos at
**exactly one slot per demo** (487 demos / 487 tracks) — the recorder. `trajectory_samples`
covers 2 785 demos / 20 936 tracks because it is reconstructed from server entity updates
for every player. This is the fundamental split: control signals exist only for the person
holding the mouse. 161 GB of `.mvd` cannot change that; re-parsing it would add opponent
*trajectories*, never opponent *usercmds*.

**Health is joinable, not native.** `replay_ticks` has no health column. `trajectory_samples`
has `h` (99.7 % non-null on the sampled track) at a finer sample cadence. All **487 of 487**
replay_ticks tracks have a matching `(demo_key, slot)` in `trajectory_samples`, so health
can be as-of-joined on `t`. Angles are available twice: `usercmds.pitch/yaw` (commanded,
uint16 = angle·65536/360) and `trajectory_samples.vp/vya` (observed).

**Buttons are a clean two-bit field.** Measured over all 29 899 266 usercmds rows the only
values present are `0` (25 172 865), `1` (2 746 375), `2` (1 881 339), `3` (98 687). So
`buttons&1` = attack and `buttons&2` = jump, with nothing else to disambiguate. Weapon-fire
segmentation is a one-bit test.

**The movement bundle is the wrong shape.** Its CSV is an event stream
(`event ∈ {movevars, playerinfo, dem_cmd, event}`) where control and state live on
*separate rows* and must be re-associated by time. More decisively, it has no `onground`
column at all — the segmentation BRIEF step 1 specifies is not computable from it without
re-running physics. Its strict-v2 JSON accepts only 4 868 of 8 240 demos (59.1 %), mostly
rejected for `dem_cmd_without_sequence` (2 593).

## Recommendation

**Reuse `~/dm3-extract/store-dm3`. Do not parse fresh. Do not touch `~/mvd-corpus`.**

Reasons, in order of weight:

1. **Re-parsing cannot beat it.** The 161 GB `.mvd` corpus has no usercmds by protocol
   design. The 56 GB `.qwd` corpus does, but `store-dm3` *is already its parsed output* —
   re-parsing would reproduce the same 27.9 M rows at a cost of days of CPU and tens of GB.
2. **It is already DM3-filtered and parquet.** Predicate-pushdown reads, hive partitions,
   train/val/test split column present. Zero preprocessing before the SE(2) transform.
3. **It has every field step 1 needs**: position, velocity, view angles, ground_contact
   (`onground`), weapon-fire (`buttons&1`), and health via a verified 487/487 join.
4. **Disk cost of reuse is ~0.** Reading is free; the step-1 output is a derived feature
   table, not a copy of the corpus.

Escalation path if 109.6 h proves too thin for TD3+BC: the all-maps staging at
`task10-42926d4/staging` holds 4.1× more replay_ticks (116.8 M) in the identical schema.
Widening is a `write_parquet.py` run over existing NDJSON — still no `.mvd` re-parse.

### Caveats to carry into step 2

- 26.3 % of ticks are replay-integrated rather than wire-confirmed (`wire_state_present=false`).
  Residual on the confirmed ones averages 1.03 units, so integration is sound, but a
  `wire_state_present` filter should be available as an ablation.
- One slot per demo means no opponent state on the same row. Adversarial context, if needed,
  must come from `trajectory_samples` by an as-of join — a step-3 concern, not step 1.
- 1.72 % of replay_ticks have no matching usercmd (489 561 rows) and must be dropped or
  masked, not interpolated.
