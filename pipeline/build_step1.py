"""Build the BRIEF step 1 feature + segment tables over store-dm3.

Writes two parquet datasets under pipeline/out/:

  step1_ticks/     one row per tick: SE(2)-invariant state, action, transition,
                   plus the derived ground state and the segment label
  step1_segments/  one row per trim/maneuver segment
  step1_state_runs/ one row per contiguous ground/air/water run

Demos are processed in batches so peak memory stays bounded and a crash costs
one batch, not the run.

Usage:
  .venv/bin/python -m pipeline.build_step1 --batch 40
  .venv/bin/python -m pipeline.build_step1 --demos 25 --tag smoke
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from . import config as C
from . import io_store, se2, segment

# The tick table written to disk. Absolute x/y/yaw are deliberately excluded:
# they are the pose the transform exists to remove. demo_key/slot/cmd_ordinal
# are enough to get back to the store if raw world coordinates are ever needed.
TICK_OUT = [
    ("demo_key", pa.uint32()), ("slot", pa.uint8()), ("cmd_ordinal", pa.int32()),
    ("t", pa.int32()), ("msec", pa.uint8()),
    # invariant state
    ("z", pa.float32()), ("v_fwd", pa.float32()), ("v_right", pa.float32()),
    ("vz", pa.float32()), ("speed_xy", pa.float32()), ("slip", pa.float32()),
    ("omega_prev", pa.float32()), ("pitch_deg", pa.float32()),
    ("wish_f", pa.float32()), ("wish_r", pa.float32()), ("wish_mag", pa.float32()),
    ("wish_slip", pa.float32()),
    # invariant action
    ("forwardmove", pa.int16()), ("sidemove", pa.int16()), ("upmove", pa.int16()),
    ("dyaw", pa.float32()), ("dpitch", pa.float32()), ("omega", pa.float32()),
    ("attack", pa.bool_()), ("jump_btn", pa.bool_()),
    # invariant transition to the next tick
    ("dx_loc", pa.float32()), ("dy_loc", pa.float32()), ("dz", pa.float32()),
    ("dv_fwd", pa.float32()), ("dv_right", pa.float32()), ("dvz", pa.float32()),
    ("dspeed_xy", pa.float32()), ("grav_res", pa.float32()),
    # labels and masks
    ("ground_state", pa.uint8()), ("kind", pa.uint8()), ("seg_id", pa.int32()),
    ("state_run_id", pa.int32()),
    ("is_takeoff", pa.bool_()), ("is_land", pa.bool_()),
    ("is_fire_edge", pa.bool_()), ("is_impulse", pa.bool_()),
    ("has_next", pa.bool_()), ("wire_state_present", pa.bool_()),
    ("waterlevel", pa.uint8()), ("seq_break", pa.bool_()),
]


def _tick_table(f, r, batch_id):
    src = dict(f)
    src.update(
        ground_state=r["state"].astype(np.uint8),
        kind=r["kind"].astype(np.uint8),
        seg_id=r["seg_id"],
        state_run_id=r["state_run_id"],
        is_takeoff=r["events"]["takeoff"], is_land=r["events"]["land"],
        is_fire_edge=r["events"]["fire_edge"], is_impulse=r["events"]["impulse"],
    )
    cols, names = [], []
    for name, typ in TICK_OUT:
        v = src[name]
        if pa.types.is_floating(typ):
            v = np.asarray(v, dtype=np.float32)
        elif pa.types.is_boolean(typ):
            v = np.asarray(v, dtype=bool)
        else:
            v = np.asarray(v)
        cols.append(pa.array(v, type=typ, from_pandas=False))
        names.append(name)
    if "split" in f:
        cols.append(pa.array(f["split"]))
        names.append("split")
    cols.append(pa.array(np.full(len(f["cmd_ordinal"]), batch_id, np.int32)))
    names.append("batch")
    return pa.table(cols, names=names)


def _dict_table(d, extra=None):
    cols, names = [], []
    for k, v in d.items():
        v = np.asarray(v)
        if v.dtype == object:
            cols.append(pa.array([str(x) for x in v]))
        elif v.dtype == np.float64:
            cols.append(pa.array(v.astype(np.float32)))
        else:
            cols.append(pa.array(v))
        names.append(k)
    for k, v in (extra or {}).items():
        cols.append(pa.array(v))
        names.append(k)
    return pa.table(cols, names=names)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=40, help="demos per batch")
    ap.add_argument("--demos", type=int, default=None, help="cap total demos")
    ap.add_argument("--tag", default="step1")
    ap.add_argument("--out", default=str(C.OUT_DIR))
    args = ap.parse_args(argv)

    out = Path(args.out)
    tick_dir = out / f"{args.tag}_ticks"
    seg_dir = out / f"{args.tag}_segments"
    run_dir = out / f"{args.tag}_state_runs"
    for d in (tick_dir, seg_dir, run_dir):
        d.mkdir(parents=True, exist_ok=True)

    con = io_store.connect(threads=16)
    keys = io_store.demo_keys(con, limit=args.demos)
    batches = [keys[i:i + args.batch] for i in range(0, len(keys), args.batch)]
    print(f"{len(keys)} demos in {len(batches)} batches of <= {args.batch}", flush=True)

    tot = dict(rows=0, segs=0, runs=0, secs=0.0, bytes=0)
    kind_hist = np.zeros(len(segment.KINDS), dtype=np.int64)
    seg_hist = np.zeros(len(segment.KINDS), dtype=np.int64)
    t_start = time.time()
    seg_base = 0
    run_base = 0

    for bi, bkeys in enumerate(batches):
        t0 = time.time()
        a = io_store.to_arrays(io_store.load_ticks(con, bkeys))
        f = se2.transform(a)
        r = segment.segment(f)
        n = len(f["cmd_ordinal"])

        # make segment ids globally unique across batches
        r["seg_id"] = r["seg_id"].astype(np.int64) + seg_base
        r["state_run_id"] = r["state_run_id"].astype(np.int64) + run_base
        segs = dict(r["segments"])
        segs["seg_id"] = segs["seg_id"].astype(np.int64) + seg_base
        runs = dict(r["state_runs"])
        runs["run_id"] = runs["run_id"].astype(np.int64) + run_base
        seg_base += len(segs["seg_id"])
        run_base += len(runs["run_id"])

        # tick table wants int32 ids; fall back to int64 if we ever overflow
        r["seg_id"] = r["seg_id"].astype(np.int32)
        r["state_run_id"] = r["state_run_id"].astype(np.int32)

        tt = _tick_table(f, r, bi)
        p1 = tick_dir / f"part-{bi:05d}.parquet"
        pq.write_table(tt, p1, compression="zstd", compression_level=3)

        st = _dict_table(segs, {"batch": np.full(len(segs["seg_id"]), bi, np.int32)})
        p2 = seg_dir / f"part-{bi:05d}.parquet"
        pq.write_table(st, p2, compression="zstd", compression_level=3)

        rt = _dict_table(runs, {"batch": np.full(len(runs["run_id"]), bi, np.int32),
                                "demo_key": f["demo_key"][runs["i0"]],
                                "slot": f["slot"][runs["i0"]]})
        p3 = run_dir / f"part-{bi:05d}.parquet"
        pq.write_table(rt, p3, compression="zstd", compression_level=3)

        for i in range(len(segment.KINDS)):
            kind_hist[i] += int((r["kind"] == i).sum())
        for i, k in enumerate(segment.KINDS):
            seg_hist[i] += int((segs["kind"] == k).sum())

        nb = sum(p.stat().st_size for p in (p1, p2, p3))
        tot["rows"] += n
        tot["segs"] += len(segs["seg_id"])
        tot["runs"] += len(runs["run_id"])
        tot["bytes"] += nb
        dt = time.time() - t0
        tot["secs"] += dt
        eta = (time.time() - t_start) / (bi + 1) * (len(batches) - bi - 1)
        print(f"[{bi+1}/{len(batches)}] demos {bkeys[0]}..{bkeys[-1]}  "
              f"{n:,} rows  {len(segs['seg_id']):,} segs  {nb/1e6:.1f} MB  "
              f"{dt:.1f}s   total {tot['rows']:,} rows / {tot['bytes']/1e9:.2f} GB   "
              f"eta {eta/60:.1f} min", flush=True)

    summary = dict(
        tag=args.tag, demos=len(keys), batches=len(batches),
        rows=tot["rows"], segments=tot["segs"], state_runs=tot["runs"],
        bytes_on_disk=tot["bytes"], wall_seconds=round(time.time() - t_start, 1),
        ticks_by_kind={k: int(kind_hist[i]) for i, k in enumerate(segment.KINDS)},
        segments_by_kind={k: int(seg_hist[i]) for i, k in enumerate(segment.KINDS)},
        thresholds=C.thresholds_dict(),
    )
    (out / f"{args.tag}_summary.json").write_text(json.dumps(summary, indent=2))
    print("\n" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
