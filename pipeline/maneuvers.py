"""Pull full rocket-jump trajectories back out of step 1 for DMP fitting.

Step 1 deliberately dropped absolute x/y/yaw from the feature table -- they are
the pose the SE(2) transform exists to remove. For a DMP we need the *path*, so
this module rejoins the labelled ticks to store-dm3 on
(demo_key, slot, cmd_ordinal) and re-expresses each maneuver in the body frame
of its own takeoff. That frame choice is what makes two rocket jumps in
different corners of dm3 comparable.

A "jump" here is: the first tick of the maneuver_rocket_jump label through the
last tick of the air phase it belongs to, plus the landing tick.
"""

from __future__ import annotations

import numpy as np
import duckdb

from . import config as C
from . import se2

OUT = C.OUT_DIR


def _con(threads: int = 16):
    con = duckdb.connect()
    con.execute(f"SET threads TO {threads}")
    con.execute("SET preserve_insertion_order = false")
    return con


def jump_index(tag: str = "step1", kind: str = "maneuver_rocket_jump"):
    """One row per maneuver: the tick span of the maneuver and of its air phase."""
    con = _con()
    q = f"""
    WITH seg AS (
      SELECT batch, seg_id, demo_key, slot, i0, i1, o0, o1, split, n_ticks,
             peak_impulse, speed0, dur_ms
      FROM read_parquet('{OUT}/{tag}_segments/*.parquet')
      WHERE kind = '{kind}'
    ),
    run AS (
      SELECT batch, run_id, i0 AS r_i0, i1 AS r_i1, state, dur_ms AS air_ms,
             z0 AS r_z0, z_peak, z1 AS r_z1, speed_peak
      FROM read_parquet('{OUT}/{tag}_state_runs/*.parquet')
      WHERE state = 'air'
    )
    SELECT s.*, r.run_id, r.r_i0, r.r_i1, r.air_ms, r.z0 AS air_z0,
           r.z_peak, r.r_z1, r.speed_peak
    FROM seg s JOIN run r
      ON s.batch = r.batch AND s.i0 >= r.r_i0 AND s.i0 <= r.r_i1
    ORDER BY s.batch, s.i0
    """
    return con.execute(q).fetch_arrow_table()


def load_trajectories(tag: str = "step1", kind: str = "maneuver_rocket_jump",
                      pad_after: int = 1):
    """Return a list of per-jump dicts with world and body-frame paths.

    Each dict carries the ballistic arc from the blast to the landing tick, both
    in world coordinates (for sanity checks against the map) and in the SE(2)
    frame of the takeoff tick (what the DMP is actually fitted in).
    """
    idx = jump_index(tag, kind)
    con = _con()

    # tick spans we need out of the store, one row per jump
    spans = []
    for i in range(idx.num_rows):
        d = int(idx.column("demo_key")[i].as_py())
        s = int(idx.column("slot")[i].as_py())
        o0 = int(idx.column("o0")[i].as_py())
        # end of the enclosing air phase in cmd_ordinal terms: the segment table
        # stores tick indices, so translate via the tick table below
        spans.append((d, s, o0, int(idx.column("r_i1")[i].as_py()),
                      int(idx.column("i0")[i].as_py()), int(idx.column("batch")[i].as_py())))

    # translate air-phase end index -> cmd_ordinal via the tick table
    con.execute(f"""
        CREATE VIEW ticks AS SELECT * FROM read_parquet('{OUT}/{tag}_ticks/*.parquet')
    """)
    end_map = con.execute(f"""
        SELECT batch, row_number() OVER (PARTITION BY batch ORDER BY demo_key, slot, cmd_ordinal) - 1 AS idx,
               demo_key, slot, cmd_ordinal
        FROM ticks
    """)
    return idx, end_map


