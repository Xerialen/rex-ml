"""Read the (replay_ticks x usercmds) join out of store-dm3 as numpy arrays.

The join key is (demo_key, slot, cmd_ordinal). `split` only exists on the
usercmds side of the store, so it is carried across by the join.
"""

from __future__ import annotations

import numpy as np
import duckdb

from . import config as C

# Columns pulled from the store, in the order the transform expects them.
TICK_COLUMNS = """
    r.demo_key, r.slot, r.cmd_ordinal, r.t,
    r.x, r.y, r.z, r.vx, r.vy, r.vz,
    r.onground, r.jump_held, r.waterlevel, r.wire_state_present, r.seq_break, r.residual,
    u.msec, u.forwardmove, u.sidemove, u.upmove,
    coalesce(u.buttons, 0) AS buttons, coalesce(u.impulse, 0) AS impulse,
    u.pitch, u.yaw, u.split
"""


def connect(threads: int = 8) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET threads TO {threads}")
    con.execute("SET preserve_insertion_order = false")
    con.execute(
        f"CREATE VIEW rt AS SELECT * FROM read_parquet('{C.REPLAY_TICKS}', hive_partitioning=1)"
    )
    con.execute(
        f"CREATE VIEW uc AS SELECT * FROM read_parquet('{C.USERCMDS}', hive_partitioning=1)"
    )
    return con


def demo_keys(con, limit: int | None = None, split: str | None = None) -> list[int]:
    """Deterministic demo list: ordered by demo_key, optionally split-filtered."""
    where = f"WHERE split = '{split}'" if split else ""
    q = f"SELECT DISTINCT demo_key FROM uc {where} ORDER BY demo_key"
    if limit:
        q += f" LIMIT {limit}"
    return [r[0] for r in con.execute(q).fetchall()]


def load_ticks(con, keys: list[int] | None = None):
    """Return the joined table as a pyarrow Table, ordered by (demo_key, slot, cmd_ordinal)."""
    filt = ""
    if keys is not None:
        lst = ",".join(str(int(k)) for k in keys)
        filt = f"WHERE r.demo_key IN ({lst})"
    q = f"""
        SELECT {TICK_COLUMNS}
        FROM rt r JOIN uc u USING (demo_key, slot, cmd_ordinal)
        {filt}
        ORDER BY r.demo_key, r.slot, r.cmd_ordinal
    """
    res = con.execute(q)
    tbl = res.fetch_arrow_table()
    if not hasattr(tbl, "column_names"):      # duckdb >= 1.3 may hand back a reader
        tbl = tbl.read_all()
    return tbl


def to_arrays(tbl) -> dict[str, np.ndarray]:
    """pyarrow Table -> dict of contiguous numpy arrays with explicit dtypes.

    Nullable columns (pitch, yaw, residual) are materialised with a null mask so
    the transform can decide what to do rather than silently seeing a zero.
    """
    out: dict[str, np.ndarray] = {}
    for name in tbl.column_names:
        col = tbl.column(name).combine_chunks()
        if name in ("pitch", "yaw", "residual"):
            out[name + "_null"] = np.asarray(col.is_null())
            arr = col.fill_null(0).to_numpy(zero_copy_only=False)
        elif name == "split":
            out[name] = np.asarray(col.to_pylist(), dtype=object)
            continue
        else:
            arr = col.to_numpy(zero_copy_only=False)
        out[name] = np.ascontiguousarray(arr)
    return out


def track_bounds(demo_key: np.ndarray, slot: np.ndarray) -> np.ndarray:
    """Start indices of each (demo_key, slot) track plus a trailing sentinel.

    Requires the input to be sorted by (demo_key, slot, cmd_ordinal).
    """
    n = len(demo_key)
    if n == 0:
        return np.array([0], dtype=np.int64)
    new = np.empty(n, dtype=bool)
    new[0] = True
    new[1:] = (demo_key[1:] != demo_key[:-1]) | (slot[1:] != slot[:-1])
    starts = np.flatnonzero(new).astype(np.int64)
    return np.append(starts, n)
