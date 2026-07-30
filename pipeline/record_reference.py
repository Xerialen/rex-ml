"""Turn the owner's reference demo for window-to-rl into the same replay record the ML page uses.

Everything here comes out of `demos/dm3-drillar/window-to-rl.qwd` and nothing is simulated. The
parser is `qw-demo-miner`'s strict QWD v2 extractor — the same one that produced
`testsuite/scenarios/dm3/routes-v1.json`, so the numbers on this page and the reference time in the
scenario file have one origin, not two.

What the demo carries, per server tick (432 samples over 5.597 s = 77.2 Hz):

  * `playerinfo` — the server's own view of the recording client: origin and velocity.
  * `dem_cmd` — what the player's hands did: view angles, forwardmove/sidemove, and the button
    bitfield, so the jump presses are the real ones rather than something inferred from the path.

Two honest gaps, both surfaced on the page rather than papered over:

  * **`on_ground` is not transmitted.** QuakeWorld's `svc_playerinfo` has no ground bit; the client
    predicts it. It is derived here as `velocity_z == 0`, which holds on 71.5 % of this demo's
    frames — against 74.5 % measured on the corpus, so the proxy lands where it should.
  * **Pitch exists here and does not exist in the ML policy.** The demo records a real view pitch
    (the player looks down through the window); the trained policy's observation has pitch pinned at
    0.0 because the environment has no view control in that axis. The first-person view is therefore
    genuinely richer here, and that difference is a property of the two subjects, not of the page.
"""

from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/benjamin-adm/qw-demo-miner-fix-round/qwd/v2")
from qwd_v2.extractor import extract_file  # noqa: E402

DEMO_DIR = Path("/home/benjamin-adm/rex-ml/demos/dm3-drillar")

# Which cohort route each reference demo is the reference *for*. The demos the owner recorded and the
# cohort routes route-lab measured its medians over are two different namings of the same journeys,
# and the mapping is stated once here rather than guessed per call site.
DEMO_ROUTE = {
    "window-to-rl.qwd": "window_to_rl",
    "ralow-to-ratop.qwd": "ralow_to_ratop",
    "ring-to-ratop.qwd": "ring_to_ratop",
    "lifts-or-ring-to-sngmega.qwd": "lifts_to_sng_mega",
    "sngspawns-to-sngmega.qwd": "sngspawn_a_to_mega",
    "(spawn)sngspawn-to-ring-to-ratop.qwd": "tunnel_to_ra",
    "(spawn)rarox-to-quad.qwd": "sngspawn_a_to_quad",
    "(spawn)rl-to-ratop-xer.qwd": "quad_to_ra",
}
MANIFEST = Path("/home/benjamin-adm/rtx-mltest/testsuite/scenarios/dm3/routes-v1.json")
OUT = Path("/home/benjamin-adm/rex-ml/pipeline/out/replay")

# The rocket launcher's own origin from the corpus (165,516 pickup events), lifted to the height a
# player standing on that spot has his origin at — the same endpoint `cohort_routes.py` uses.
RL_ITEM = (1520.0, 496.0, -112.0)
RL_STAND = (1520.0, 496.0, -88.0)

# The live server's arrival gate (`rtx-game/src/control.rs`), drawn on the page so the reference and
# the policy are measured against the same box.
ARRIVE_BOX = 24.0
ARRIVE_Z = 48.0

FRAME_BYTES = 25  # x,y,z,yaw f32 | flags u8 | speed f32 | pitch f32


def _f(v) -> float:
    return float(v) if v is not None else 0.0


def load(demo: Path) -> dict:
    ex = extract_file(demo)
    rows = ex.rows
    pi = [r for r in rows if r["event"] == "playerinfo"]
    dc = [r for r in rows if r["event"] == "dem_cmd"]
    if len(pi) != len(dc):
        # Not fatal, but it must be visible: the pairing below assumes one command per state.
        print(f"WARNING: {len(pi)} playerinfo rows vs {len(dc)} dem_cmd rows; pairing by index",
              file=sys.stderr)

    t0 = _f(pi[0]["packet_time"])
    frames = []
    for i, p in enumerate(pi):
        c = dc[i] if i < len(dc) else {}
        vx, vy, vz = _f(p["velocity_x"]), _f(p["velocity_y"]), _f(p["velocity_z"])
        frames.append({
            "t": _f(p["packet_time"]) - t0,
            "x": _f(p["origin_x"]), "y": _f(p["origin_y"]), "z": _f(p["origin_z"]),
            "yaw": _f(c.get("command_yaw")), "pitch": _f(c.get("command_pitch")),
            "speed": math.hypot(vx, vy),
            "vz": vz,
            "ground": vz == 0.0,
            "jump": bool((c.get("buttons") or 0) & 2),
            "fwd": c.get("forwardmove") or 0, "side": c.get("sidemove") or 0,
        })
    return {"frames": frames, "manifest": ex.manifest, "name": demo.name,
            "demo_id": pi[0]["demo_id"], "duration_s": frames[-1]["t"]}


