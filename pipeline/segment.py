"""Trim / maneuver segmentation of SE(2)-reduced QuakeWorld tracks (BRIEF step 1).

Framing follows the maneuver automaton (Frazzoli/Dahleh/Feron), which is also
what BRIEF step 4 asks for:

  * a **trim** is a relative equilibrium of the symmetry-reduced dynamics --
    the shape variables (slip angle, turn rate) hold steady, so the world-frame
    motion is a helix/arc. A sustained strafejump and a sustained ground run are
    both trims.
  * a **maneuver** is a finite-time transition between trims. Takeoffs,
    landings and rocket-blast impulses are maneuvers.

Segment boundaries come from exactly the two signals BRIEF step 1 names --
ground contact and weapon fire -- plus the impulse test that tells a rocket
blast apart from a plain jump.

Ground contact is *derived*, not read off `replay_ticks.onground`. Measured on
store-dm3, 53 % of ticks flagged `onground = false` have `vz == 0` and no change
in z, i.e. the player is standing still on a floor. The flag is a subset of true
ground contact, so it is OR-ed in but never trusted alone.
"""

from __future__ import annotations

import numpy as np

from . import config as C

# --------------------------------------------------------------------------
# state / label vocabularies
# --------------------------------------------------------------------------

GROUND, AIR, WATER = 0, 1, 2
STATE_NAMES = ("ground", "air", "water")

KINDS = (
    "trim_ground",
    "trim_air",
    "maneuver_jump",
    "maneuver_rocket_jump",
    # An impulse the POV usercmd stream cannot attribute to the recorder's own
    # attack: enemy splash damage, lifts, teleporters, trigger_push. Only one
    # slot per demo has usercmds (AUDIT), so these are unattributable by
    # construction, not by a gap in the classifier.
    "maneuver_external",
    "maneuver_fall",
    "maneuver_land",
    "other_ground",
    "other_air",
    "water",
)
KIND_ID = {k: i for i, k in enumerate(KINDS)}


# --------------------------------------------------------------------------
# run-length utilities
# --------------------------------------------------------------------------

def runs_of(v: np.ndarray, breaks: np.ndarray | None = None):
    """Maximal runs of equal values. Returns (starts, ends_exclusive, values).

    `breaks[i] == True` forces a boundary between i-1 and i.
    """
    n = len(v)
    if n == 0:
        return (np.empty(0, np.int64),) * 2 + (np.empty(0, v.dtype),)
    new = np.empty(n, dtype=bool)
    new[0] = True
    new[1:] = v[1:] != v[:-1]
    if breaks is not None:
        new |= breaks
    starts = np.flatnonzero(new).astype(np.int64)
    ends = np.append(starts[1:], n)
    return starts, ends, v[starts]


def chunk_breaks(f: dict) -> np.ndarray:
    """True at index i when i starts a new contiguous chunk.

    A chunk breaks on a track change, a cmd_ordinal gap, a seq_break, or a
    usercmd frametime outside the sane range.
    """
    n = len(f["cmd_ordinal"])
    b = np.zeros(n, dtype=bool)
    b[0] = True
    if n > 1:
        b[1:] = ~f["has_next"][:-1]
    b |= f["seq_break"]
    msec = f["msec"].astype(np.int32)
    b |= (msec < C.THRESHOLDS.msec_min) | (msec > C.THRESHOLDS.msec_max)
    return b


# --------------------------------------------------------------------------
# ground contact
# --------------------------------------------------------------------------

