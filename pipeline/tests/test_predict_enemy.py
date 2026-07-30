"""Correctness checks for pipeline/predict_enemy.py's rotation math.

Run: .venv/bin/python -m pipeline.tests.test_predict_enemy
"""

from __future__ import annotations

import numpy as np

from .. import predict_enemy as pe


def _fake_cols(n=2000, seed=0):
    """Synthetic duckdb-column dict shaped like _fetch_arrays's output, spanning
    a range of yaws, speeds and a few "no previous sample" edge rows."""
    rng = np.random.default_rng(seed)
    vx0 = rng.normal(0, 300, n); vy0 = rng.normal(0, 300, n); vz0 = rng.normal(0, 50, n)
    vx1 = rng.normal(0, 300, n); vy1 = rng.normal(0, 300, n); vz1 = rng.normal(0, 50, n)
    no_prev = rng.random(n) < 0.1
    vx1[no_prev] = np.nan; vy1[no_prev] = np.nan; vz1[no_prev] = np.nan
    dt1 = rng.uniform(8, 40, n); dt1[no_prev] = np.nan
    dxr = rng.normal(0, 100, n); dyr = rng.normal(0, 100, n); dzr = rng.normal(0, 30, n)
    return dict(
        vx0=vx0, vy0=vy0, vz0=vz0, vx1=vx1, vy1=vy1, vz1=vz1,
        dt0=rng.uniform(8, 40, n), dt1=dt1, elapsed_ms=rng.uniform(275, 325, n),
        vp=rng.integers(0, 65536, n), vya=rng.integers(0, 65536, n),
        vya1=rng.integers(0, 65536, n).astype(float),
        e_still=np.sqrt(dxr ** 2 + dyr ** 2 + dzr ** 2),
        dxr=dxr, dyr=dyr, dzr=dzr,
    )


def test_rotation_is_isometry():
    """Frame-space target norm must equal the world-space linear-extrapolation
    error (e_lin) exactly: that equivalence is the whole reason the training loss
    (frame-space MSE/Huber) is a valid proxy for the world-space metric the gate
    is measured in."""
    cols = _fake_cols()
    X, Y, e_still, e_lin = pe._make_xy(cols)
    recomputed = np.sqrt((Y ** 2).sum(1))
    d = np.abs(recomputed - e_lin)
    assert d.max() < 1e-3, f"rotation is not an isometry: max diff {d.max():.2e}"
    print(f"  rotation isometry: max |off-space norm - e_lin| = {d.max():.2e}")


def test_have_v1_flag_matches_nans():
    cols = _fake_cols()
    X, Y, e_still, e_lin = pe._make_xy(cols)
    have_v1 = X[:, pe.FEATURE_COLS.index("have_v1")]
    expected = ~np.isnan(cols["vx1"])
    assert np.array_equal(have_v1.astype(bool), expected)
    # and rows without a previous sample must have zeroed v1 features, not NaN
    v1f = X[:, pe.FEATURE_COLS.index("v1_f")]
    v1r = X[:, pe.FEATURE_COLS.index("v1_r")]
    assert np.isfinite(v1f).all() and np.isfinite(v1r).all()
    assert (v1f[~expected] == 0).all() and (v1r[~expected] == 0).all()
    print("  have_v1 flag matches vx1 nulls; v1 features zeroed (not NaN) when absent")


def test_frame_zeroes_current_yaw():
    """By construction the frame's forward axis IS the current view yaw, so a
    velocity pointing exactly along the view direction must land entirely on
    v0_f with v0_r == 0 -- the one closed-form case that catches a sign error
    in frot() immediately."""
    n = 500
    rng = np.random.default_rng(1)
    vya = rng.integers(0, 65536, n)
    yaw = vya.astype(np.float64) * pe.TWO_PI_OVER_65536
    speed = rng.uniform(50, 500, n)
    vx0 = speed * np.cos(yaw); vy0 = speed * np.sin(yaw)
    cols = dict(
        vx0=vx0, vy0=vy0, vz0=np.zeros(n),
        vx1=np.full(n, np.nan), vy1=np.full(n, np.nan), vz1=np.full(n, np.nan),
        dt0=np.full(n, 16.0), dt1=np.full(n, np.nan), elapsed_ms=np.full(n, 300.0),
        vp=np.zeros(n, dtype=int), vya=vya, vya1=vya.astype(float),
        e_still=np.zeros(n), dxr=np.zeros(n), dyr=np.zeros(n), dzr=np.zeros(n),
    )
    X, Y, _, _ = pe._make_xy(cols)
    v0_f = X[:, pe.FEATURE_COLS.index("v0_f")]
    v0_r = X[:, pe.FEATURE_COLS.index("v0_r")]
    assert np.allclose(v0_f, speed, atol=1e-6), f"max err {np.abs(v0_f-speed).max():.2e}"
    assert np.allclose(v0_r, 0.0, atol=1e-6), f"max |v0_r| {np.abs(v0_r).max():.2e}"
    print("  velocity aligned with view yaw lands entirely on v0_f, v0_r == 0")


def test_dyaw_view_wraps():
    """A view yaw that wraps from just below 65536 to just above 0 must report a
    small positive turn, not a ~65536-unit jump."""
    cols = dict(
        vx0=np.array([0.0]), vy0=np.array([0.0]), vz0=np.array([0.0]),
        vx1=np.array([np.nan]), vy1=np.array([np.nan]), vz1=np.array([np.nan]),
        dt0=np.array([16.0]), dt1=np.array([np.nan]), elapsed_ms=np.array([300.0]),
        vp=np.array([0]), vya=np.array([10]), vya1=np.array([65530.0]),
        e_still=np.array([0.0]), dxr=np.array([0.0]), dyr=np.array([0.0]), dzr=np.array([0.0]),
    )
    X, _, _, _ = pe._make_xy(cols)
    dyaw = X[0, pe.FEATURE_COLS.index("dyaw_view")]
    expected = 16 * pe.TWO_PI_OVER_65536  # (10 - 65530) wraps to +16
    assert abs(dyaw - expected) < 1e-9, f"{dyaw} vs {expected}"
    print(f"  yaw wraparound: dyaw_view={dyaw:.5f} rad (expected {expected:.5f})")


if __name__ == "__main__":
    for fn in (test_rotation_is_isometry, test_have_v1_flag_matches_nans,
               test_frame_zeroes_current_yaw, test_dyaw_view_wraps):
        print(f"{fn.__name__}:")
        fn()
    print("\nALL TESTS PASSED")
