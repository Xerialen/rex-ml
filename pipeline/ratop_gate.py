"""The RA-top edge jump as a manoeuvre requirement — the gate the envelope cannot be.

Measured 2026-07-30 (`evidence/ratop_edge_jump.json`): a bot that walks *around* the RA-top void —
z=264 walkway east to x~316, up the ramp at x~300-330, west along the RA ledge — stays 43-63 u from
every RA-top route's human point cloud, inside ring's 84.3 u band and tunnel's 110.7 u band, 3-5 u
outside ralow's 47.8, and quad_to_ra has no band at all. The envelope is an unordered cloud with no
notion of sequence or of being airborne, and the human line itself crosses that corridor earlier in
the run, so the go-around can never be reliably failed by it.

What *does* separate the two lines is the manoeuvre: every human run crosses the void in one jump.
So each RA-top route carries a requirement, checked with the same one-event logic as
`manoeuvres.executed()`: one airborne segment whose takeoff is within `TOL_U` of the human takeoff
AND whose next ground contact is within `TOL_U` of the human landing — walking round and standing on
the landing spot is not the jump. Additionally the segment must fly over `MIN_VOID_U` of void
(floor probed along the flight, same probe as `record_replay.air_segments`), so a hop between two
points on the near ledge cannot satisfy the anchors by accident.
"""

from __future__ import annotations

import numpy as np

from . import manoeuvres as MA
from . import edge_signal as ES
from . import cohort_routes as C

# Anchor tolerance. 96 u covers the corpus takeoff spread (std x up to 38 u on tunnel_to_ra) while
# staying far short of the 158-185 u the go-around corridor strays from the jump line.
TOL_U = 96.0
# Two plain jumps' worth of height under the flight — same threshold as `record_replay.VOID_U`.
# The real void under these jumps is 320-336 u; a ledge hop clears ~0.
MIN_VOID_U = 96.0
# Past dm3's deepest pit, so the probe never reports its own reach as floor
# (same as `record_replay.VOID_PROBE_U`).
VOID_PROBE_U = 512.0

# Human takeoff/landing anchors per RA-top route: the `human_jump` fields of
# `evidence/ratop_edge_jump.json`, read off each route's reference demo (apex-split airborne
# segments merged). Embedded as literals so the gate has no runtime file dependency; the evidence
# file is the source and the cross-check (corpus takeoff/landing means sit 27-100 u away, inside
# TOL_U except tunnel's corpus line which takes the jump further west — still one jump over the
# same void).
MANOEUVRE_GATES: dict[str, dict] = {
    "ring_to_ratop": {"takeoff": (59.6, -551.1, 312.0), "landing": (159.9, -674.6, 328.0)},
    "ralow_to_ratop": {"takeoff": (73.2, -554.1, 312.0), "landing": (178.0, -700.2, 328.0)},
    "quad_to_ra": {"takeoff": (68.0, -561.1, 312.0), "landing": (216.9, -694.6, 328.0)},
    "tunnel_to_ra": {"takeoff": (91.6, -564.0, 296.0), "landing": (202.5, -687.2, 328.0)},
    # Not RA-top but the same disease: `sng_to_quad`'s envelope band is 289.5 u from only 4 runs
    # (`evidence/envelope_band.json`) and gates nothing, while its defining manoeuvre is the double
    # jump via the mid ledge over a 263 u void (`evidence/sng_to_quad_route.json`, owner demo).
    # The gate is the flight OFF the west lip. Two landings are legitimate, because the mid ledge
    # (z 99.9) is HIGHER than both lips: a one-tick ledge touch is a local z maximum and is merged
    # away by `_strip_apex_blips` (the owner's demo measures exactly so — one 50-tick segment
    # landing at the far lip), while a two-tick touch survives and splits the jump at the ledge.
    # All 4 corpus runs pass 8.9-39.1 u from the ledge and 11-35 u from the takeoff.
    "sng_to_quad": {"takeoff": (459.5, 151.6, 56.0),
                    "landing": ((598.4, 110.8, 99.9), (732.0, 168.8, 56.0))},
}


def _strip_apex_blips(pos: np.ndarray, ground: np.ndarray) -> np.ndarray:
    """Clear single-tick 'ground' contacts at a flight's apex.

    The reference demos carry no ground bit; it is derived as vz == 0, which fires for one tick at
    a jump's apex and cuts the jump in two (`evidence/ratop_edge_jump.json` merged those splits
    when deriving the anchors, so the check must see the same single event). The blip is
    identifiable because an apex is a local *maximum* of z where every real one-tick touch — a
    bunny hop — is a local minimum: only the maxima are cleared, so bot traces with a real ground
    flag pass through unchanged.
    """
    g = ground.copy()
    for i in range(1, len(g) - 1):
        if g[i] and not g[i - 1] and not g[i + 1] \
                and pos[i, 2] >= max(pos[i - 1, 2], pos[i + 1, 2]) - 0.5:
            g[i] = False
    return g


def _void_u(flight: np.ndarray) -> float:
    """How far the floor along the flight drops below the lower endpoint — identical in method to
    `record_replay.air_segments`, reused here on just the candidate segment."""
    floor_z = flight[:, 2] - ES._floor_below(flight.astype(np.float32),
                                             depth=VOID_PROBE_U, step=8.0)
    return float(min(flight[0, 2], flight[-1, 2]) - floor_z.min())


def check(route: str, pos: np.ndarray, ground: np.ndarray,
          speed: np.ndarray | None = None) -> dict | None:
    """Did this trajectory perform the route's edge jump? ``None`` if the route carries no gate.

    Same spirit as `manoeuvres.executed()`: the takeoff and the landing are one event. The void
    requirement is checked on the candidate segments only, so the map probe runs on a handful of
    ticks, not the whole episode.
    """
    g = MANOEUVRE_GATES.get(route)
    if g is None:
        return None
    pos = np.asarray(pos, np.float32)
    ground = _strip_apex_blips(pos, np.asarray(ground, bool))
    if speed is None:
        speed = np.zeros(len(pos), np.float32)
    t = np.asarray(g["takeoff"], np.float64)
    # One route (`sng_to_quad`) has two legitimate landing points; a plain tuple is one anchor.
    l = np.atleast_2d(np.asarray(g["landing"], np.float64))

    best = None          # closest segment by worst anchor error, whatever its void
    executed = False
    for s in MA.airborne_segments(pos, ground, np.asarray(speed, np.float32), C.TICK_DT):
        d_t = float(np.linalg.norm(np.asarray(s["takeoff"]) - t))
        d_l = float(np.linalg.norm(np.asarray(s["landing"]) - l, axis=1).min())
        worst = max(d_t, d_l)
        cand = {"takeoff_err_u": round(d_t, 1), "landing_err_u": round(d_l, 1),
                "worst_u": round(worst, 1), "void_u": None, "at_tick": s["a"],
                "air_ticks": s["air_ticks"]}
        if d_t <= TOL_U and d_l <= TOL_U:
            cand["void_u"] = round(_void_u(pos[s["a"]:s["b"] + 1]), 1)
            if cand["void_u"] >= MIN_VOID_U:
                executed = True
                best = cand
                break
        if best is None or worst < best["worst_u"]:
            best = cand
    if best is None:
        return {"executed": False, "reason": "lämnade aldrig marken", "best": None}
    reason = "" if executed else (
        "närmaste luftsegment saknar tomrum under sig" if best["void_u"] is not None
        else "närmaste luftsegment startar eller landar för långt bort")
    return {"executed": bool(executed), "reason": reason, "best": best}