def derive_state(f: dict, th: C.Thresholds = C.THRESHOLDS):
    """Per-tick {ground, air, water}, plus the raw (undebounced) ground signal.

    Support test: a supported player has vz exactly 0 -- QW zeroes the vertical
    velocity on contact and gravity is the only vertical force otherwise, so a
    free-falling tick has vz == 0 only at the apex. The apex is excluded by
    requiring that the previous tick was not moving upward. `onground` is OR-ed
    in to catch slope contacts where vz != 0.
    """
    vz = f["vz"]
    prv = np.empty(len(vz), dtype=np.int64)
    prv[0] = 0
    prv[1:] = np.arange(len(vz) - 1)
    prev_up = np.zeros(len(vz), dtype=bool)
    prev_up[1:] = (vz[:-1] > th.vz_zero_eps) & f["has_prev"][1:]

    supported = (np.abs(vz) <= th.vz_zero_eps) & ~prev_up
    ground_raw = supported | f["onground_flag"]

    state = np.where(ground_raw, GROUND, AIR).astype(np.int8)
    state[f["waterlevel"] > 0] = WATER

    breaks = chunk_breaks(f)
    state_deb = _debounce(state, breaks, th)
    return state_deb, ground_raw, state


def _debounce(state: np.ndarray, breaks: np.ndarray, th: C.Thresholds) -> np.ndarray:
    """Absorb runs shorter than the per-state minimum into the previous run.

    Ground contact in QW genuinely flickers on stairs and ramps; without this a
    single stair step reads as a jump.
    """
    out = state.copy()
    minlen = {GROUND: th.min_ground_run, AIR: th.min_air_run, WATER: 1}
    for _ in range(4):  # converges fast; bounded so it cannot spin
        s, e, v = runs_of(out, breaks)
        short = (e - s) < np.array([minlen[int(x)] for x in v])
        short[0] = False  # nothing to the left to absorb into
        short &= ~breaks[s]  # do not merge across a chunk boundary
        if not short.any():
            break
        for i in np.flatnonzero(short):
            out[s[i]:e[i]] = out[s[i] - 1]
    return out


# --------------------------------------------------------------------------
# events
# --------------------------------------------------------------------------

def detect_events(f: dict, state: np.ndarray, th: C.Thresholds = C.THRESHOLDS):
    """Rising edges and impulses. All are indexed by tick.

    `impulse` is attached to tick i and describes the transition i -> i+1: it is
    True when the observed velocity change cannot be produced by gravity plus
    QW's capped air acceleration. Only air->air transitions are tested; ground
    contact legitimately absorbs velocity.
    """
    n = len(state)
    breaks = chunk_breaks(f)
    first = breaks.copy()

    attack = f["attack"]
    fire_edge = np.zeros(n, dtype=bool)
    fire_edge[1:] = attack[1:] & ~attack[:-1]
    fire_edge |= attack & first

    jb = f["jump_btn"]
    jump_edge = np.zeros(n, dtype=bool)
    jump_edge[1:] = jb[1:] & ~jb[:-1]
    jump_edge |= jb & first

    nxt_air = np.zeros(n, dtype=bool)
    nxt_air[:-1] = state[1:] == AIR
    air_to_air = (state == AIR) & nxt_air & f["has_next"]

    grav_res = np.nan_to_num(f["grav_res"], nan=0.0)
    dv_xy = np.nan_to_num(f["dv_xy"], nan=0.0)
    impulse = air_to_air & ((np.abs(grav_res) > th.impulse_dvz) | (dv_xy > th.impulse_dvxy))
    impulse_mag = np.hypot(np.nan_to_num(f["dv_xy"], nan=0.0),
                           np.nan_to_num(f["grav_res"], nan=0.0))

    # transitions, indexed at the tick *after* the change
    takeoff = np.zeros(n, dtype=bool)
    land = np.zeros(n, dtype=bool)
    if n > 1:
        same = ~breaks[1:]
        takeoff[1:] = same & (state[1:] == AIR) & (state[:-1] == GROUND)
        land[1:] = same & (state[1:] == GROUND) & (state[:-1] == AIR)

    return dict(fire_edge=fire_edge, jump_edge=jump_edge, impulse=impulse,
                impulse_mag=impulse_mag, takeoff=takeoff, land=land, breaks=breaks)


