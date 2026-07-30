"""The owner's eight DM3 cohort routes — the route set the median gates were measured on.

This is deliberately a **second, separate** route set from `ppo.load_goto_scenarios()`, which reads
`~/rtx-mltest/testsuite/scenarios/dm3/*.toml`. The two must never be mixed:

  * the **cohort routes** (this file) carry the owner's event bindings and are the set the human
    medians in `route-lab` were computed over, so they are the only set whose times may be compared
    against those medians;
  * the **suite scenarios** are the T1 contract for phase 3 and have different endpoints — the
    suite's `window_to_rl` target sits ~161 u *past* the rocket launcher, which is a different
    journey, not a rounding difference.

Endpoints are the items' own origins, taken from the corpus (`store-dm3/item_events`, counts in the
table below) after the owner fixed them on 2026-07-29: "ratop = exakt där itemet RA ligger. RL =
exakt där RL ligger." Start points come from `route-lab`'s registry
(`route_lab/routes_dm3.json`) — the same bindings the medians were measured with — resolved to
concrete coordinates here:

  * `spawn` starts are already exact coordinates in the registry;
  * `item` starts resolve to that item's corpus origin (a pickup happens at the item);
  * the one `crossing` start (lifts hole) resolves to the centre of its XY box at the plane's z.

Item origins used, with the number of corpus events backing each — none of these are guesses:

    ra    (256, -704,  304)   186 702
    rl    (1520,  496, -112)  165 516
    quad  (952,   296,   56)   82 715
    mh    (-720,   80,  160)   75 752   (the SNG mega; dm3 has three megas, this is the one the
                                         registry pins by origin)
    ring  (240,   -32,   56)   16 838
    ng    (-64,  -704,  -40)   88 452

The gates are route-lab's **median without combat** — the owner's first gate — from the calibration
table in PROGRESS.md. The owner's acceptance band, set 2026-07-29: take the median, the best time,
or better; **at most 2.0 s worse than the median**.
"""

from __future__ import annotations

from dataclasses import dataclass

TICK_DT = 1.0 / 77.0   # the game's tick; see rex-env::TICK_DT

# An item's corpus origin is its resting point on the floor; a player standing on that spot has his
# origin 24 u higher, because QuakeWorld's player hull is (-16,-16,-24)-(16,16,32) around the origin.
# The map confirms the offset independently: the owner's own suite puts `ratop` at z = 328 = 304 + 24
# and the RL target at z = -88 = -112 + 24. Route endpoints are *places a player stands*, so every
# item origin below is lifted by this before it is handed to `Route::planned` — at z + 0 the RA, RL,
# mega and NG all fail to snap onto the navmesh, which is the same fact stated by the mesh.
PLAYER_ORIGIN_DZ = 24.0


def _at(x: float, y: float, z: float) -> tuple[float, float, float]:
    return (x, y, z + PLAYER_ORIGIN_DZ)


# item origins from ~/dm3-extract/store-dm3/item_events (see module docstring for event counts)
RA = _at(256.0, -704.0, 304.0)
RL = _at(1520.0, 496.0, -112.0)
QUAD = _at(952.0, 296.0, 56.0)
MH_SNG = _at(-720.0, 80.0, 160.0)
RING = _at(240.0, -32.0, 56.0)
NG = _at(-64.0, -704.0, -40.0)

# The band the owner set: median + this many seconds is still a pass.
TOLERANCE_S = 2.0

# The live server's own arrival gate (`rtx-game/src/control.rs`: GOTO_ARRIVE_XY = 24,
# GOTO_ARRIVE_Z = 48), not the 70 u `arrive_box` in the scenario files.
#
# Corrected 2026-07-29 after the owner asked whether vertical position is actually being checked.
# It is — in both places — but the environment's gate was 70 u horizontal and 64 u vertical while
# the server's is 24 and 48, and the difference is not academic. Measured over 460 arrivals across
# all seven routes: the horizontal offset at arrival was 71-74 u on every one of them, and the
# vertical offset reached 57 u on `window_to_rl` and 58 u on `ralow_to_ratop`. **Every single
# arrival would have been rejected by the live server.** A policy optimises to the edge of the box
# it is given; a loose box does not produce slightly optimistic times, it produces times that do
# not reproduce at all where the proof has to come from.
#
# Worth stating plainly for the report: 24 u is also *stricter* than a real item pickup, so a route
# finished under this gate is finished under the pickup rule too.
ARRIVE_BOX = 24.0
ARRIVE_Z = 48.0


