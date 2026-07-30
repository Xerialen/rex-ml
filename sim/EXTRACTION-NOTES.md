# libqwsim — extraction notes

Batched, GIL-free, bit-exact QuakeWorld player-physics simulator, extracted
from `vendor/mvdsv-src/src/` (vendor tree untouched). Built 2026-07-30.

## 1. File provenance

### Byte-identical copies (physics path)

`sim/csrc/{pmove.c, pmove.h, pmovetst.c, cmodel.c, cmodel.h, mathlib.c,
mathlib.h, bspfile.h, md4.c}` are copies of the same-named files in
`vendor/mvdsv-src/src/`. Upstream sha256 of the originals are recorded in
`sim/csrc/UPSTREAM-SHA256.txt`. `diff` against vendor shows **exactly 8
changed lines and zero other differences** (verified 2026-07-30):

| # | file:line | original | change | reason |
|---|-----------|----------|--------|--------|
| 1 | pmove.c:30 | `playermove_t pmove;` | `__thread` added | per-OpenMP-thread pmove state so N slots step in parallel |
| 2 | pmove.c:32 | `static float pm_frametime;` | `__thread` added | same |
| 3 | pmove.c:34 | `static vec3_t pm_forward, pm_right;` | `__thread` added | same |
| 4 | pmove.c:36 | `static vec3_t groundnormal;` | `__thread` added | same |
| 5 | pmove.h:92 | `extern playermove_t pmove;` | `__thread` added | must match edit 1 |
| 6 | cmodel.c:99 | `static hull_t box_hull;` | `__thread` added | CM_HullForBox writes it per call; thread-local + per-thread `CM_Init()` |
| 7 | cmodel.c:100 | `static mclipnode_t box_clipnodes[6];` | `__thread` added | same |
| 8 | cmodel.c:101 | `static mplane_t box_planes[6];` | `__thread` added | same |

All are storage-class-only changes; no arithmetic, control flow or data
layout is touched. Single-threaded execution is semantically identical to
the original. Multi-thread determinism verified: 200 ticks x 1484 slots,
1 thread vs 64 threads, outputs **bitwise identical**.

`movevars` stays a shared global (read-only during stepping; the only write
inside pmove.c is the `ktjump > 1` clamp at pmove.c:733-734, which we never
trigger since ktjump is set ≤ 1).

### Shim files (new code, NOT from mvdsv — infrastructure only, no physics)

- `csrc/qwsvdef.h` — replaces the original include chain (bothdefs.h,
  mathlib.h, zone.h, cvar.h, common.h, fs.h, vfs.h, protocol.h). Every
  reproduced definition mirrors its mvdsv/qwprot original:
  - `qbool` = `enum { false, true }` (bothdefs.h:163), `byte`, `min/max/bound`
    (bothdefs.h:147-151), `MAX_QPATH/MAX_OSPATH` (bothdefs.h:40-41),
    `LittleShort/Long/Float` = identity (bothdefs.h:206-208, x86-64 LE).
  - `usercmd_t` and `BUTTON_*` verified against QW-Group/qwprot
    `src/protocol.h` master (the vendor tree's `qwprot/` submodule is empty);
    `MVD_PEXT1_WEAPONPREDICTION` is not defined, so the struct matches the
    8-field layout the server uses.
- `csrc/shim.c` — malloc-backed Hunk allocator (cmodel.c never relies on hunk
  contiguity; every lump is used via its own returned pointer), stdio VFS,
  cvar stubs (`sv_bspversion`, `sv_halflifebsp`, `pm_rampjump`),
  `Sys_Error` -> thread-local longjmp so BSP errors surface as Python
  exceptions, `COM_FileBase` reimplementation (only feeds hunk tag names).
- `csrc/qwsim_api.h`, `csrc/qwsim_core.c` — slot driver + batched ray API
  (see section 2).
- `qwsim_module.cpp` — pybind11 bindings; releases the GIL around
  `step_batch` / `trace_rays` / `reset` / `get_state`.

`.qpn` external physics-normal files and the BSPX `MVDSV_PHYSICSNORMALS`
lump: `FS_LoadHunkFile` returns NULL and dm3.bsp/100m.bsp carry no BSPX
lump, so physics normals fall back to the clipnode planes — identical to a
stock mvdsv install running these maps (checked: `CM_LoadPhysicsNormals`
default branch).

## 2. What the wrapper replicates from SV_RunCmd (sv_user.c)

`qwsim_step_one()` reproduces the per-command player path around the
untouched `PM_PlayerMove()` (sv_user.c:3777-3813):

- `pmove.origin = v->origin + (v->mins - player_mins)` — offset is zero for
  live players, so origin is copied directly.
- `cmd.angles[PITCH]` clamped to `[sv_minpitch, sv_maxpitch]` = **[-70, 80]**
  (sv_user.c:107-108, :3723).
- `pmove.jump_msec = 0` always (sv_user.c:3785; the pogo filter is
  client-prediction-only).
- KTeams "broken ankle" hack: `velocity[2] == -270 && (buttons & BUTTON_JUMP)`
  forces `jump_held = true` (sv_user.c:3786-3795, unconditional in mvdsv).
- `physents = { world }` only, `numphysent = 1`.
- movevars filled per sv_user.c:3803-3810.
- NOT replicated (out of scope, documented divergence sources):
  `SV_RunThink`/progs PreThink (KTX may touch velocity), `AddLinksToPmove`
  (doors/plats/players as physents), the `msec > 50` command chop (validation
  skips such cmds; RL env always uses msec ≤ 50), and the AM101
  anti-speedhack msec trimming (sv_user.c:3650-3680) — the server may run a
  cmd with a *smaller* msec than the client recorded, which is unobservable
  from the demo.

### Static world limitation

func_plat / func_door are server entities **outside pmove**; in the sim the
dm3 lift shafts contain no platform, so lift rides are non-functional (you
fall to the shaft floor). dm3's three func_plat travel volumes (from the BSP
entity + models lumps, used by the validator to classify divergences and to
be excluded from Gate-2 zones):

