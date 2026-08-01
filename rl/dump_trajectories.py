"""Dumpar greedy-episoder som 3D-banor för dm3-artefakten + hoppanalys.

    PYTHONPATH=. sim/.venv-sf/bin/python -m rl.dump_trajectories \
        pipeline/out/rl/train_dir/<experiment> --n 10 --out <fil.json>

Per episod: bana (var 2:e tick: x,y,z,fart), spawn, medelfart (counted),
zonsekvens (landmärken). Global analys (ägarens frågor 2026-08-01, utvidgade
till ALLA hopp/rutter): varje luftsegment med span >200 u registreras med
golvdjup under kordan (3-punkts nedåt-raycast, samma metod som
analyze_gapjumps) så äkta gap-hopp (tomrum under banan) skiljs från platta
bunnyhopp; ring↔quad-direktflygningar; mega-SNG-besök.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import types
from pathlib import Path

os.environ.setdefault("SF_STDDEV_MAX", "1.0")

import numpy as np
import torch

from rl.eval_gate1 import load_policy
from rl.sf_env import QWGate2Env
from rl.spatial_report import ZoneNamer

BSP = Path("/home/benjamin-adm/mlx/qwserver/serverdir/id1/maps/dm3.bsp")
NEAR = 180.0                 # "vid plattformen" (u, 2D)


def item_positions():
    data = BSP.read_bytes()
    off, ln = struct.unpack_from("<ii", data, 4)
    txt = data[off:off + ln].split(b"\0")[0].decode("latin-1")
    ents = [dict(re.findall(r'"([^"]+)"\s+"([^"]*)"', b))
            for b in re.findall(r"\{(.*?)\}", txt, re.S)]
    want = {"item_artifact_invisibility": "ring",
            "item_artifact_super_damage": "quad",
            "weapon_supernailgun": "sng"}
    out = {}
    for e in ents:
        cn = e.get("classname", "")
        if cn in want:
            out[want[cn]] = np.array([float(v) for v in e["origin"].split()])
        if cn == "item_health" and e.get("spawnflags") == "2":
            out.setdefault("megas", []).append(
                np.array([float(v) for v in e["origin"].split()]))
    # mega-SNG = megan närmast SNG
    out["mega_sng"] = min(out["megas"], key=lambda m: np.linalg.norm(m[:2] - out["sng"][:2]))
    return out


def near2d(pos, target, r=NEAR):
    return float(np.hypot(pos[0] - target[0], pos[1] - target[1])) < r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("exp_dir", type=Path)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    items = item_positions()
    cfg, _, ac = load_policy(args.exp_dir, "cpu")
    env = QWGate2Env("qw_gate2", types.SimpleNamespace(qw_backend="qwsim"))
    from sample_factory.model.model_utils import get_rnn_size
    namer = ZoneNamer()

    episodes = []
    ring_quad_flights = []
    air_segments = []                 # alla hopp/fall span>200: klassas i byggsteget
    climb_landings = []               # V1a-mätaren: landningar med rise>=24 (bonusvillkoret)
    for ep in range(args.n):
        obs, _ = env.reset()
        rnn = torch.zeros([1, get_rnn_size(cfg)])
        c = env.core
        pts = []
        air_start = None
        prev_og = c.onground
        prev_pos = c.pos.copy()
        mega_sng_ticks = 0
        route = []
        last_zone = None
        done = False
        t = 0
        while not done:
            with torch.no_grad():
                out = ac(ac.normalize_obs({"obs": torch.tensor(obs[None])}), rnn)
                rnn = out["new_rnn_states"]
                dist = ac.action_distribution()
                parts = []
                for d in dist.distributions:
                    parts.append(d.means.ravel() if hasattr(d, "means")
                                 else torch.argmax(d.log_probs, dim=-1).float().ravel())
                a = torch.cat(parts).numpy()
            obs, r, term, trunc, info = env.step(a)
            sp = float(np.hypot(c.vel[0], c.vel[1]))
            if t % 2 == 0:
                pts.append([round(float(c.pos[0]), 1), round(float(c.pos[1]), 1),
                            round(float(c.pos[2]), 1), round(sp)])
            zn = namer.name(c.pos, c.waterlevel)
            if zn != last_zone:
                route.append(zn)
                last_zone = zn
            if near2d(c.pos, items["mega_sng"], 120.0):
                mega_sng_ticks += 1
            if air_start is None and prev_og and not c.onground:
                air_start = (prev_pos.copy(), sp)
            elif air_start is not None and c.onground:
                a0, v0 = air_start
                a1 = c.pos
                span = float(np.hypot(a1[0] - a0[0], a1[1] - a0[1]))
                # V1a-mätaren (2026-08-01, ägarfråga "mäter vi klätterbonusen?"):
                # landningar med höjdvinst ≥24 u = exakt bonusens utlösningsvillkor;
                # mänsklig RA-klättring har rise p50 32.8/hopp. Oberoende av span.
                rise = float(a1[2] - a0[2])
                if rise >= 24.0:
                    climb_landings.append({
                        "ep": ep, "rise": round(rise, 1), "span": round(span, 1),
                        "v_takeoff": round(v0),
                        "pos": [round(float(v), 1) for v in a1],
                    })
                if span > 200.0:
                    # golvdjup under kordan (jfr analyze_gapjumps): skiljer
                    # gap-hopp från platta bunnyhopp
                    zref = min(float(a0[2]), float(a1[2])) + 8.0
                    pts3 = np.array([[a0[0] + (a1[0] - a0[0]) * f,
                                      a0[1] + (a1[1] - a0[1]) * f, zref]
                                     for f in (0.3, 0.5, 0.7)], dtype=np.float32)
                    down = np.tile(np.array([[0.0, 0.0, -1.0]], dtype=np.float32), (3, 1))
                    fr = np.asarray(c.b.trace_rays(pts3, down, 320.0),
                                    dtype=np.float32).ravel()[:3]
                    air_segments.append({
                        "ep": ep,
                        "takeoff": [round(float(v), 1) for v in a0],
                        "land": [round(float(v), 1) for v in a1],
                        "span": round(span, 1),
                        "dz": round(float(a1[2] - a0[2]), 1),
                        "v_takeoff": round(v0),
                        "floor_depth": round(float(fr.max() * 320.0), 1),
                    })
                for src, dst in (("ring", "quad"), ("quad", "ring")):
                    if near2d(a0, items[src]) and near2d(a1, items[dst]):
                        ring_quad_flights.append({
                            "ep": ep, "riktning": f"{src}→{dst}",
                            "takeoff": [round(float(v), 1) for v in a0],
                            "land": [round(float(v), 1) for v in a1],
                            "span": round(span, 1),
                        })
                air_start = None
            prev_og = c.onground
            prev_pos = c.pos.copy()
            t += 1
            done = term or trunc
        episodes.append({
            "spawn_zone": namer.name(np.array(pts[0][:3])),
            "mean_speed": round(info.get("mean_speed_counted", 0.0), 1),
            "stuck": bool(info.get("stuck", False)),
            "mega_sng_s": round(mega_sng_ticks * 0.013, 1),
            "route": route[:24],
            "path": pts,
        })

    res = {"experiment": str(args.exp_dir), "n": args.n,
           "items": {k: [round(float(x), 1) for x in v]
                     for k, v in items.items() if k != "megas"},
           "ring_quad_flights": ring_quad_flights,
           "mega_sng_visits": sum(1 for e in episodes if e["mega_sng_s"] > 0.2),
           "air_segments": air_segments,
           "climb_landings": climb_landings,
           "episodes": episodes}
    json.dump(res, open(args.out, "w"))
    print(json.dumps({k: v for k, v in res.items() if k != "episodes"}, indent=1,
                     ensure_ascii=False))
    print("episoder:", [(e["spawn_zone"], e["mean_speed"], e["mega_sng_s"]) for e in episodes])


if __name__ == "__main__":
    main()