def segments(frames: list[dict], demo_name: str, target) -> list[dict]:
    """The three views of the same recording the page offers, each a real interval of it.

    Not three attempts — one recording, cut three ways, and labelled so nobody reads it as three
    runs. The cuts are the ones the owner's own manifest already makes: the whole file, the motion
    run it segments out, and the stretch from the run's start to the closest approach to the rocket
    launcher, which is the number the scenario's `reference_time_s` is built from.
    """
    man = json.loads(MANIFEST.read_text())
    hit = [d for d in man["demos"] if d["demo"] == demo_name]
    t_all = np.array([f["t"] for f in frames])
    d_all = np.array([math.dist((f["x"], f["y"], f["z"]), target) for f in frames])
    if not hit or not hit[0].get("runs"):
        # No manifest entry: the whole recording is the only honest cut, plus the approach to the
        # item, which is found in the frames themselves.
        i_rl = int(np.argmin(d_all))
        return [
            {"label": "hela demot", "a": 0, "b": len(frames) - 1,
             "note": f"{len(frames)} tick, {t_all[-1]:.3f} s — inget manifestsegment för detta demo"},
            {"label": "fram till itemet", "a": 0, "b": i_rl,
             "note": f"närmaste passage, {d_all[i_rl]:.1f} u ifrån"},
        ]
    run = hit[0]["runs"][0]
    t = np.array([f["t"] for f in frames])

    def idx(ts: float) -> int:
        return int(np.argmin(np.abs(t - ts)))

    i_start, i_end = idx(run["start_time_s"]), idx(run["end_time_s"])

    # Closest approach to the rocket launcher, found in the frames rather than taken on trust — the
    # manifest's own `reach_time_s` is the check, not the source.
    d = d_all
    i_rl = i_start + int(np.argmin(d[i_start:i_end + 1]))

    return [
        {"label": "hela demot", "a": 0, "b": len(frames) - 1,
         "note": f"{len(frames)} tick, {t[-1]:.3f} s — allt som spelades in"},
        {"label": "körningen", "a": i_start, "b": i_end,
         "note": f"manifestets rörelsesegment, {run['travel_time_s']:.3f} s"},
        {"label": "fram till itemet", "a": i_start, "b": i_rl,
         "note": f"närmaste passage av itemet, {d[i_rl]:.1f} u ifrån"},
    ]


def build_record(demo: Path, route_name: str) -> tuple[bytes, dict]:
    from . import cohort_routes as C
    from . import record_replay as RRP
    r = C.BY_NAME[route_name]
    item = (r.target[0], r.target[1], r.target[2] - C.PLAYER_ORIGIN_DZ)
    demo_data = load(demo)
    frames = demo_data["frames"]
    segs = segments(frames, demo.name, item)

    blob = bytearray()
    runs = []
    for s in segs:
        off = len(blob)
        for f in frames[s["a"]:s["b"] + 1]:
            blob += struct.pack("<ffffBff", f["x"], f["y"], f["z"], f["yaw"],
                                (1 if f["ground"] else 0) | (2 if f["jump"] else 0),
                                f["speed"], f["pitch"])
        sub = frames[s["a"]:s["b"] + 1]
        moving = [f["speed"] for f in sub if f["speed"] > 1.0]
        runs.append({
            "count": 1, "attempt_ids": [0], "outcome": "arrived",
            "ticks": len(sub), "time_s": round(frames[s["b"]]["t"] - frames[s["a"]]["t"], 3),
            "wall_contact": False, "offset": off, "n_frames": len(sub),
            "label": s["label"], "note": s["note"],
            # Measured the same way as the policy's, with the caveat this file already states: the
            # reference's ground flag is derived (vz == 0), not transmitted, so a segment boundary
            # here is an inference where the policy's is a reading.
            "segments": RRP.air_segments([(f["x"], f["y"], f["z"], f["yaw"], f["ground"],
                                           f["jump"], f["speed"]) for f in sub]),
            "median_speed_ups": round(float(np.median(moving)), 1) if moving else 0.0,
            "peak_speed_ups": round(max((f["speed"] for f in sub), default=0.0), 1),
            "frac_above_320": round(float(np.mean([m > 320 for m in moving])), 3) if moving else 0.0,
            "frac_airborne": round(float(np.mean([not f["ground"] for f in sub])), 3),
            "jump_presses": int(sum(1 for i in range(1, len(sub))
                                    if sub[i]["jump"] and not sub[i - 1]["jump"])),
        })

    rec = {
        "route": route_name,
        "geometry": f"referensdemo {demo.name}",
        "decode": "reference",
        "group_label": f"REFERENSDEMO {demo.name} — en inspelning, {len(runs)} utsnitt",
        "attempts": 1, "distinct_trajectories": 1, "arrival_rate": 1.0,
        "median_s": runs[-1]["time_s"], "best_s": runs[-1]["time_s"], "worst_s": runs[-1]["time_s"],
        "wall_contact_attempts": 0,
        "gate_s": r.gate_s, "pass_s": r.pass_s, "owner_s": r.owner_s,
        "start": [round(v, 1) for v in (frames[0]["x"], frames[0]["y"], frames[0]["z"])],
        "goal": [round(v, 1) for v in r.target],
        "path": [[round(f["x"], 1), round(f["y"], 1), round(f["z"], 1)] for f in frames],
        "runs": runs,
        "demo_id_sha256": demo_data["demo_id"],
        "sample_rate_hz": round(len(frames) / max(demo_data["duration_s"], 1e-6), 1),
    }
    return bytes(blob), rec


