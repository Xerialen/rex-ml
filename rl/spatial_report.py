"""Spatial rapport för Gate 2: VAR rör sig policyn, var är den snabb/långsam,
var fastnar den. Ägarens stående önskemål (2026-08-01): rapportera geografi
med zonnamn, inte bara aggregatsiffror.

    PYTHONPATH=. sim/.venv-sf/bin/python -m rl.spatial_report \
        pipeline/out/rl/train_dir/<experiment> [--n 10] [--out evidence/...json]

Zonnamn ur evidence/gate2_zones.json; voxlar utanför namngivna zoner märks
"open-misc"/"constrained-misc" via zonrastrets klass.
"""
from __future__ import annotations

import argparse
import json
import os
import types
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("SF_STDDEV_MAX", "1.0")

import numpy as np
import torch

from rl.eval_gate1 import load_policy
from rl.sf_env import QWGate2Env

GATE2_ZONES = Path(__file__).resolve().parent.parent / "evidence" / "gate2_zones.json"


_FAMILY = [  # prefix → landmärkesnamn ägaren känner igen
    ("ratop", "RA-toppen"), ("ralow", "RA-nedre/NG-tunneln"), ("rl", "RL"),
    ("quad", "quad"), ("mega", "mega"), ("pent", "pent"), ("ssg-ya", "YA/SSG"),
    ("ya", "YA"), ("sng", "SNG"), ("window", "window"), ("ring", "ringen"),
    ("tele", "tele"), ("constrained-misc", None),  # catch-all utesluts ur uppslaget
]


def _family(name: str):
    for pre, label in _FAMILY:
        if name.startswith(pre):
            return label
    return None


class ZoneNamer:
    """Närmaste-landmärke-uppslag: POI-zonernas centroider kollapsade per familj
    (gårdarna är ozonade OPEN-ytor, så boxuppslag ger bara catch-all)."""

    def __init__(self):
        zones = json.load(open(GATE2_ZONES))
        if isinstance(zones, dict):
            zones = zones["zones"]
        self.pois = [(lbl, np.array(z["centroid"], float))
                     for z in zones if (lbl := _family(z["name"]))]

    def name(self, pos, waterlevel: int = 0):
        if waterlevel > 0:
            return "VATTNET"
        best, bd = "?", 1e18
        for lbl, c in self.pois:
            d = (pos[0] - c[0]) ** 2 + (pos[1] - c[1]) ** 2 + 0.3 * (pos[2] - c[2]) ** 2
            if d < bd:
                best, bd = lbl, d
        return f"vid {best}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("exp_dir", type=Path)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    cfg, _, ac = load_policy(args.exp_dir, "cpu")
    env = QWGate2Env("qw_gate2", types.SimpleNamespace(qw_backend="qwsim"))
    from sample_factory.model.model_utils import get_rnn_size
    namer = ZoneNamer()

    ticks = defaultdict(int)
    speed = defaultdict(float)
    slow = defaultdict(int)          # tickar under 100 u/s per zon (dipp/tvekan)
    episodes = []
    for ep in range(args.n):
        obs, _ = env.reset()
        rnn = torch.zeros([1, get_rnn_size(cfg)])
        c = env.core
        spawn = c.pos.copy()
        done = False
        visited_seq = []              # zonbyten i ordning (rutten)
        last_zone = None
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
            zn = namer.name(c.pos, c.waterlevel)
            ticks[zn] += 1
            speed[zn] += sp
            if sp < 100.0:
                slow[zn] += 1
            if zn != last_zone:
                visited_seq.append(zn)
                last_zone = zn
            done = term or trunc
        episodes.append({
            "spawn": [round(x) for x in spawn],
            "spawn_zone": namer.name(spawn),  # spawn är aldrig i vatten (settling på golv)
            "stuck": bool(info.get("stuck", False)),
            "stuck_pos": [round(x) for x in c.pos] if info.get("stuck") else None,
            "stuck_zone": namer.name(c.pos) if info.get("stuck") else None,
            "mean_speed": round(info.get("mean_speed_counted", 0.0), 1),
            "distinct_zones": len(set(visited_seq)),
            "route_zones": visited_seq[:40],
        })

    total = sum(ticks.values())
    zone_rows = sorted(
        ({"zon": z, "tidsandel_pct": round(100 * n / total, 1),
          "medelfart": round(speed[z] / n, 1),
          "tvekan_pct": round(100 * slow[z] / n, 1)}
         for z, n in ticks.items() if n > total * 0.005),
        key=lambda r: -r["tidsandel_pct"])
    res = {"experiment": str(args.exp_dir), "episodes": args.n,
           "zoner": zone_rows, "episoder": episodes}
    print(json.dumps(res, indent=1, ensure_ascii=False))
    if args.out:
        json.dump(res, open(args.out, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
