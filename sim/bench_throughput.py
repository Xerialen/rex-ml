#!/usr/bin/env python
"""Throughput benchmark for libqwsim on dm3.

- step_batch: slot-steps/s at 1 and 64 threads, batch 256/1024/4096,
  realistic pseudo-inputs (running, strafing, jumping, yaw drift), slots
  seeded at recorded human positions from the corpus so they interact with
  real geometry (floors, walls, stairs), reseeded periodically.
- trace_rays: rays/s at 1 and 64 threads, 128 rays per slot in a batch of
  4096 origins (typical perception workload).

Output: evidence/libqwsim_throughput.json
"""
import json
import sys
import time
from pathlib import Path

import duckdb
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import qwsim  # noqa: E402

DM3_BSP = "/home/benjamin-adm/mlx/qwserver/serverdir/id1/maps/dm3.bsp"
RT = "/home/benjamin-adm/dm3-extract/store-dm3/replay_ticks/**/*.parquet"
EVIDENCE = Path("/home/benjamin-adm/rex-ml/evidence/libqwsim_throughput.json")

rng = np.random.default_rng(7)


def human_positions(n):
    con = duckdb.connect()
    rows = con.execute(f"""
        select x, y, z from read_parquet('{RT}')
        where wire_state_present and waterlevel = 0
        using sample reservoir({n} rows) repeatable (42)
    """).fetchall()
    p = np.array(rows, np.float32)
    p[:, 2] += 1.0
    return p


def make_inputs(n, t_steps):
    """Pre-generate realistic cmd streams: mostly full forward, strafing
    bursts, jump every ~0.5-1 s, yaw random-walk."""
    yaw = rng.uniform(-180, 180, n).astype(np.float32)
    yaw_rate = rng.normal(0, 40, (t_steps, n)).astype(np.float32)  # deg/s
    fm = np.full((t_steps, n), 400, np.int16)
    sm = np.where(rng.random((t_steps, n)) < 0.4,
                  rng.choice(np.array([-700, 700], np.int16), (t_steps, n)),
                  0).astype(np.int16)
    jump = (rng.random((t_steps, n)) < 0.05)
    bt = np.where(jump, 2, 0).astype(np.uint8)
    return yaw, yaw_rate, fm, sm, bt


def bench_step(batch, threads, seconds=3.0):
    qwsim.set_num_threads(threads)
    qwsim.alloc_slots(batch)
    ids = np.arange(batch, dtype=np.int32)
    pos = SPAWNS[rng.integers(0, len(SPAWNS), batch)]
    vel = np.zeros((batch, 3), np.float32)
    qwsim.reset(ids, pos, vel)

    T = 256
    yaw, yaw_rate, fm, sm, bt = make_inputs(batch, T)
    um = np.zeros(batch, np.int16)
    ms = np.full(batch, 13, np.uint8)
    ang = np.zeros((batch, 3), np.float32)

    # warmup
    for t in range(8):
        yaw += yaw_rate[t] * 0.013
        ang[:, 1] = yaw
        qwsim.step_batch(ids, ang, fm[t], sm[t], um, bt[t], ms)

    steps = 0
    t0 = time.perf_counter()
    t = 0
    while True:
        yaw += yaw_rate[t % T] * 0.013
        ang[:, 1] = yaw
        qwsim.step_batch(ids, ang, fm[t % T], sm[t % T], um, bt[t % T], ms)
        steps += batch
        t += 1
        if t % 512 == 0:
            # periodic reseed so slots keep hitting varied geometry
            pos = SPAWNS[rng.integers(0, len(SPAWNS), batch)]
            qwsim.reset(ids, pos, vel)
            if time.perf_counter() - t0 > seconds:
                break
        elif t % 64 == 0 and time.perf_counter() - t0 > seconds:
            break
    dt = time.perf_counter() - t0
    return dict(batch=batch, threads=threads, slot_steps_per_s=steps / dt,
                ticks=t, wall_s=dt)


def bench_rays(threads, n_origins=4096, rays_per_origin=128, seconds=3.0):
    qwsim.set_num_threads(threads)
    m = n_origins * rays_per_origin
    orig = np.repeat(SPAWNS[rng.integers(0, len(SPAWNS), n_origins)],
                     rays_per_origin, axis=0)
    d = rng.normal(size=(m, 3)).astype(np.float32)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    # warmup
    qwsim.trace_rays(orig[:4096], d[:4096], 4096.0)
    total = 0
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        fr, nrm, ss = qwsim.trace_rays(orig, d, 4096.0)
        total += m
    dt = time.perf_counter() - t0
    return dict(threads=threads, origins=n_origins,
                rays_per_origin=rays_per_origin, rays_per_s=total / dt,
                mean_fraction=float(fr.mean()), wall_s=dt)


def main():
    qwsim.load_bsp(DM3_BSP)
    global SPAWNS
    SPAWNS = human_positions(8192)
    print(f"{len(SPAWNS)} human seed positions loaded", flush=True)

    step_results = []
    for threads in (1, 64):
        for batch in (256, 1024, 4096):
            r = bench_step(batch, threads)
            step_results.append(r)
            print(f"step_batch batch={batch:5d} threads={threads:2d}: "
                  f"{r['slot_steps_per_s']/1e6:8.2f} M slot-steps/s", flush=True)

    ray_results = []
    for threads in (1, 64):
        r = bench_rays(threads)
        ray_results.append(r)
        print(f"trace_rays threads={threads:2d}: {r['rays_per_s']/1e6:8.2f} M rays/s "
              f"(mean fraction {r['mean_fraction']:.3f})", flush=True)

    rt = 77.0
    best = max(r["slot_steps_per_s"] for r in step_results)
    out = dict(
        generated="2026-07-30",
        bsp=DM3_BSP,
        machine="vmonster: 64 cores, dt=13ms inputs, seeds from corpus positions",
        note="slot-steps/s = full PM_PlayerMove server ticks incl. nudge/"
             "categorize/trace; rays = CM_HullTrace on hull 0, max_dist 4096",
        step_batch=step_results,
        trace_rays=ray_results,
        realtime_factor_at_77hz=best / rt,
    )
    EVIDENCE.parent.mkdir(exist_ok=True)
    EVIDENCE.write_text(json.dumps(out, indent=1))
    print("wrote", EVIDENCE)
    print(f"best: {best/1e6:.2f} M slot-steps/s = {best/rt/1000:.0f}k parallel "
          f"players at 77 Hz realtime")


if __name__ == "__main__":
    main()
