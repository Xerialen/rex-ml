"""Record every attempt the ML policy makes, tick by tick, for the replay page.

One row per server tick per attempt: world position, view yaw, ground state, jump input. That is
everything a 1:1 replay needs — the page advances one row every `TICK_DT` = 14 ms, which is the same
clock the physics ran on, so the playback speed *is* the game speed rather than an approximation of
it.

Two decode modes are recorded per route, and they are different measurements, not two samples of
one:

  * **greedy** — the shipped decision rule (argmax on the discrete heads, the mean of the steering
    distribution). This is what `race eval` grades. From a fixed start it is deterministic, so all
    64 episodes are one trajectory; the recorder verifies that rather than assuming it, and stores
    the distinct ones with their counts.
  * **sampled** — the policy's own distribution. This is where the spread lives, and spread is the
    thing the owner's brief calls the bot's real problem. A page that showed only the greedy line
    would show a bot that never varies, which is an artefact of the decode rule and not a property
    of the policy.

Nothing here is reconstructed or smoothed. The positions are read out of the environment between
`step` calls, so they are the same numbers the arrival test was applied to.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import numpy as np
import torch

from . import cohort_routes as C
from . import race
from .ppo import PPOActorCritic, actions_to_env, obs_to_state

OUT = Path("/home/benjamin-adm/rex-ml/pipeline/out/replay")
TICK_DT = C.TICK_DT


# Two plain jumps' worth of height. Below this a player who lands short can jump back out and has
# lost time; past it the miss puts them on another level entirely, which is what makes the jump
# critical rather than merely long.
VOID_U = 96.0
# Deeper than dm3's deepest pit (the RL chasm floors at -392, some 370 u under its ledges), so the
# probe never reports its own reach as solid ground.
VOID_PROBE_U = 512.0


def air_segments(frames: list[tuple]) -> list[dict]:
    """Each airborne stretch of a run, measured — so the page can point at a jump instead of
    asserting one.

    **What the first version of this got wrong** (2026-07-29, corrected on the owner's objection):
    it classified purely by reach — did the stretch cover more ground than the takeoff speed carries
    through a plain jump's 0.675 s hang. By that test the reference demo's jump onto the RL box's
    window ledge, 144 u from (1446, 58, -24) up to (1546, 161, +20), came out as an ordinary hop,
    because 144 u is well inside the 322 u a plain jump reaches on flat ground. The floor under that
    flight is at -392. Reach is the wrong question when missing costs a 400 u fall.

    So the first question asked here is what is *underneath*: `void_u` is how far the floor along the
    flight path drops below the lower of the two endpoints. Past [`VOID_U`] a miss does not cost time,
    it drops the player onto a different level — that is a gap jump whatever its length, and one that
    also gains height is harder still. Only where there is no void do the older, weaker distinctions
    apply: a stretch longer than its own takeoff speed carries, or a plain descent.
    """
    import numpy as np

    from . import manoeuvres as MA

    from . import edge_signal as ES

    a = np.asarray([(f[0], f[1], f[2]) for f in frames], np.float32)
    ground = np.asarray([f[4] for f in frames], np.float32)
    speed = np.asarray([f[6] for f in frames], np.float32)
    out = []
    for s in MA.airborne_segments(a, ground, speed, TICK_DT):
        p0, p1 = np.asarray(s["takeoff"], np.float32), np.asarray(s["landing"], np.float32)
        gap = float(np.linalg.norm(p1[:2] - p0[:2]))
        dz = float(p1[2] - p0[2])
        flight = a[s["a"]:s["b"] + 1]
        rise = float(flight[:, 2].max() - p0[2])
        reach = float(s["takeoff_speed"]) * MA.PLAIN_JUMP_HANG_S
        # How far the floor along the flight drops below the lower of the two landing surfaces.
        # `VOID_PROBE_U` has to reach past the deepest pit on dm3 or the probe reports its own limit
        # as the floor and a chasm reads as solid ground.
        floor_z = flight[:, 2] - ES._floor_below(flight.astype(np.float32),
                                                 depth=VOID_PROBE_U, step=8.0)
        void = float(min(p0[2], p1[2]) - floor_z.min())
        if void >= VOID_U:
            kind = "gap_up" if dz > 0 else "gap"
        elif gap > reach * MA.REACH_MARGIN:
            kind = "carried"
        elif dz < -MA.PLAIN_JUMP_RISE_U:
            kind = "descent"
        else:
            kind = "hop"
        out.append({"a": int(s["a"]), "b": int(s["b"]), "air_s": round(s["air_s"], 3),
                    "gap_u": round(gap, 1), "dz_u": round(dz, 1), "rise_u": round(rise, 1),
                    "void_u": round(void, 1),
                    "takeoff_ups": round(float(s["takeoff_speed"])),
                    "peak_ups": round(float(s["peak_speed"])),
                    "plain_reach_u": round(reach, 1), "kind": kind})
    return out


def record_route(ac, route: C.CohortRoute, n: int, greedy: bool, human_path: dict | None,
                 dev: str = "cuda") -> dict:
    import rex_env
    if human_path is not None:
        env = rex_env.PyVecEnv.from_path(race.MAP, [tuple(p) for p in human_path["path"]], n,
                                         C.ARRIVE_BOX, route.max_ticks)
        geometry = f"human:{human_path['demo_key']}@{human_path['duration_s']}"
    else:
        env = rex_env.PyVecEnv(race.MAP, route.start, route.target, n, C.ARRIVE_BOX, route.max_ticks)
        geometry = "navmesh"
    path = env.path
    obs = env.reset()

    done = np.zeros(n, dtype=bool)
    ticks = np.zeros(n, dtype=np.int64)
    outcome = np.array(["unfinished"] * n, dtype=object)
    wall = np.zeros(n, dtype=bool)
    frames: list[list[tuple]] = [[] for _ in range(n)]

    for _ in range(route.max_ticks + 2):
        obs_t = obs_to_state(obs, torch, dev)
        with torch.no_grad():
            if greedy:
                f_l, s_l, yaw, j_l = ac.actor(obs_t)
                ac_tuple = (f_l.argmax(-1), s_l.argmax(-1), yaw.squeeze(-1),
                            (j_l.squeeze(-1) > 0).float())
            else:
                ac_tuple, _, _, _ = ac.act(obs_t)
        acts = actions_to_env(ac_tuple)

        P = env.origins
        V = env.velocities
        Y = env.view_yaws
        G = env.on_ground
        live = np.flatnonzero(~done)
        for i in live:
            frames[i].append((float(P[i, 0]), float(P[i, 1]), float(P[i, 2]),
                              float(Y[i]), float(G[i]) > 0.5, bool(acts[i, 3] > 0.5),
                              float(np.hypot(V[i, 0], V[i, 1]))))
        ticks[live] += 1

        obs, parts, dones = env.step(acts)
        parts = np.asarray(parts)
        wall[live] |= parts[live, 2] < 0
        just = np.flatnonzero((~done) & np.asarray(dones))
        if len(just):
            # The tick the episode *ended* on, read from the environment's own kept copy rather
            # than from `origins` — which the auto-reset has already advanced to the next episode's
            # start. Without this the replay stops one tick short of the goal and shows a bot that
            # never quite arrives, which is what the first recording did.
            T = env.terminal_states
            for i in just:
                done[i] = True
                outcome[i] = ("arrived" if parts[i, 4] > 0
                              else ("timeout" if parts[i, 3] < 0 else "void"))
                if T[i, 4] >= 0:
                    frames[i].append((float(T[i, 0]), float(T[i, 1]), float(T[i, 2]),
                                      float(T[i, 3]), T[i, 4] > 0.5, bool(acts[i, 3] > 0.5),
                                      float(T[i, 5])))
                    ticks[i] += 1
        if done.all():
            break

    # Distinct trajectories, so 64 identical greedy runs are stored once and *reported* as 64.
    groups: dict[bytes, dict] = {}
    for i in range(n):
        arr = np.asarray([fr[:4] for fr in frames[i]], dtype=np.float32)
        key = arr.tobytes()
        g = groups.setdefault(key, {"attempts": [], "frames": frames[i]})
        g["attempts"].append(i)

    runs = []
    for g in groups.values():
        i = g["attempts"][0]
        runs.append({
            "count": len(g["attempts"]),
            "attempt_ids": g["attempts"],
            "outcome": outcome[i],
            "ticks": int(ticks[i]),
            "time_s": round(float(ticks[i]) * TICK_DT, 3),
            "wall_contact": bool(wall[i]),
            "segments": air_segments(g["frames"]),
            "frames": g["frames"],
        })
    runs.sort(key=lambda r: (r["outcome"] != "arrived", r["time_s"]))

    arrived = outcome == "arrived"
    return {
        "route": route.name,
        "geometry": geometry,
        "decode": "greedy" if greedy else "sampled",
        "attempts": n,
        "distinct_trajectories": len(runs),
        "arrival_rate": float(arrived.mean()),
        "median_s": float(np.median(ticks[arrived]) * TICK_DT) if arrived.any() else None,
        "best_s": float(ticks[arrived].min() * TICK_DT) if arrived.any() else None,
        "worst_s": float(ticks[arrived].max() * TICK_DT) if arrived.any() else None,
        "wall_contact_attempts": int(wall.sum()),
        "gate_s": route.gate_s,
        "pass_s": route.pass_s,
        "owner_s": route.owner_s,
        "start": [round(v, 1) for v in path[0]],
        "goal": [round(v, 1) for v in path[-1]],
        "path": [[round(v, 1) for v in p] for p in path],
        "runs": runs,
    }


def pack_runs(records: list[dict]) -> tuple[bytes, list[dict]]:
    """Frames as one binary blob; the JSON index carries byte offsets into it.

    Layout per frame: x,y,z,yaw as float32, then one byte of flags (bit 0 on_ground, bit 1 jump),
    then speed_xy as float32 — 21 bytes. Float rather than quantised because the owner asked for the
    movement to be exact, and 4 bytes a channel is the cheapest way to promise that without a
    caveat.
    """
    blob = bytearray()
    index = []
    for rec in records:
        runs_meta = []
        for run in rec["runs"]:
            off = len(blob)
            for (x, y, z, yaw, og, jmp, spd) in run["frames"]:
                blob += struct.pack("<ffffBf", x, y, z, yaw, (1 if og else 0) | (2 if jmp else 0), spd)
            runs_meta.append({k: run[k] for k in
                              ("count", "attempt_ids", "outcome", "ticks", "time_s",
                               "wall_contact", "segments")}
                             | {"offset": off, "n_frames": len(run["frames"])})
        index.append({k: rec[k] for k in rec if k != "runs"} | {"runs": runs_meta})
    return bytes(blob), index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="race_v5.pt")
    ap.add_argument("--human-k", type=int, default=0)
    ap.add_argument("--greedy-n", type=int, default=64)
    ap.add_argument("--sampled-n", type=int, default=24)
    ap.add_argument("--tag", default="v5")
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    ac = PPOActorCritic(dev="cuda")
    ac.load(race.OUT / a.ckpt)

    records = []
    for r in race.training_routes(human_k=a.human_k):
        tracks = race.human_paths_for(r, 1) if a.human_k else [None]
        hp = tracks[0] if tracks else None
        for greedy, n in ((True, a.greedy_n), (False, a.sampled_n)):
            rec = record_route(ac, r, n, greedy, hp)
            records.append(rec)
            print(f"{r.name:22s} {rec['decode']:8s} n={n:3d} distinct={rec['distinct_trajectories']:3d} "
                  f"arr={rec['arrival_rate'] * 100:5.1f}%  "
                  f"med={rec['median_s'] if rec['median_s'] is None else round(rec['median_s'], 2)}  "
                  f"wall={rec['wall_contact_attempts']}", flush=True)

    blob, index = pack_runs(records)
    (OUT / f"frames_{a.tag}.bin").write_bytes(blob)
    (OUT / f"index_{a.tag}.json").write_text(json.dumps(
        {"ckpt": a.ckpt, "tick_dt": TICK_DT, "arrive_box": C.ARRIVE_BOX, "arrive_z": C.ARRIVE_Z,
         "frame_bytes": 21, "records": index}, indent=1, default=float))
    print(f"frames {len(blob) / 1e6:.2f} MB -> {OUT / f'frames_{a.tag}.bin'}")


if __name__ == "__main__":
    main()