def _fire_near(fire_edge: np.ndarray, idx: int, before: int, after: int,
               lo: int, hi: int) -> bool:
    a = max(lo, idx - before)
    b = min(hi, idx + after + 1)
    return bool(fire_edge[a:b].any()) if b > a else False


def is_self_blast(f, ev, j: int, clo: int, chi: int,
                  th: C.Thresholds = C.THRESHOLDS) -> bool:
    """Is the impulse at transition j the recorder's own rocket jump?

    Three conditions, all measured to matter (see analyze_rocket.py):
      1. magnitude above what gravity + capped air-accel can produce,
      2. the blast pushes *up* -- that is what makes it a jump rather than a
         sideways knock from someone else's rocket,
      3. the recorder pulled the trigger a few ticks earlier while aiming at the
         floor. Both halves are needed: fire alone gives 1.4x lift over a
         shifted-fire null, fire + up + look-down gives 5.3x.
    """
    mag = float(ev["impulse_mag"][j])
    if mag < th.rocket_impulse_min:
        return False
    up = float(np.nan_to_num(f["grav_res"][j], nan=0.0)) / max(mag, 1e-9)
    if up < th.rocket_up_min:
        return False
    if f["pitch_deg"][j] < th.rocket_pitch_min:
        return False
    return _fire_near(ev["fire_edge"], j, th.fire_window_before,
                      th.fire_window_after, clo, chi)


# --------------------------------------------------------------------------
# trim scan
# --------------------------------------------------------------------------

def _scan_trims(f, slip_u, lo, hi, blocked, th):
    """Greedy maximal quasi-steady windows in [lo, hi). Returns list of (a, b)."""
    out = []
    i = lo
    speed = f["speed_xy"]
    omega = f["omega_prev"]
    while i < hi:
        if blocked[i] or speed[i] < th.trim_min_speed or not np.isfinite(omega[i]):
            i += 1
            continue
        s_lo = s_hi = slip_u[i]
        o_lo = o_hi = omega[i]
        v0 = speed[i]
        j = i + 1
        while j < hi and not blocked[j]:
            if speed[j] < th.trim_min_speed or not np.isfinite(omega[j]):
                break
            ns_lo, ns_hi = min(s_lo, slip_u[j]), max(s_hi, slip_u[j])
            no_lo, no_hi = min(o_lo, omega[j]), max(o_hi, omega[j])
            if ns_hi - ns_lo > 2 * th.trim_phi_tol:
                break
            if no_hi - no_lo > 2 * th.trim_omega_tol:
                break
            if abs(speed[j] / v0 - 1.0) > th.trim_speed_rel_tol:
                break
            s_lo, s_hi, o_lo, o_hi = ns_lo, ns_hi, no_lo, no_hi
            j += 1
        if j - i >= th.trim_min_len:
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


# --------------------------------------------------------------------------
# main segmentation
# --------------------------------------------------------------------------

