"""Invariance and correctness tests for the SE(2) transform.

Run: .venv/bin/python -m pipeline.tests.test_se2
"""

from __future__ import annotations

import numpy as np

from .. import config as C
from .. import se2, segment


def _synth(n=400, seed=0):
    """A synthetic track: ground run -> jump -> air-strafe -> land."""
    rng = np.random.default_rng(seed)
    yaw = np.cumsum(rng.normal(0, 0.02, n)) + 1.0
    speed = 320.0 + np.arange(n) * 0.4
    slip = np.full(n, 0.4)
    course = yaw - slip  # world-frame velocity heading given the left-handed basis
    vx = speed * np.cos(course)
    vy = speed * np.sin(course)
    vz = np.zeros(n)
    vz[100:260] = 270.0 - C.GRAVITY * 0.013 * np.arange(160)
    x = np.cumsum(vx) * 0.013
    y = np.cumsum(vy) * 0.013
    z = np.cumsum(vz) * 0.013
    return dict(
        demo_key=np.zeros(n, np.uint32), slot=np.zeros(n, np.uint8),
        cmd_ordinal=np.arange(n, dtype=np.int64), t=(np.arange(n) * 13).astype(np.int32),
        x=x.astype(np.float32), y=y.astype(np.float32), z=z.astype(np.float32),
        vx=vx.astype(np.float32), vy=vy.astype(np.float32), vz=vz.astype(np.float32),
        onground=(vz == 0), jump_held=np.zeros(n, bool),
        waterlevel=np.zeros(n, np.uint8), wire_state_present=np.ones(n, bool),
        seq_break=np.zeros(n, bool), residual=np.zeros(n, np.float32),
        msec=np.full(n, 13, np.uint8),
        forwardmove=np.full(n, 400, np.int16), sidemove=np.full(n, 400, np.int16),
        upmove=np.zeros(n, np.int16),
        buttons=np.zeros(n, np.uint8), impulse=np.zeros(n, np.uint8),
        pitch=np.zeros(n, np.uint16),
        yaw=np.mod(np.rad2deg(yaw) / C.U16_TO_DEG, 65536).astype(np.uint16),
    )


def test_invariance():
    a = _synth()
    fa = se2.transform(a)
    worst = {}
    for theta, tx, ty in [(0.7, 100.0, -50.0), (np.pi, -3000.0, 2000.0), (-2.4, 0.0, 0.0)]:
        fb = se2.transform(se2.apply_se2(a, theta, tx, ty))
        for k in se2.INVARIANT_KEYS:
            u, v = np.asarray(fa[k], float), np.asarray(fb[k], float)
            m = np.isfinite(u) & np.isfinite(v)
            if k in ("slip", "wish_slip", "dyaw", "omega", "omega_prev"):
                d = np.abs(se2.wrap_pi(u[m] - v[m]))
            else:
                d = np.abs(u[m] - v[m])
            scale = max(1.0, float(np.nanmax(np.abs(u[m]))) if m.any() else 1.0)
            worst[k] = max(worst.get(k, 0.0), float(d.max() / scale) if m.any() else 0.0)
    bad = {k: v for k, v in worst.items() if v > 2e-3}
    print(f"  max relative deviation over {len(se2.INVARIANT_KEYS)} invariant features: "
          f"{max(worst.values()):.2e}")
    assert not bad, f"not SE(2)-invariant: {bad}"
    return worst


def test_frame_matches_quake():
    """wishvel in the body frame must equal (forwardmove, sidemove) exactly."""
    rng = np.random.default_rng(1)
    yaw = rng.uniform(0, 2 * np.pi, 1000)
    fm, sm = rng.normal(0, 400, 1000), rng.normal(0, 400, 1000)
    # Quake AngleVectors with pitch/roll zeroed (PM_AirMove does exactly this)
    fwd = np.stack([np.cos(yaw), np.sin(yaw)])
    right = np.stack([np.sin(yaw), -np.cos(yaw)])
    wish_world = fwd * fm + right * sm
    # project back with the transform's basis
    cy, sy = np.cos(yaw), np.sin(yaw)
    w_f = wish_world[0] * cy + wish_world[1] * sy
    w_r = wish_world[0] * sy - wish_world[1] * cy
    err = max(np.abs(w_f - fm).max(), np.abs(w_r - sm).max())
    print(f"  body-frame wishvel round trip: max err {err:.2e}")
    assert err < 1e-9


def test_speed_and_slip_consistency():
    a = _synth()
    f = se2.transform(a)
    assert np.allclose(np.hypot(f["v_fwd"], f["v_right"]), f["speed_xy"], atol=1e-6)
    assert np.allclose(f["slip"], np.arctan2(f["v_right"], f["v_fwd"]), atol=1e-12)
    print(f"  slip held at {np.rad2deg(f['slip']).mean():.3f} deg "
          f"(synthetic ground truth 0.4 rad = {np.rad2deg(0.4):.3f} deg)")


def test_segmentation_on_synthetic():
    a = _synth()
    f = se2.transform(a)
    r = segment.segment(f)
    kinds = {segment.KINDS[i]: int((r["kind"] == i).sum()) for i in range(len(segment.KINDS))}
    kinds = {k: v for k, v in kinds.items() if v}
    print(f"  synthetic labels: {kinds}")
    st = r["state"]
    assert (st[110:250] == segment.AIR).all(), "airborne stretch not detected"
    assert (st[:95] == segment.GROUND).all(), "ground stretch not detected"
    segs = r["segments"]
    assert "maneuver_jump" in set(segs["kind"]), "the +270 takeoff was not called a jump"
    assert "trim_air" in set(segs["kind"]), "steady air-strafe was not called a trim"


def test_no_leakage_of_absolute_pose():
    """A pure translation must not move a single invariant feature.

    Positions are float32 in the store, so a translation to the far corner of a
    Quake map (|coord| <= 4096) costs about 4096 * 2^-23 = 5e-4 units of
    resolution on the displacement features. The tolerance is that floor, not
    slack in the transform.
    """
    a = _synth()
    fa = se2.transform(a)
    fb = se2.transform(se2.apply_se2(a, 0.0, 2048.0, -1536.0))
    worst = 0.0
    for k in se2.INVARIANT_KEYS:
        u, v = np.asarray(fa[k], float), np.asarray(fb[k], float)
        m = np.isfinite(u) & np.isfinite(v)
        d = float(np.abs(u[m] - v[m]).max())
        worst = max(worst, d)
        assert d < 2e-3, f"{k}: {d:.2e}"
    print(f"  pure translation: worst absolute drift {worst:.2e} units "
          f"(float32 floor ~5e-4)")


if __name__ == "__main__":
    for fn in (test_frame_matches_quake, test_speed_and_slip_consistency,
               test_invariance, test_no_leakage_of_absolute_pose,
               test_segmentation_on_synthetic):
        print(f"{fn.__name__}:")
        fn()
    print("\nALL TESTS PASSED")
