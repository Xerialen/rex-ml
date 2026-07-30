"""SPEC K0.2 -- a learned enemy-motion predictor that beats constant velocity.

This is the kill criterion for the ML-combat track (specs/K0.2-enemy-prediction.md).
rtx aims by assuming the enemy holds its current velocity (`bot/combat/aim.rs`).
`evidence/k0_baseline.json` measured how wrong that is; this module trains a model
to correct it and reports the raw error distribution against still/linear. REVIEW
ROUND 1 put the original 16u/28.7u threshold under review (it was derived from the
direct-hit `fire_tolerance`; the dominant relevant weapon, the rocket, is a splash
weapon with its own, different `fire_tolerance`) -- so this module reports median,
p90, and the fraction of rows under 16u/40u/160u and does not compute a pass/fail
verdict at all.

Data. `trajectory_samples` carries no velocity (`vx/vy/vz` null, `velocity_present`
false) for the mvd-format rows that are 93 % of `split=train` -- velocity has to be
finite-differenced from positions, exactly as `k0_baseline.py` does. Windowing is
reused unchanged so the numbers are comparable: velocity differenced over an
8-40 ms gap, the future sample must land within +/-25 ms of `t+H`.

Correction to the spec, superseded once already -- recorded precisely this time.
The spec states "`velocity_present` is false everywhere". Measured on the full
`split=train` table:

    format  rows          velocity_present   vx null
    mvd     752,249,168   0.0 %              100 %
    qwd      55,031,703   43.3 %              56.7 %

So the spec is RIGHT about `mvd` (93 % of the table: `velocity_present` is false
and `vx/vy/vz` null for every row) and WRONG about `qwd`, where ~23.8 M of its
55.0 M rows (the recording-POV rows) carry a real `velocity_present = true` with
genuine `vx/vy/vz`. (An earlier revision of this note inverted the `mvd` half of
that statement -- backwards from both the spec and the data. This is the corrected
version.) Methodology is unaffected: this module finite-differences positions
uniformly regardless of the native velocity columns, so windowing -- and the
numbers -- stay identical to the baseline's methodology across the whole table.

Frame. Positions are never fed in world coordinates -- that lets a model memorise
dm3 geometry instead of learning motion. Per `pipeline/README.md`'s SE(2) transform
(also used by `pipeline/policy.py`), the body frame is Quake's own horizontal view
basis with pitch zeroed:

    e_f = (cos yaw, sin yaw)     e_r = (sin yaw, -cos yaw)

Here "yaw" is the *tracked player's own view yaw* (`vya`), not a heading fit to
its velocity -- using view yaw keeps the frame well defined even when the target
is nearly stationary (velocity direction is degenerate at v=0), and it is also
what makes the view-angle features falsifiable: if a bot's own view yaw carried no
information about where its velocity is about to point, rotating into that frame
would buy nothing over rotating into the velocity's own heading. Everything world
frame -- the two velocity windows, the offset target -- is rotated into it. Because
this rotation is an isometry, squared error in frame space is *exactly* squared
Euclidean error in world space; no inverse rotation is needed to score a
prediction, only to deploy one.

Features (14, see FEATURE_COLS): the current finite-differenced velocity and the
one before it, both in the view-yaw frame (this is "a short history of positions"
reduced to its two independent degrees of freedom, and "the differenced velocity
and its recent change" in the same features); the view pitch as sin/cos; the
*rate of change* of view yaw (raw view yaw would be exactly zero by construction,
since it defines the frame -- its derivative is the non-trivial residual signal:
"does this player's view keep turning" is informative in a way "which way is it
pointing right now" is not, once the frame already encodes the latter); the two
irregular sample gaps; and the elapsed time to the query horizon, so one model
serves both 300 ms and 600 ms instead of two.

Target: the offset from the linear (constant-velocity) extrapolation, in the same
frame -- per spec, so a failed run degrades to the baseline rather than to noise.

Subcommands:
    build      materialise train/val (full demo diversity, row_cap-limited) and
               test (full, uncapped) to .npy via duckdb -- see SPLIT_CFG
    train      MLP, Huber loss on the frame-space offset, on the H100
    eval       val (or test, if already built) error for still/linear/learned,
               at both horizons, as median/p90/fraction-under-threshold
    eval_test  the ONE touch of split=test -- do not call until instructed
"""