@dataclass(frozen=True)
class CohortRoute:
    name: str
    start: tuple[float, float, float]
    target: tuple[float, float, float]
    gate_s: float            # route-lab median without combat — the gate
    owner_s: float | None    # the owner's own recorded time, when he has one
    median_all_s: float      # route-lab median including combat, for context
    n_cohort: int            # how many human runs the median is over
    timeout_s: float
    note: str = ""

    @property
    def max_ticks(self) -> int:
        return int(self.timeout_s / TICK_DT) + 50

    @property
    def pass_s(self) -> float:
        return self.gate_s + TOLERANCE_S


def _t(gate: float) -> float:
    """Episode budget: generous enough that a slow-but-arriving policy still registers as an
    arrival (which is information) rather than as a timeout (which is not), capped at the suite's
    own 20 s so no single route dominates a rollout."""
    return min(20.0, gate + 8.0)


ROUTES: list[CohortRoute] = [
    # GATE CORRECTED 2026-07-29, and flagged to the owner rather than changed quietly. His +1.0 s
    # adjustment was for a *target that sat 161 u short of the rocket launcher* — the suite's target.
    # The cohort median is not measured against that target: route-lab binds the end of the run to
    # the `rl` **pickup event**, so 2.75 s is already the time to reach the actual item, and adding
    # a second on top would hand the bot a gate a full second easier than the human data supports.
    # Confirmed directly: every run pulled by `human_paths.py` ends at `pickup_t`. The owner's own
    # 3.49 s keeps the adjustment, because *his* recorded run really did stop short.
    CohortRoute("window_to_rl", (1328.0, 540.0, 71.0), RL,
                gate_s=2.75, owner_s=3.49, median_all_s=2.86, n_cohort=1360, timeout_s=_t(3.75),
                note="Start is a 'near' binding (r=64) — the loosest in the registry, by the owner's "
                     "choice. Human runs here are rocket-jump-free: max rise over any half second is "
                     "~40 u across the fastest 120, against 45.5 u for a plain jump. They average "
                     "465-645 u/s over a 1150-1350 u path."),
    CohortRoute("sngspawn_a_to_quad", (-880.0, -232.0, -16.0), QUAD,
                gate_s=4.27, owner_s=None, median_all_s=4.30, n_cohort=128, timeout_s=_t(4.27),
                note="registry binds two SNG-tele spawns; the human median pools both, so both are "
                     "built and the pooled median is what gates."),
    CohortRoute("sngspawn_b_to_quad", (-632.0, -680.0, -16.0), QUAD,
                gate_s=4.27, owner_s=None, median_all_s=4.30, n_cohort=128, timeout_s=_t(4.27)),
    CohortRoute("ralow_to_ratop", NG, RA,
                gate_s=7.71, owner_s=7.48, median_all_s=8.04, n_cohort=3100, timeout_s=_t(7.71),
                note="start bound to the nailgun take at RA-low."),
    # z = 182, not the registry's plane z = 190: the crossing plane sits just above the floor and
    # 190 does not snap, 182 does. The 8 u is the mesh telling us where the standing surface is.
    CohortRoute("lifts_to_sng_mega", (508.0, 610.0, 182.0), MH_SNG,
                gate_s=7.93, owner_s=None, median_all_s=8.29, n_cohort=8071, timeout_s=_t(7.93),
                note="KNOWN DEVIATION: the registry start is a downward crossing of z=190 inside "
                     "the lifts hole, i.e. the human is falling with speed. This env starts at rest "
                     "on whatever floor the navmesh snaps to, which is not the same initial state."),
    CohortRoute("quad_to_ra", QUAD, RA,
                gate_s=8.96, owner_s=None, median_all_s=10.41, n_cohort=2286, timeout_s=_t(8.96)),
    CohortRoute("ring_to_ratop", RING, RA,
                gate_s=9.26, owner_s=6.97, median_all_s=10.14, n_cohort=1322, timeout_s=_t(9.26)),
    CohortRoute("sngspawn_a_to_mega", (-880.0, -232.0, -16.0), MH_SNG,
                gate_s=9.98, owner_s=7.38, median_all_s=10.49, n_cohort=875, timeout_s=_t(9.98)),
    CohortRoute("sngspawn_b_to_mega", (-632.0, -680.0, -16.0), MH_SNG,
                gate_s=9.98, owner_s=7.38, median_all_s=10.49, n_cohort=875, timeout_s=_t(9.98)),
    CohortRoute("tunnel_to_ra", (192.0, -208.0, -176.0), RA,
                gate_s=12.13, owner_s=None, median_all_s=12.52, n_cohort=239, timeout_s=_t(12.13)),
]

# Routes that share one human median because the registry pools their start points. Reported
# individually and gated on the pooled median, the same way the human number was formed.
POOLED = {
    "sngspawn_to_quad": ("sngspawn_a_to_quad", "sngspawn_b_to_quad"),
    "sngspawn_to_mega": ("sngspawn_a_to_mega", "sngspawn_b_to_mega"),
}

BY_NAME = {r.name: r for r in ROUTES}
