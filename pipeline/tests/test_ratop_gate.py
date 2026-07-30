"""Does the RA-top manoeuvre gate pass the human and fail the go-around?

The two cases the gate exists to separate (`evidence/ratop_edge_jump.json`):

  * The owner's reference demo for ring_to_ratop performs the edge-to-edge jump the anchors were
    derived from — it MUST pass, and the margin says how much room the 96 u tolerance leaves.
  * A trace that walks around the void on the probed floor route — takeoff ledge z312 down to the
    z264 walkway, east to the ramp at x~316, up, then west along the RA ledge — reaches the same
    place without the jump. The envelope gate was measured unable to fail this line (43-63 u from
    the cloud vs bands of 48-111 u); the manoeuvre gate MUST.

Run: .venv/bin/python -m pipeline.tests.test_ratop_gate     (CPU only; the void probe uses
rex_env's pointcontents on the map file, no environments are stepped)
"""

from __future__ import annotations

import numpy as np

from .. import ratop_gate as RG
from .. import record_reference as RF


def _walk(points: list[tuple], step: float = 4.0) -> np.ndarray:
    """Densify a polyline to ~`step` u spacing — a 77 Hz walk at ~300 u/s."""
    out = [np.asarray(points[0], np.float64)]
    for a, b in zip(points, points[1:]):
        a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
        n = max(int(np.ceil(np.linalg.norm(b - a) / step)), 1)
        for k in range(1, n + 1):
            out.append(a + (b - a) * k / n)
    return np.asarray(out, np.float32)


def _hop(a: tuple, b: tuple, ticks: int = 20, rise: float = 45.0) -> np.ndarray:
    """A ballistic arc from a to b: the airborne part of a jump or a drop."""
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    t = np.linspace(0.0, 1.0, ticks + 2)[1:-1]
    p = a[None, :] + (b - a)[None, :] * t[:, None]
    p[:, 2] += rise * 4.0 * t * (1.0 - t)  # parabola peaking `rise` above the chord
    return p.astype(np.float32)


def test_reference_demo_passes() -> dict:
    """The owner's ring-to-ratop recording performs the manoeuvre it defined."""
    demo = RF.DEMO_DIR / "ring-to-ratop.qwd"
    d = RF.load(demo)
    fr = d["frames"]
    pos = np.asarray([(f["x"], f["y"], f["z"]) for f in fr], np.float32)
    ground = np.asarray([f["ground"] for f in fr], bool)
    speed = np.asarray([f["speed"] for f in fr], np.float32)
    res = RG.check("ring_to_ratop", pos, ground, speed)
    assert res is not None
    b = res["best"]
    print(f"  referensdemot {demo.name}: {len(fr)} tick, "
          f"takeoff-fel {b['takeoff_err_u']} u, landnings-fel {b['landing_err_u']} u "
          f"(tolerans {RG.TOL_U} u), tomrum {b['void_u']} u (krav >= {RG.MIN_VOID_U} u)")
    assert res["executed"], f"referensdemot underkändes: {res}"
    assert b["void_u"] is not None and b["void_u"] >= RG.MIN_VOID_U
    return {"executed": True, "takeoff_err_u": b["takeoff_err_u"],
            "landing_err_u": b["landing_err_u"], "void_u": b["void_u"],
            "margin_u": round(RG.TOL_U - b["worst_u"], 1)}


def test_other_gated_routes_pass_their_demos() -> None:
    """Every gated route with a parseable owner demo executes its own manoeuvre.

    quad_to_ra has no owner reference demo (see record_reference.py's audit note); its anchors
    come from the same evidence file and are covered by the corpus cross-check there.
    """
    for demo, route in [("ralow-to-ratop.qwd", "ralow_to_ratop"),
                        ("(spawn)sngspawn-to-ring-to-ratop.qwd", "tunnel_to_ra")]:
        d = RF.load(RF.DEMO_DIR / demo)
        fr = d["frames"]
        pos = np.asarray([(f["x"], f["y"], f["z"]) for f in fr], np.float32)
        ground = np.asarray([f["ground"] for f in fr], bool)
        speed = np.asarray([f["speed"] for f in fr], np.float32)
        res = RG.check(route, pos, ground, speed)
        b = res["best"]
        print(f"  {route}: takeoff-fel {b['takeoff_err_u']} u, landnings-fel "
              f"{b['landing_err_u']} u, tomrum {b['void_u']} u")
        assert res["executed"], f"{route}: {res}"


def test_go_around_fails() -> dict:
    """The synthesized go-around from the evidence file — same floor corridor, no jump."""
    # The probed-floor waypoints from evidence/ratop_edge_jump.json (go_around_waypoints_xy) with
    # the z profile the corridor has: ledge 312, walkway 264, ramp up at x~316, RA ledge 328.
    ledge = (60.0, -551.0, 312.0)
    walkway = [(120.0, -556.0, 264.0), (200.0, -562.0, 264.0)]
    ramp = [(296.0, -570.0, 264.0), (316.0, -600.0, 264.0),
            (316.0, -640.0, 290.0), (316.0, -688.0, 316.0)]
    ra_ledge = [(288.0, -700.0, 328.0), (256.0, -702.0, 328.0),
                (216.0, -696.0, 328.0), (180.0, -694.0, 328.0)]

    parts: list[tuple[np.ndarray, bool]] = [
        (np.repeat([[*ledge]], 4, axis=0).astype(np.float32), True),   # standing at the edge
        (_hop(ledge, walkway[0], ticks=14, rise=2.0), False),          # DROP to the walkway
        (_walk([walkway[0], walkway[1]]), True),                       # walk east
        (_hop(walkway[1], ramp[0], ticks=20, rise=45.0), False),       # an ordinary bunny hop
        (_walk(ramp), True),                                           # up the ramp
        (_walk([ramp[-1], *ra_ledge]), True),                          # west along the RA ledge
    ]
    pos = np.concatenate([p for p, _ in parts])
    ground = np.concatenate([np.full(len(p), g) for p, g in parts])
    res = RG.check("ring_to_ratop", pos, ground)
    assert res is not None
    b = res["best"]
    end = pos[-1]
    d_land = float(np.linalg.norm(end - np.asarray(RG.MANOEUVRE_GATES["ring_to_ratop"]["landing"],
                                                   np.float32)))
    print(f"  gå-runt-spåret: {len(pos)} tick, slutar {d_land:.1f} u från landningsankaret "
          f"utan hoppet — närmaste luftsegment: takeoff-fel {b['takeoff_err_u']} u, "
          f"landnings-fel {b['landing_err_u']} u ({res['reason']})")
    assert not res["executed"], f"gå-runt-spåret godkändes: {res}"
    # It ends standing on the landing — the one-event check is what fails it, not arrival distance.
    assert d_land < RG.TOL_U
    return {"executed": False, "takeoff_err_u": b["takeoff_err_u"],
            "landing_err_u": b["landing_err_u"],
            "fail_margin_u": round(b["worst_u"] - RG.TOL_U, 1),
            "ends_u_from_landing": round(d_land, 1)}


def test_ungated_route_is_untouched() -> None:
    """Routes off RA top carry no requirement — check() must say so, not invent one."""
    assert RG.check("window_to_rl", np.zeros((10, 3), np.float32), np.ones(10, bool)) is None
    print("  ogrindad rutt (window_to_rl): check() -> None")


if __name__ == "__main__":
    for fn in (test_reference_demo_passes, test_other_gated_routes_pass_their_demos,
               test_go_around_fails, test_ungated_route_is_untouched):
        print(f"{fn.__name__}:")
        fn()
    print("\nALL TESTS PASSED")