from __future__ import annotations

import argparse
import glob
import json
import time
from pathlib import Path

import numpy as np

OUT = Path("/home/benjamin-adm/rex-ml/pipeline/out/predict_enemy")
EVIDENCE = Path("/home/benjamin-adm/rex-ml/evidence/k0_2_predictor.json")
STORE = Path("/home/benjamin-adm/dm3-extract/store-dm3")

# ---- windowing, reused unchanged from k0_baseline.py so numbers are comparable ----
HORIZONS_MS = (300, 600)
DT_MIN, DT_MAX = 8, 40     # ms gap a velocity is differenced over
TOL_MS = 25                # the future sample must land within this of t+H

# ---- feature/target layout -------------------------------------------------------
FEATURE_COLS = [
    "v0_f", "v0_r", "v0_z",       # current finite-differenced velocity, view-yaw frame
    "v1_f", "v1_r", "v1_z",       # velocity one window back, same frame
    "have_v1",                     # 0 if the previous sample wasn't usable (edge of track)
    "speed0",                      # |v0| in the xy plane
    "dyaw_view",                   # rate of change of view yaw over the dt0 window (rad)
    "sin_vp", "cos_vp",            # view pitch
    "dt0_ms", "dt1_ms",             # the two (irregular) sample gaps
    "elapsed_ms",                   # actual t -> future-sample gap (~H +/- tol)
]
FEATURE_SCALE = np.array(
    [400., 400., 400., 400., 400., 400., 1., 400., 1., 1., 1., 40., 40., 600.],
    dtype=np.float32,
)
TARGET_COLS = ["off_f", "off_r", "off_z"]   # offset from linear extrapolation, same frame

TWO_PI_OVER_65536 = 2.0 * np.pi / 65536.0

# REVIEW ROUND 1: no demo-level subsampling for train/val any more. Round 1 used
# demo_cap=300/80 (0.8 % of the 807 M available train rows) specifically to keep
# builds fast; the reviewer's point is that a plateau measured on a narrow demo
# slice doesn't establish a ceiling for the problem -- demo *diversity* covers map
# geometry and player styles, which a bigger row_cap on the same 300 demos would
# not. Measured while fixing this: the feat + ASOF-join stage over the FULL
# 807 M-row train split (all 2,449 demos, no demo filter) takes ~35 s combined for
# both horizons -- there was no performance reason to have restricted it in the
# first place; the actual cost (measured, see _stage_paired's docstring) was a
# reservoir-sample bug, now fixed. row_cap still exists to bound the cached
# tensors' disk footprint -- see build()'s docstring for the measured sizes this
# produces. test stays full/uncapped and is never subsampled, as before.
SPLIT_CFG = {
    "train": dict(demo_cap=None, row_cap=50_000_000),
    "val":   dict(demo_cap=None, row_cap=10_000_000),
    "test":  dict(demo_cap=None, row_cap=None),
}


# ==================================================================================
# SQL (duckdb). Built as staged CREATE TEMP TABLEs, not one nested CTE: a single
# query that self-joins a CTE defined via its own nested WITH measured *two full
# minutes and counting* (killed) on 20 demos where the identical logic staged as
# three materialised temp tables took 0.9 s combined. Whatever duckdb's planner is
# doing with the inlined self-reference, don't do that.
# ==================================================================================

def _files(split: str) -> list[str]:
    files = sorted(glob.glob(f"{STORE}/trajectory_samples/split={split}/**/*.parquet", recursive=True))
    if not files:
        raise SystemExit(f"no parquet files for split={split}")
    return files