def jump_frames(tag: str = "step1", kind: str = "maneuver_rocket_jump",
                pad_after: int = 2):
    """Body-frame trajectory of every maneuver of `kind`, as a ragged list.

    Implemented as one duckdb pass: label ticks by the air run they belong to,
    keep only the runs that contain the maneuver, then rejoin world coordinates.
    """
    con = _con()
    con.execute(f"CREATE VIEW ticks AS SELECT * FROM read_parquet('{OUT}/{tag}_ticks/*.parquet')")
    con.execute(f"CREATE VIEW segs  AS SELECT * FROM read_parquet('{OUT}/{tag}_segments/*.parquet')")
    con.execute(
        f"CREATE VIEW rt AS SELECT * FROM read_parquet('{C.REPLAY_TICKS}', hive_partitioning=1)")
    con.execute(
        f"CREATE VIEW uc AS SELECT * FROM read_parquet('{C.USERCMDS}', hive_partitioning=1)")

    kind_id = {k: i for i, k in enumerate(_KINDS)}[kind]

    q = f"""
    WITH hit AS (              -- air runs that contain at least one maneuver tick
      SELECT DISTINCT batch, state_run_id
      FROM ticks WHERE kind = {kind_id}
    ),
    span AS (                  -- the whole air phase, in cmd_ordinal terms
      SELECT t.batch, t.state_run_id, t.demo_key, t.slot,
             min(t.cmd_ordinal) AS o0, max(t.cmd_ordinal) AS o1,
             any_value(t.split) AS split,
             min(CASE WHEN t.kind = {kind_id} THEN t.cmd_ordinal END) AS o_blast
      FROM ticks t JOIN hit h USING (batch, state_run_id)
      GROUP BY 1,2,3,4
    )
    SELECT s.batch, s.state_run_id AS jump_id, s.demo_key, s.slot, s.split,
           s.o0, s.o1, s.o_blast,
           r.cmd_ordinal, r.x, r.y, r.z, r.vx, r.vy, r.vz,
           u.yaw, u.pitch, u.msec, u.forwardmove, u.sidemove, u.buttons
    FROM span s
    JOIN rt r ON r.demo_key = s.demo_key AND r.slot = s.slot
             AND r.cmd_ordinal BETWEEN s.o_blast AND s.o1 + {pad_after}
    JOIN uc u ON u.demo_key = r.demo_key AND u.slot = r.slot
             AND u.cmd_ordinal = r.cmd_ordinal
    ORDER BY s.batch, s.state_run_id, r.cmd_ordinal
    """
    tbl = con.execute(q).fetch_arrow_table()
    return _split_jumps(tbl)


_KINDS = (
    "trim_ground", "trim_air", "maneuver_jump", "maneuver_rocket_jump",
    "maneuver_external", "maneuver_fall", "maneuver_land",
    "other_ground", "other_air", "water",
)


def _split_jumps(tbl):
    """Ragged split by (batch, jump_id) + body-frame re-expression."""
    cols = {n: np.asarray(tbl.column(n).combine_chunks().to_numpy(zero_copy_only=False))
            for n in tbl.column_names if n != "split"}
    split = np.asarray(tbl.column("split").to_pylist(), dtype=object)
    key = cols["batch"].astype(np.int64) * (1 << 32) + cols["jump_id"].astype(np.int64)
    new = np.empty(len(key), bool)
    new[0] = True
    new[1:] = key[1:] != key[:-1]
    starts = np.flatnonzero(new)
    ends = np.append(starts[1:], len(key))

    jumps = []
    for a, b in zip(starts, ends):
        if b - a < 4:                      # too short to fit anything
            continue
        yaw0 = np.deg2rad(float(cols["yaw"][a]) * C.U16_TO_DEG)
        cy, sy = np.cos(yaw0), np.sin(yaw0)
        x, y, z = cols["x"][a:b], cols["y"][a:b], cols["z"][a:b]
        vx, vy, vz = cols["vx"][a:b], cols["vy"][a:b], cols["vz"][a:b]
        dx, dy = x - x[0], y - y[0]
        jumps.append(dict(
            batch=int(cols["batch"][a]), jump_id=int(cols["jump_id"][a]),
            demo_key=int(cols["demo_key"][a]), slot=int(cols["slot"][a]),
            split=str(split[a]),
            o0=int(cols["cmd_ordinal"][a]), n=int(b - a),
            dt=np.clip(cols["msec"][a:b], 1, 50).astype(np.float64) / 1000.0,
            # world, for map-space checks only
            x=x, y=y, z=z,
            # body frame of the blast tick -- the DMP's coordinates
            px=dx * cy + dy * sy, py=dx * sy - dy * cy, pz=z - z[0],
            vf=vx * cy + vy * sy, vr=vx * sy - vy * cy, vz=vz,
            yaw0=yaw0,
            pitch0=se2.u16_to_signed_deg(np.array([cols["pitch"][a]]))[0],
            speed0=float(np.hypot(vx[0], vy[0])),
        ))
    return jumps