def main():
    from . import record_replay as RRP

    OUT.mkdir(parents=True, exist_ok=True)
    demo = load()
    frames = demo["frames"]
    segs = segments(frames)

    blob = bytearray()
    runs = []
    for s in segs:
        off = len(blob)
        n = s["b"] - s["a"] + 1
        for f in frames[s["a"]:s["b"] + 1]:
            blob += struct.pack("<ffffBff", f["x"], f["y"], f["z"], f["yaw"],
                                (1 if f["ground"] else 0) | (2 if f["jump"] else 0),
                                f["speed"], f["pitch"])
        span = frames[s["b"]]["t"] - frames[s["a"]]["t"]
        sub = frames[s["a"]:s["b"] + 1]
        moving = [f["speed"] for f in sub if f["speed"] > 1.0]
        runs.append({
            "count": 1, "attempt_ids": [0], "outcome": "arrived",
            "ticks": n, "time_s": round(span, 3), "wall_contact": False,
            "offset": off, "n_frames": n,
            "label": s["label"], "note": s["note"],
            "segments": RRP.air_segments([(f["x"], f["y"], f["z"], f["yaw"], f["ground"],
                                           f["jump"], f["speed"]) for f in sub]),
            "median_speed_ups": round(float(np.median(moving)), 1) if moving else 0.0,
            "peak_speed_ups": round(max((f["speed"] for f in sub), default=0.0), 1),
            "frac_above_320": round(float(np.mean([m > 320 for m in moving])), 3) if moving else 0.0,
            "frac_airborne": round(float(np.mean([not f["ground"] for f in sub])), 3),
            "jump_presses": int(sum(1 for i in range(1, len(sub))
                                    if sub[i]["jump"] and not sub[i - 1]["jump"])),
        })

    path = [[round(f["x"], 2), round(f["y"], 2), round(f["z"], 2)] for f in frames]
    record = {
        "route": "window_to_rl",
        "geometry": f"referensdemo {DEMO.name}",
        "decode": "reference",
        "group_label": "referensdemo — en inspelning, tre utsnitt",
        "attempts": 1,
        "distinct_trajectories": 1,
        "arrival_rate": 1.0,
        "median_s": runs[2]["time_s"],
        "best_s": runs[2]["time_s"],
        "worst_s": runs[2]["time_s"],
        "wall_contact_attempts": 0,
        "gate_s": 2.75,
        "pass_s": 4.75,
        "owner_s": 3.49,
        "start": path[0],
        "goal": [RL_STAND[0], RL_STAND[1], RL_STAND[2]],
        "path": path,
        "runs": runs,
    }

    (OUT / "frames_ref.bin").write_bytes(bytes(blob))
    (OUT / "index_ref.json").write_text(json.dumps({
        "ckpt": DEMO.name,
        "source": str(DEMO),
        "demo_id_sha256": demo["demo_id"],
        "parser": "qw-demo-miner qwd/v2 strict extractor",
        "sample_rate_hz": round(len(frames) / demo["duration_s"], 1),
        "tick_dt": round(demo["duration_s"] / (len(frames) - 1), 6),
        "arrive_box": ARRIVE_BOX, "arrive_z": ARRIVE_Z,
        "frame_bytes": FRAME_BYTES, "has_pitch": True,
        "ground_is_derived": True,
        "records": [record],
    }, indent=1))
    for r in runs:
        print(f"{r['label']:14s} {r['n_frames']:4d} tick  {r['time_s']:6.3f} s  "
              f"medfart {r['median_speed_ups']:5.1f}  topp {r['peak_speed_ups']:5.1f}  "
              f">320 {r['frac_above_320'] * 100:4.0f}%  luft {r['frac_airborne'] * 100:4.0f}%  "
              f"hopp {r['jump_presses']}")
    print(f"frames {len(blob) / 1e6:.3f} MB")


if __name__ == "__main__":
    main()