- plat *1: top (593,657,-291)-(655,719,-129), travel 154 u down
- plat *2: top (593,833,-127)-(655,895,-1), travel 118 u down
- plat *3: top (449,833,17)-(575,895,191), travel 166 u down
- teleporter triggers: (1169,-927,-15)-(1191,-881,15) and
  (-519,-471,1)-(-497,-425,47)

Teleport destinations, damage knockback and item pickups are likewise
server-side and absent.

## 3. Movevars locked for the RL environment

Source of truth: mvdsv defaults (sv_phys.c:46-66) — identical to the values
explicitly set in `~/mlx/qwserver/serverdir/rtx/dragonbot_rtx_27500.cfg`
(the A/B evaluation server). No other cfg in serverdir overrides them.

| var | value | | var | value |
|-----|-------|-|-----|-------|
| gravity | 800 | | friction | 4 |
| stopspeed | 100 | | waterfriction | 4 |
| maxspeed | 320 | | entgravity | 1.0 |
| spectatormaxspeed | 500 | | bunnyspeedcap | 0 |
| accelerate | 10 | | ktjump | 1 |
| airaccelerate | 10 | | slidefix / airstep / pground / rampjump | 0 |
| wateraccelerate | 10 | | | |

Note: `PM_AirMove` passes `movevars.accelerate` (not `airaccelerate`) to
`PM_AirAccelerate` (pmove.c:534) — the `sv_airaccelerate` cvar is dead for
player movement in this codebase; consistent with the corpus fit done
earlier in `pipeline/qwphys.py` (fitted air accel = 10.0).

**Tick rate:** mvdsv `sv_mintic` default 0.013 s ⇒ 77 Hz server frames, and
the server integrates the client's integer `msec` byte. QWD cmds carry
msec 12-14 (median 13). The RL environment default is **msec = 13**
(dt = 0.013 s exactly — the server never integrates 1/77 = 12.987 ms; it
integrates whole milliseconds).

## 4. Build

`sim/build.sh`: gcc/g++ -O2, **no -ffast-math**, `-ffp-contract=off` (no FMA
fusion) ⇒ strict IEEE-754 single precision, same arithmetic as a stock
x86-64 mvdsv build. No cmake on the machine; direct invocation. Python.h
comes from the uv-managed CPython 3.12.13 (system python3.12 has no -dev
headers; ABI tag cp312 matches the repo venv). Output:
`sim/qwsim.cpython-312-x86_64-linux-gnu.so`, importable with
`sys.path.insert(0, "~/rex-ml/sim")`.

## 5. Validation ground-truth findings (context for the numbers)

See `sim/validate_bitexact.py` and `evidence/libqwsim_bitexact.json`.

- In the QWD subset, only `wire_state_present` rows are ground truth. The QW
  wire quantises origin to **1/8 u** (`MSG_WriteCoord`, truncation toward 0)
  and velocity to **1 u/s** (short). Non-wire replay_ticks rows are the
  corpus parser's own forward-simulation (its `residual` column shows
  ~4.5 u exactly where its reconstruction slipped a tick) and are NOT used
  as truth.
- The wire state in a QWD frame lags the outgoing cmd stream by a variable
  0-12 cmds (network ack, jitter ±2); the validator matches each checkpoint
  against sim states 0-12 cmds back, preferring lag continuity, and reports
  the accepted-lag histogram per run.
- Segments are cut and re-seeded at events pmove cannot know about:
  damage knockback (velocity impulse), lift rides, teleports, water,
  seq breaks, plus a residue of near-threshold "other" cuts concentrated in
  a few high-ping demos (consistent with server-side AM101 msec trimming).