def _stage_demo_sample(con, files, demo_cap, seed=0):
    if demo_cap is None:
        con.execute("CREATE OR REPLACE TEMP TABLE sampled_demos AS SELECT demo_key FROM read_parquet($files) WHERE false", {"files": files})
        return False
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE sampled_demos AS
        SELECT demo_key FROM (SELECT DISTINCT demo_key FROM read_parquet($files))
        ORDER BY hash(demo_key || $seed) LIMIT $k
        """,
        {"files": files, "k": demo_cap, "seed": str(seed)},
    )
    return True


def _stage_feat(con, files, use_demo_filter: bool):
    demo_clause = "AND demo_key IN (SELECT demo_key FROM sampled_demos)" if use_demo_filter else ""
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE feat AS
        WITH pos AS (
          SELECT demo_key, slot, t, x, y, z, vp, vya,
                 lag(t) OVER w AS t1, lag(x) OVER w AS x1, lag(y) OVER w AS y1, lag(z) OVER w AS z1,
                 lag(vya) OVER w AS vya1,
                 lag(t,2) OVER w AS t2, lag(x,2) OVER w AS x2, lag(y,2) OVER w AS y2, lag(z,2) OVER w AS z2
          FROM read_parquet($files)
          WHERE x IS NOT NULL AND vp IS NOT NULL AND vya IS NOT NULL
            {demo_clause}
          WINDOW w AS (PARTITION BY demo_key, slot ORDER BY t)
        )
        SELECT demo_key, slot, t, x, y, z,
               CAST(vp AS INTEGER) AS vp, CAST(vya AS INTEGER) AS vya, CAST(vya1 AS DOUBLE) AS vya1,
               CAST(t - t1 AS DOUBLE) AS dt0,
               (x - x1)/(t - t1)*1000.0 AS vx0,
               (y - y1)/(t - t1)*1000.0 AS vy0,
               (z - z1)/(t - t1)*1000.0 AS vz0,
               CASE WHEN t2 IS NOT NULL AND (t1 - t2) BETWEEN $dt_min AND $dt_max
                    THEN CAST(t1 - t2 AS DOUBLE) END AS dt1,
               CASE WHEN t2 IS NOT NULL AND (t1 - t2) BETWEEN $dt_min AND $dt_max
                    THEN (x1 - x2)/(t1 - t2)*1000.0 END AS vx1,
               CASE WHEN t2 IS NOT NULL AND (t1 - t2) BETWEEN $dt_min AND $dt_max
                    THEN (y1 - y2)/(t1 - t2)*1000.0 END AS vy1,
               CASE WHEN t2 IS NOT NULL AND (t1 - t2) BETWEEN $dt_min AND $dt_max
                    THEN (z1 - z2)/(t1 - t2)*1000.0 END AS vz1
        FROM pos
        WHERE t1 IS NOT NULL AND (t - t1) BETWEEN $dt_min AND $dt_max
        """,
        {"files": files, "dt_min": DT_MIN, "dt_max": DT_MAX},
    )


def _stage_paired(con, h: int, row_cap: int | None, seed: int):
    """Materialise the ASOF-joined, tol-filtered pairs for horizon h, then (if
    row_cap) subsample down to it.

    Measured bug, found while scaling this up for REVIEW ROUND 1: fusing
    `USING SAMPLE n ROWS (reservoir, seed)` into the SAME statement as the ASOF
    join is pathological -- at 700 demos (181 M candidate rows) the join alone
    (materialised, no sampling) took 6.3 s; adding the reservoir-sample clause to
    that same query didn't finish in 120 s, and didn't finish as a *separate*
    query against the already-materialised table either. A plain
    `WHERE random() < frac` filter on the materialised table, in contrast, took
    0.1 s over the same 179 M rows. Whatever duckdb's planner does with reservoir
    sampling here, don't fuse it with a large join -- and prefer independent
    per-row sampling (which parallelises trivially) over reservoir sampling
    (which is inherently sequential) regardless.
    """
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE paired_full_{h} AS
        SELECT f.vx0, f.vy0, f.vz0, f.vx1, f.vy1, f.vz1, f.dt0, f.dt1,
               (ff.t - f.t) AS elapsed_ms, f.vp, f.vya, f.vya1,
               sqrt(pow(ff.x-f.x,2)+pow(ff.y-f.y,2)+pow(ff.z-f.z,2)) AS e_still,
               (ff.x - (f.x + f.vx0*(ff.t-f.t)/1000.0)) AS dxr,
               (ff.y - (f.y + f.vy0*(ff.t-f.t)/1000.0)) AS dyr,
               (ff.z - (f.z + f.vz0*(ff.t-f.t)/1000.0)) AS dzr
        FROM feat f ASOF JOIN feat ff
            ON f.demo_key = ff.demo_key AND f.slot = ff.slot AND ff.t >= f.t + {h}
        WHERE (ff.t - f.t - {h}) BETWEEN -{TOL_MS} AND {TOL_MS}
        """
    )
    n_full = con.execute(f"SELECT count(*) FROM paired_full_{h}").fetchone()[0]
    if row_cap and n_full > row_cap:
        frac = min(1.0, row_cap / n_full * 1.05)  # 5% oversample buffer, then LIMIT to exact cap
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE paired_{h} AS
            SELECT * FROM paired_full_{h} WHERE random() < {frac}
            LIMIT {row_cap}
            """
        )
    else:
        con.execute(f"CREATE OR REPLACE TEMP TABLE paired_{h} AS SELECT * FROM paired_full_{h}")
    con.execute(f"DROP TABLE paired_full_{h}")
    return con.execute(f"SELECT count(*) FROM paired_{h}").fetchone()[0]