def segment(f: dict, th: C.Thresholds = C.THRESHOLDS):
    """Label every tick and return (kind_code_per_tick, seg_id_per_tick, segments).

    `segments` is a dict of arrays, one row per segment.
    """
    n = len(f["cmd_ordinal"])
    state, ground_raw, state_raw = derive_state(f, th)
    ev = detect_events(f, state, th)
    breaks = ev["breaks"]

    kind = np.empty(n, dtype=np.int8)
    kind[:] = KIND_ID["other_air"]
    kind[state == GROUND] = KIND_ID["other_ground"]
    kind[state == WATER] = KIND_ID["water"]

    painted = np.zeros(n, dtype=bool)   # maneuver ticks, not eligible for trims
    dvz = np.nan_to_num(f["dvz"], nan=0.0)
    dv_xy = np.nan_to_num(f["dv_xy"], nan=0.0)
    imag = ev["impulse_mag"]
    pad = th.maneuver_pad

    # chunk boundaries so no window spans a discontinuity
    cs, ce, _ = runs_of(np.zeros(n, dtype=np.int8), breaks)

    s_st, e_st, v_st = runs_of(state, breaks)
    # chunk index of each state run
    chunk_of = np.searchsorted(cs, s_st, side="right") - 1

    for k in range(len(s_st)):
        s, e, st = int(s_st[k]), int(e_st[k]), int(v_st[k])
        clo, chi = int(cs[chunk_of[k]]), int(ce[chunk_of[k]])
        if st == WATER:
            painted[s:e] = True
            continue

        if st == AIR:
            # --- takeoff maneuver -------------------------------------
            if s > clo:                      # there is a preceding tick in-chunk
                tdvz = float(dvz[s - 1])
                tmag = float(imag[s - 1])
                if is_self_blast(f, ev, s - 1, clo, chi, th):
                    lab = "maneuver_rocket_jump"
                elif th.jump_dvz_lo <= tdvz <= th.jump_dvz_hi:
                    lab = "maneuver_jump"
                elif tdvz > th.jump_dvz_hi or tmag >= th.rocket_impulse_min:
                    lab = "maneuver_external"
                else:
                    lab = "maneuver_fall"
                b = min(e, s + max(1, pad))
                kind[s:b] = KIND_ID[lab]
                painted[s:b] = True

            # --- mid-air blasts ---------------------------------------
            for j in np.flatnonzero(ev["impulse"][s:e]) + s:
                if imag[j] < th.rocket_impulse_min:
                    continue
                lab = ("maneuver_rocket_jump"
                       if is_self_blast(f, ev, int(j), clo, chi, th)
                       else "maneuver_external")
                a = max(s, j - pad + 1)
                b = min(e, j + pad + 1)
                kind[a:b] = KIND_ID[lab]
                painted[a:b] = True
        else:
            # --- landing maneuver at the head of a ground run ----------
            if s > clo and state[s - 1] == AIR:
                b = min(e, s + max(1, pad))
                kind[s:b] = KIND_ID["maneuver_land"]
                painted[s:b] = True

        # --- weapon fire always breaks a trim -------------------------
        for j in np.flatnonzero(ev["fire_edge"][s:e]) + s:
            painted[j] = True

    # --- trims in the unpainted interior of each state run -------------
    slip_u = _unwrap_chunked(f["slip"], breaks)
    for k in range(len(s_st)):
        s, e, st = int(s_st[k]), int(e_st[k]), int(v_st[k])
        if st == WATER or e - s < th.trim_min_len:
            continue
        lab = KIND_ID["trim_ground"] if st == GROUND else KIND_ID["trim_air"]
        for a, b in _scan_trims(f, slip_u, s, e, painted, th):
            kind[a:b] = lab

    seg_id, segs = _collect(f, kind, state, ev, breaks, th)

    # state-run bookkeeping: lets a consumer ask "which air phase is this
    # maneuver part of", which is the physically meaningful unit for a jump.
    state_run_id = np.repeat(np.arange(len(s_st), dtype=np.int32), e_st - s_st)
    last_st = np.maximum(e_st - 1, s_st)
    state_runs = dict(
        run_id=np.arange(len(s_st), dtype=np.int32),
        state=np.array([STATE_NAMES[int(v)] for v in v_st], dtype=object),
        i0=s_st, i1=last_st, n_ticks=(e_st - s_st).astype(np.int32),
        dur_ms=np.array([float(f["dt"][a:b].sum() * 1000.0) for a, b in zip(s_st, e_st)]),
        z0=f["z"][s_st], z_peak=np.array([float(f["z"][a:b].max()) for a, b in zip(s_st, e_st)]),
        z1=f["z"][last_st],
        speed0=f["speed_xy"][s_st], speed1=f["speed_xy"][last_st],
        speed_peak=np.array([float(f["speed_xy"][a:b].max()) for a, b in zip(s_st, e_st)]),
        planar_dist=np.hypot(f["x"][last_st] - f["x"][s_st], f["y"][last_st] - f["y"][s_st]),
    )
    return dict(state=state, ground_raw=ground_raw, state_raw=state_raw,
                kind=kind, seg_id=seg_id, events=ev, segments=segs,
                state_run_id=state_run_id, state_runs=state_runs)


