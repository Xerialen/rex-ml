"""Speedhopps-analys (Gate 2): utför policyn FARTGRINDADE hopp — gap som bara
kan korsas i hög fart — och upprepas de på samma platser (inlärda genvägar)?

    PYTHONPATH=. sim/.venv-sf/bin/python -m rl.analyze_gapjumps \
        pipeline/out/rl/train_dir/<experiment> [--n 10] [--out evidence/...json]

Fysikgrund: hopp-vz 270, g 800 ⇒ luftid ~0,675 s; horisontell räckvidd vid
marktaket 320 u/s ≈ 216 u. Ett luftsegment med span > 240 u och nära plan
utgång (dz > −64) kräver alltså fart över marktaket = FARTGRINDAT. Drops
(dz ≤ −64) rapporteras separat (fartbevarande stup, också ruttvärde, men
inte "öppnade gap"). Kluster: startpunkter rastreras till 64 u-celler;
upprepning över episoder ⇒ inlärd rutt, inte slump.
"""
from __future__ import annotations

import argparse
import json
import os
import types
from collections import Counter
from pathlib import Path

os.environ.setdefault("SF_STDDEV_MAX", "1.0")

import numpy as np
import torch

from rl.eval_gate1 import load_policy
from rl.sf_env import QWGate2Env

GATE2_ZONES = Path(__file__).resolve().parent.parent / "evidence" / "gate2_zones.json"
SPEED_GATED_SPAN = 240.0     # > markfartens ~216 u + marginal
LEVEL_DZ = -64.0             # planare än så = gap-korsning, under = drop


def _zone_lookup():
    zones = json.load(open(GATE2_ZONES))
    if isinstance(zones, dict):
        zones = zones["zones"]
    def name(pos):
        best, bd = None, 1e18
        for z in zones:
            (lo, hi) = z["bounds"]
            inside = all(lo[i] - 64 <= pos[i] <= hi[i] + 64 for i in range(3))
            c = z["centroid"]
            d = sum((pos[i] - c[i]) ** 2 for i in range(3))
            if inside and d < bd:
                best, bd = z["name"], d
        return best or "?"
    return name


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("exp_dir", type=Path)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    cfg, _, ac = load_policy(args.exp_dir, "cpu")
    env = QWGate2Env("qw_gate2", types.SimpleNamespace(qw_backend="qwsim"))
    from sample_factory.model.model_utils import get_rnn_size

    segs = []                     # (ep, takeoff xyz, land xyz, span, dz, v_takeoff)
    for ep in range(args.n):
        obs, _ = env.reset()
        rnn = torch.zeros([1, get_rnn_size(cfg)])
        done = False
        air_start = None
        c = env.core
        prev = (c.pos.copy(), float(np.hypot(c.vel[0], c.vel[1])), c.onground)
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
            pos, sp, og = c.pos.copy(), float(np.hypot(c.vel[0], c.vel[1])), c.onground
            if air_start is None and prev[2] and not og:
                air_start = prev                       # lyfte denna tick
            elif air_start is not None and og:
                t0, v0 = air_start[0], air_start[1]
                span = float(np.hypot(pos[0] - t0[0], pos[1] - t0[1]))
                segs.append({"ep": ep, "takeoff": [round(x, 1) for x in t0],
                             "land": [round(x, 1) for x in pos],
                             "span": round(span, 1), "dz": round(float(pos[2] - t0[2]), 1),
                             "v_takeoff": round(v0, 1)})
                air_start = None
            prev = (pos, sp, og)
            done = term or trunc

    name = _zone_lookup()
    gated = [s for s in segs if s["span"] > SPEED_GATED_SPAN and s["dz"] > LEVEL_DZ]
    drops = [s for s in segs if s["span"] > SPEED_GATED_SPAN and s["dz"] <= LEVEL_DZ]
    cells = Counter((int(s["takeoff"][0] // 64), int(s["takeoff"][1] // 64)) for s in gated)
    clusters = []
    for (cx, cy), cnt in cells.most_common(15):
        ex = [s for s in gated if int(s["takeoff"][0] // 64) == cx and int(s["takeoff"][1] // 64) == cy]
        eps = sorted({s["ep"] for s in ex})
        s0 = max(ex, key=lambda s: s["span"])
        clusters.append({
            "cell_xy": [cx * 64, cy * 64], "count": cnt, "episodes": eps,
            "zone_from": name(s0["takeoff"]), "zone_to": name(s0["land"]),
            "max_span": s0["span"], "dz": s0["dz"], "v_takeoff": s0["v_takeoff"],
            "example": {"takeoff": s0["takeoff"], "land": s0["land"]},
        })
    res = {
        "experiment": str(args.exp_dir), "episodes": args.n,
        "air_segments": len(segs),
        "speed_gated_jumps": len(gated),
        "speed_gated_per_episode": round(len(gated) / args.n, 2),
        "long_drops": len(drops),
        "distinct_takeoff_cells": len(cells),
        "repeated_cells": sum(1 for v in cells.values() if v >= 3),
        "repeated_across_episodes": sum(1 for cl in clusters if len(cl["episodes"]) >= 3),
        "span_p50": float(np.median([s["span"] for s in gated])) if gated else None,
        "span_max": float(max((s["span"] for s in gated), default=0)),
        "clusters_top": clusters,
    }
    print(json.dumps(res, indent=1))
    if args.out:
        json.dump(res, open(args.out, "w"), indent=1)


if __name__ == "__main__":
    main()