def _fetch_arrays(con, h: int) -> dict:
    tbl = con.execute(f"SELECT * FROM paired_{h}").arrow()
    if hasattr(tbl, "read_all"):
        tbl = tbl.read_all()
    return {
        name: tbl.column(name).combine_chunks().to_numpy(zero_copy_only=False)
        for name in tbl.column_names
    }


def _make_xy(cols: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Raw duckdb columns -> (X features, Y targets, e_still, e_lin), all float32.

    Rotation math lives here (numpy), not in SQL, so it's one place to read and
    test (see pipeline/tests/test_predict_enemy.py).
    """
    vx0 = cols["vx0"].astype(np.float64); vy0 = cols["vy0"].astype(np.float64); vz0 = cols["vz0"].astype(np.float64)
    vx1 = cols["vx1"].astype(np.float64); vy1 = cols["vy1"].astype(np.float64); vz1 = cols["vz1"].astype(np.float64)
    have_v1 = ~np.isnan(vx1)
    vx1 = np.nan_to_num(vx1, nan=0.0); vy1 = np.nan_to_num(vy1, nan=0.0); vz1 = np.nan_to_num(vz1, nan=0.0)
    dt1 = np.nan_to_num(cols["dt1"].astype(np.float64), nan=0.0)
    dt0 = cols["dt0"].astype(np.float64)
    elapsed = cols["elapsed_ms"].astype(np.float64)
    vp = cols["vp"].astype(np.float64)
    vya = cols["vya"].astype(np.int64)
    vya1 = np.nan_to_num(cols["vya1"].astype(np.float64), nan=0.0).astype(np.int64)

    yaw = vya.astype(np.float64) * TWO_PI_OVER_65536
    cy, sy = np.cos(yaw), np.sin(yaw)

    def frot(dx, dy):
        return dx * cy + dy * sy, dx * sy - dy * cy

    v0_f, v0_r = frot(vx0, vy0)
    v1_f, v1_r = frot(vx1, vy1)
    speed0 = np.sqrt(vx0 ** 2 + vy0 ** 2)
    raw_dyaw = ((vya - vya1 + 32768) % 65536) - 32768
    dyaw_view = raw_dyaw.astype(np.float64) * TWO_PI_OVER_65536
    vp_rad = vp * TWO_PI_OVER_65536
    sin_vp, cos_vp = np.sin(vp_rad), np.cos(vp_rad)

    X = np.stack([
        v0_f, v0_r, vz0, v1_f, v1_r, vz1, have_v1.astype(np.float64), speed0,
        dyaw_view, sin_vp, cos_vp, dt0, dt1, elapsed,
    ], axis=1).astype(np.float32)

    dxr = cols["dxr"].astype(np.float64); dyr = cols["dyr"].astype(np.float64); dzr = cols["dzr"].astype(np.float64)
    off_f, off_r = frot(dxr, dyr)
    Y = np.stack([off_f, off_r, dzr], axis=1).astype(np.float32)

    e_still = cols["e_still"].astype(np.float32)
    e_lin = np.sqrt(dxr ** 2 + dyr ** 2 + dzr ** 2).astype(np.float32)
    return X, Y, e_still, e_lin


# ==================================================================================
# build
# ==================================================================================

def build(split: str, out: Path = OUT, seed: int = 0):
    import duckdb
    out.mkdir(parents=True, exist_ok=True)
    cfg = SPLIT_CFG[split]
    files = _files(split)
    con = duckdb.connect()
    con.execute("SET threads TO 32")
    con.execute("SET preserve_insertion_order = false")

    t0 = time.time()
    used_filter = _stage_demo_sample(con, files, cfg["demo_cap"], seed)
    _stage_feat(con, files, used_filter)
    n_feat = con.execute("SELECT count(*) FROM feat").fetchone()[0]
    print(f"[{split}] feat rows {n_feat:,} ({time.time()-t0:.1f}s)", flush=True)

    Xs, Ys, Hs, ESs, ELs = [], [], [], [], []
    counts = {}
    for h in HORIZONS_MS:
        t0 = time.time()
        n = _stage_paired(con, h, cfg["row_cap"], seed)
        cols = _fetch_arrays(con, h)
        X, Y, e_still, e_lin = _make_xy(cols)
        Xs.append(X); Ys.append(Y); Hs.append(np.full(len(X), h, dtype=np.int16))
        ESs.append(e_still); ELs.append(e_lin)
        counts[str(h)] = int(len(X))
        print(f"[{split}] H={h} paired {n:,} -> kept {len(X):,} ({time.time()-t0:.1f}s)", flush=True)

    X = np.concatenate(Xs); Y = np.concatenate(Ys); Hh = np.concatenate(Hs)
    ES = np.concatenate(ESs); EL = np.concatenate(ELs)
    assert np.isfinite(X).all() and np.isfinite(Y).all()

    np.save(out / f"{split}_X.npy", X)
    np.save(out / f"{split}_Y.npy", Y)
    np.save(out / f"{split}_H.npy", Hh)
    np.save(out / f"{split}_Estill.npy", ES)
    np.save(out / f"{split}_Elin.npy", EL)
    meta = dict(split=split, n=int(len(X)), counts_by_horizon=counts,
                demo_cap=cfg["demo_cap"], row_cap=cfg["row_cap"],
                feature_cols=FEATURE_COLS, target_cols=TARGET_COLS)
    (out / f"{split}_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"[{split}] wrote {len(X):,} rows -> {out}", flush=True)
    return meta


# ==================================================================================
# model
# ==================================================================================

def _torch():
    import torch
    import torch.nn as nn
    return torch, nn


def make_net(in_dim: int, out_dim: int, width: int = 512, depth: int = 3):
    """depth = number of hidden layers. REVIEW ROUND 1: round 1 shipped 70,403
    params (width=256, depth=2) against a stated 19x margin to the K0.4 per-tick
    budget; scale with the data rather than parking there -- width and depth are
    both knobs now. See train()'s docstring for the configuration actually used.
    """
    torch, nn = _torch()

    class OffsetNet(nn.Module):
        def __init__(s):
            super().__init__()
            layers = [nn.Linear(in_dim, width), nn.ReLU()]
            for _ in range(depth - 1):
                layers += [nn.Linear(width, width), nn.ReLU()]
            layers += [nn.Linear(width, out_dim)]
            s.f = nn.Sequential(*layers)

        def forward(s, x):
            return s.f(x)

    net = OffsetNet()
    n_params = sum(p.numel() for p in net.parameters())
    return net, n_params


def train(steps: int = 100_000, batch: int = 16_384, lr: float = 3e-4, width: int = 512,
          depth: int = 3, huber_beta: float = 5.0, out: Path = OUT, seed: int = 0,
          tag: str = "model", ablate_view: bool = False, lr_min_frac: float = 0.05):
    """Huber (SmoothL1) loss on the frame-space offset, not MSE: offset targets have
    a long right tail (bunny-hop direction changes, occasional teleports on
    respawn/death), and both the median and the fraction-under-threshold numbers
    this module reports (REVIEW ROUND 1: the fixed 16u/28.7u gate is under review,
    so training no longer optimises toward any single threshold) care about the
    bulk of the distribution more than a squared loss's outlier sensitivity would.

    ablate_view drops the three view-derived columns (dyaw_view, sin_vp, cos_vp) --
    the ablation the spec's own hypothesis calls for: if these don't matter, the
    remaining features (still built on the view-yaw frame) reduce to a de-rotated
    velocity/acceleration model, and the improvement over linear (if any) has to be
    coming from acceleration alone, not from view angles.

    width=512, depth=3 (~1.05 M params, see make_net) and batch=16_384 are the
    REVIEW ROUND 1 scale-up from round 1's width=256/depth=2 (70,403 params,
    batch=4096): round 1 was told to use the H100 to the maximum rather than
    settle for a plateau measured on 0.8 % of the corpus. Checkpoint selection
    remains the val H=300 median specifically (not a horizon-pooled statistic):
    H=600 error is consistently far below H=300 error at every configuration
    tried, so a pooled median mostly just reports the easier horizon.
    """
    torch, nn = _torch()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(seed)
    X = np.load(out / "train_X.npy"); Y = np.load(out / "train_Y.npy")
    Xv = np.load(out / "val_X.npy"); Yv = np.load(out / "val_Y.npy")
    Hv = np.load(out / "val_H.npy")

    cols = list(range(len(FEATURE_COLS)))
    scale = FEATURE_SCALE.copy()
    if ablate_view:
        drop = {FEATURE_COLS.index(c) for c in ("dyaw_view", "sin_vp", "cos_vp")}
        cols = [c for c in cols if c not in drop]
        scale = scale[cols]

    s_sc = torch.tensor(scale, device=dev)
    Xt = torch.tensor(X[:, cols], device=dev) / s_sc
    Yt = torch.tensor(Y, device=dev)
    Xvt = torch.tensor(Xv[:, cols], device=dev) / s_sc
    Yvt = torch.tensor(Yv, device=dev)
    m300 = Hv == 300
    n = Xt.shape[0]

    net, n_params = make_net(len(cols), 3, width, depth)
    net = net.to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=steps, eta_min=lr * lr_min_frac)
    loss_fn = nn.SmoothL1Loss(beta=huber_beta)

    def _val_forward(chunk=2_000_000):
        # val is now tens of millions of rows (REVIEW ROUND 1): a single forward
        # pass of width=512 through all of it at once peaks at tens of GB of
        # activations with no_grad still materialising each layer's output.
        # Chunking keeps peak memory to one chunk's worth regardless of val size.
        outs = []
        with torch.no_grad():
            for i in range(0, Xvt.shape[0], chunk):
                outs.append(net(Xvt[i:i + chunk]))
        return torch.cat(outs)

    t0 = time.time()
    log = []
    best_h300 = float("inf")
    best_state = None
    for it in range(1, steps + 1):
        idx = torch.randint(0, n, (batch,), device=dev)
        pred = net(Xt[idx])
        loss = loss_fn(pred, Yt[idx])
        opt.zero_grad(set_to_none=True); loss.backward(); opt.step(); sched.step()
        if it % 5_000 == 0:
            vpred = _val_forward()
            verr = torch.sqrt(((vpred - Yvt) ** 2).sum(1)).cpu().numpy()
            h300_med = float(np.median(verr[m300]))
            h600_med = float(np.median(verr[~m300]))
            h600_p90 = float(np.percentile(verr[~m300], 90))
            if h300_med < best_h300:
                best_h300 = h300_med
                best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
            loss_v = float(loss.detach())
            log.append(dict(it=it, train_loss=loss_v, val_h300_median_u=h300_med,
                             val_h600_median_u=h600_med, val_h600_p90_u=h600_p90,
                             s=round(time.time() - t0, 1)))
            print(f"[{tag} {it:>7}] loss {loss_v:.3f}  val H300 med {h300_med:.2f}u (best {best_h300:.2f}u)  "
                  f"H600 med {h600_med:.2f}u p90 {h600_p90:.2f}u  {time.time()-t0:.0f}s", flush=True)

    net.load_state_dict(best_state)
    ck = dict(state_dict=net.state_dict(), width=width, depth=depth, in_cols=cols, scale=scale,
              feature_cols=[FEATURE_COLS[c] for c in cols], target_cols=TARGET_COLS,
              n_params=n_params, huber_beta=huber_beta, ablate_view=ablate_view)
    torch.save(ck, out / f"{tag}.pt")
    (out / f"{tag}_train_log.json").write_text(json.dumps(log, indent=2))
    print(f"saved {out/f'{tag}.pt'}  params={n_params}  best_val_h300_median={best_h300:.2f}u", flush=True)
    return n_params, best_h300


# ==================================================================================
# eval
# ==================================================================================

# REVIEW ROUND 1: the fixed 16u/28.7u gate is under review (the reviewer notes
# 16u is the *direct-hit* fire_tolerance; the dominant projectile, the rocket, is
# a splash weapon whose own fire_tolerance is 40u; 160u is the splash radius).
# Report the raw distribution against all three rather than a single derived
# threshold, and let the threshold question be settled on these numbers.
DIST_THRESHOLDS_U = (16.0, 40.0, 160.0)


def _dist_stats(err: np.ndarray) -> dict:
    return dict(
        median_u=round(float(np.median(err)), 2),
        p90_u=round(float(np.percentile(err, 90)), 2),
        **{f"frac_under_{int(t)}u": round(float((err < t).mean()), 4) for t in DIST_THRESHOLDS_U},
    )


def _forward_chunked(net, xb, chunk=2_000_000):
    torch, _ = _torch()
    outs = []
    with torch.no_grad():
        for i in range(0, xb.shape[0], chunk):
            outs.append(net(xb[i:i + chunk]))
    return torch.cat(outs)


def _eval_cached(net, scale, in_cols, X, Y, Estill, Elin, Hh, dev):
    """Median, p90, AND the fraction under each of DIST_THRESHOLDS_U, for all
    three of still/linear/learned, at both horizons. Chunked forward pass:
    round 1's val set was 1.4M rows; round 2's is 10-20M+, and a single forward
    through a width=512 net over tens of millions of rows at once would peak at
    tens of GB of activations even under no_grad."""
    torch, _ = _torch()
    res = {}
    s_sc = torch.tensor(scale, device=dev)
    for h in HORIZONS_MS:
        m = Hh == h
        xb = torch.tensor(X[m][:, in_cols], device=dev) / s_sc
        yb = Y[m]
        pred = _forward_chunked(net, xb).cpu().numpy()
        e_learn = np.sqrt(((pred - yb) ** 2).sum(1))
        es, el = Estill[m], Elin[m]
        res[str(h)] = dict(
            n=int(m.sum()),
            still=_dist_stats(es), linear=_dist_stats(el), learned=_dist_stats(e_learn),
        )
    return res


def evaluate(split: str = "val", ckpt: str = "model.pt", out: Path = OUT):
    torch, _ = _torch()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    ck = torch.load(out / ckpt, map_location=dev, weights_only=False)
    net, _ = make_net(len(ck["in_cols"]), 3, ck["width"], ck.get("depth", 2))
    net.load_state_dict(ck["state_dict"]); net = net.to(dev); net.eval()

    X = np.load(out / f"{split}_X.npy"); Y = np.load(out / f"{split}_Y.npy")
    Hh = np.load(out / f"{split}_H.npy")
    ES = np.load(out / f"{split}_Estill.npy"); EL = np.load(out / f"{split}_Elin.npy")
    res = _eval_cached(net, ck["scale"], ck["in_cols"], X, Y, ES, EL, Hh, dev)
    for h, v in res.items():
        print(f"[{split} H={h}] n={v['n']:,}")
        for k in ("still", "linear", "learned"):
            d = v[k]
            print(f"    {k:8s} median {d['median_u']:>7.1f}u  p90 {d['p90_u']:>7.1f}u  "
                  f"<16u {d['frac_under_16u']*100:5.1f}%  <40u {d['frac_under_40u']*100:5.1f}%  "
                  f"<160u {d['frac_under_160u']*100:5.1f}%")
    return res


def _arch_string(ck: dict) -> str:
    depth = ck.get("depth", 2)
    dims = "->".join([str(len(ck["in_cols"]))] + [str(ck["width"])] * depth + ["3"])
    return f"MLP {dims}, ReLU, SmoothL1(beta={ck['huber_beta']}) loss on frame-space offset"


def evaluate_test_and_report(ckpt: str = "model.pt", out: Path = OUT, key: str = "round_2_test_measurement_FINAL"):
    """The ONE touch of split=test -- DO NOT CALL until instructed (owner sign-off
    after REVIEW ROUND 1: "test split stays untouched until the final
    measurement"). Streams the full test population through duckdb (no demo/row
    subsampling -- same universe k0_baseline.json used) and the trained net, in
    chunks. Test rows are never cached to disk: the raw feature matrix would be
    several GB for no benefit (the numbers are exact from the in-memory pass;
    there is nothing to iterate against once written, and nothing should be).

    No gate/verdict computed here -- the 16u/28.7u threshold fell under review
    and the owner has settled the question rather than moved it (see spec REVIEW
    ROUND 1/2). Reports median, p90, and the fraction of rows under 16u/40u/160u
    for all three of still/linear/learned, same as evaluate() reports for val.

    MERGES into the existing evidence/k0_2_predictor.json under `key` rather than
    overwriting it: that file also carries the val-split results and the
    superseded round-1 historical record, and this is meant to be an additional,
    clearly-labelled, closing entry -- not a replacement for either."""
    import duckdb
    torch, _ = _torch()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    ck = torch.load(out / ckpt, map_location=dev, weights_only=False)
    net, n_params = make_net(len(ck["in_cols"]), 3, ck["width"], ck.get("depth", 2))
    net.load_state_dict(ck["state_dict"]); net = net.to(dev); net.eval()

    files = _files("test")
    con = duckdb.connect()
    con.execute("SET threads TO 32")
    _stage_demo_sample(con, files, None, 0)
    _stage_feat(con, files, False)
    n_feat = con.execute("SELECT count(*) FROM feat").fetchone()[0]

    horizons = {}
    s_sc = torch.tensor(ck["scale"], device=dev)
    for h in HORIZONS_MS:
        n = _stage_paired(con, h, None, 0)
        cols = _fetch_arrays(con, h)
        X, Y, e_still, e_lin = _make_xy(cols)
        xb = torch.tensor(X[:, ck["in_cols"]], device=dev) / s_sc
        pred = _forward_chunked(net, xb).cpu().numpy()
        e_learn = np.sqrt(((pred - Y) ** 2).sum(1))
        horizons[str(h)] = dict(
            n=int(len(X)),
            still=_dist_stats(e_still), linear=_dist_stats(e_lin), learned=_dist_stats(e_learn),
        )
        v = horizons[str(h)]
        print(f"[TEST H={h}] n={len(X):,}  still {v['still']['median_u']}/{v['still']['p90_u']}  "
              f"linear {v['linear']['median_u']}/{v['linear']['p90_u']}  "
              f"learned {v['learned']['median_u']}/{v['learned']['p90_u']}", flush=True)

    entry = dict(
        note=("Final, one-time split=test measurement. Not a gate -- the gate as written fell "
              "and the owner is not moving it; this is a closing record for a banked artifact "
              "(K1-K3 deferred). Compare against this same checkpoint's val numbers elsewhere in "
              "this file to see the val/test gap directly."),
        checkpoint_path=str((out / ckpt).resolve()),
        dt_window_ms=[DT_MIN, DT_MAX], tol_ms=TOL_MS,
        dist_thresholds_u=list(DIST_THRESHOLDS_U),
        row_counts={"train": _meta_n("train", out), "val": _meta_n("val", out), "test": n_feat},
        feature_set=ck["feature_cols"],
        architecture=_arch_string(ck),
        n_params=n_params,
        split="test",
        horizons=horizons,
    )

    existing = json.loads(EVIDENCE.read_text()) if EVIDENCE.exists() else {}
    existing[key] = entry
    EVIDENCE.write_text(json.dumps(existing, indent=2))
    print(f"wrote {EVIDENCE} (merged under key '{key}')")
    return entry


def _meta_n(split, out):
    p = out / f"{split}_meta.json"
    if p.exists():
        return json.loads(p.read_text())["n"]
    return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "train", "eval", "eval_test"])
    ap.add_argument("--split", default="train")
    # REVIEW ROUND 1 scale-up (see train()'s docstring): width=512, depth=3
    # (~1.05M params), batch=16_384, steps=100_000, over the full-diversity
    # 100M-row train build. Round 1's width=256/depth=2/batch=4096/steps=150_000
    # (70,403 params, 0.8% of the corpus) plateaued at val H=300 median ~35.1u.
    ap.add_argument("--steps", type=int, default=100_000)
    ap.add_argument("--batch", type=int, default=16_384)
    ap.add_argument("--width", type=int, default=512)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--tag", default="model")
    ap.add_argument("--ablate-view", action="store_true")
    ap.add_argument("--ckpt", default="model.pt")
    ap.add_argument("--huber-beta", type=float, default=5.0)
    ap.add_argument("--lr", type=float, default=3e-4)
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.split)
    elif a.cmd == "train":
        train(steps=a.steps, batch=a.batch, width=a.width, depth=a.depth, tag=a.tag,
              ablate_view=a.ablate_view, huber_beta=a.huber_beta, lr=a.lr)
    elif a.cmd == "eval":
        evaluate(split=a.split, ckpt=a.ckpt)
    elif a.cmd == "eval_test":
        evaluate_test_and_report(ckpt=a.ckpt)