def _unwrap_chunked(a: np.ndarray, breaks: np.ndarray) -> np.ndarray:
    out = a.copy()
    s, e, _ = runs_of(np.zeros(len(a), dtype=np.int8), breaks)
    for i in range(len(s)):
        sl = slice(int(s[i]), int(e[i]))
        out[sl] = np.unwrap(a[sl])
    return out


def _nanmean(a: np.ndarray) -> float:
    m = np.isfinite(a)
    return float(a[m].mean()) if m.any() else float("nan")


def _span(a: np.ndarray) -> float:
    """Peak-to-peak of an angle sequence, unwrapped *within the window only*."""
    m = np.isfinite(a)
    if m.sum() < 2:
        return 0.0
    u = np.unwrap(a[m])
    return float(u.max() - u.min())


def _collect(f, kind, state, ev, breaks, th):
    """Group contiguous equal labels into segment records."""
    n = len(kind)
    s, e, v = runs_of(kind, breaks | (np.append(True, state[1:] != state[:-1])))
    seg_id = np.repeat(np.arange(len(s), dtype=np.int32), e - s)

    last = np.maximum(e - 1, s)
    dt = f["dt"]
    dur = np.array([float(dt[a:b].sum() * 1000.0) for a, b in zip(s, e)])
    fire_n = np.array([int(ev["fire_edge"][a:b].sum()) for a, b in zip(s, e)])
    imp_n = np.array([int(ev["impulse"][a:b].sum()) for a, b in zip(s, e)])
    peak = np.array([float(np.nanmax(ev["impulse_mag"][a:b])) if b > a else 0.0
                     for a, b in zip(s, e)])
    # circular mean -- slip lives on a circle, an arithmetic mean of unwrapped
    # values accumulates whole turns and reports nonsense like +5722 deg
    cs_, sn_ = np.cos(f["slip"]), np.sin(f["slip"])
    mean_slip = np.array([np.arctan2(_nanmean(sn_[a:b]), _nanmean(cs_[a:b]))
                          for a, b in zip(s, e)])
    slip_span = np.array([_span(f["slip"][a:b]) for a, b in zip(s, e)])
    mean_omega = np.array([_nanmean(f["omega_prev"][a:b]) for a, b in zip(s, e)])
    dxy = np.hypot(f["x"][last] - f["x"][s], f["y"][last] - f["y"][s])

    segs = dict(
        seg_id=np.arange(len(s), dtype=np.int32),
        demo_key=f["demo_key"][s], slot=f["slot"][s],
        kind=np.array([KINDS[i] for i in v], dtype=object),
        state=np.array([STATE_NAMES[i] for i in state[s]], dtype=object),
        i0=s.astype(np.int64), i1=last.astype(np.int64),
        o0=f["cmd_ordinal"][s], o1=f["cmd_ordinal"][last],
        t0=f["t"][s], t1=f["t"][last],
        n_ticks=(e - s).astype(np.int32), dur_ms=dur,
        speed0=f["speed_xy"][s], speed1=f["speed_xy"][last],
        dspeed=f["speed_xy"][last] - f["speed_xy"][s],
        z0=f["z"][s], z1=f["z"][last], dz_total=f["z"][last] - f["z"][s],
        planar_dist=dxy,
        mean_slip=mean_slip, slip_span=slip_span, mean_omega=mean_omega,
        n_fire=fire_n, n_impulse=imp_n, peak_impulse=peak,
        wire_frac=np.array([float(f["wire_state_present"][a:b].mean()) for a, b in zip(s, e)]),
    )
    if "split" in f:
        segs["split"] = f["split"][s]
    return seg_id, segs
