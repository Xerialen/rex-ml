"""The 100m corridor: how fast does the policy actually get, with nothing in the way?

The owner's gate, and it comes before any dm3 result: **peak speed of at least 790 u/s** down the
straight on `100m`, the same run `rtx-mcp`'s `corridor_test` puts the analytic bot through
(`start=(224, -1408, 32)`, `end=(224, 2900, 32)`, a 4308 u straight along +Y; the finish platform
steps up near y=3008, so the end is kept short of it).

Why this is the right test to fail on first: every dm3 route measured so far is a mixture of
navigation, geometry and speed, and a slow time can be blamed on any of the three. A straight
corridor removes two of them. `sv_maxspeed` is 320 — everything above it is air acceleration
compounding across jumps, which is the whole of the movement problem stated without a map.

Reported per trial, matching what `corridor_test` reports for the analytic bot so the two are
comparable: peak speed, cross-track drift from the centreline, and frames spent moving backwards.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

MAP = "/home/benjamin-adm/rex-ml/rtx/playground/qw/maps/100m.bsp"
START = (224.0, -1408.0, 32.0)
END = (224.0, 2900.0, 32.0)
PEAK_GATE = 790.0
MAX_TICKS = 1600
OUT = Path("/home/benjamin-adm/rex-ml/evidence/corridor_100m.json")


def run(actor, n: int, dev: str = "cuda", greedy: bool = False,
        max_ticks: int = MAX_TICKS) -> dict:
    """One batch of `n` runs down the corridor, from the same start, sampled or greedy."""
    import rex_env
    import torch

    from . import policy as P

    env = rex_env.PyVecEnv.from_path(MAP, [START, END], n, 24.0, max_ticks)
    obs = env.reset()
    done = np.zeros(n, bool)
    ticks = np.zeros(n, np.int64)
    peak = np.zeros(n, np.float32)
    cross = np.zeros(n, np.float32)
    reverse = np.zeros(n, np.int64)
    arrived = np.zeros(n, bool)
    speeds: list[np.ndarray] = []

    for _ in range(max_ticks + 2):
        t = torch.tensor(obs, device=dev, dtype=torch.float32)
        with torch.no_grad():
            fl, sl, yaw, jl = actor(t)
            if greedy:
                f, s = fl.argmax(-1), sl.argmax(-1)
                j = (jl.squeeze(-1) > 0).float()
            else:
                f = torch.distributions.Categorical(logits=fl).sample()
                s = torch.distributions.Categorical(logits=sl).sample()
                j = (torch.rand_like(jl.squeeze(-1)) < torch.sigmoid(jl.squeeze(-1))).float()
        a = np.stack([(f.cpu().numpy() - 1).astype(np.float32),
                      (s.cpu().numpy() - 1).astype(np.float32),
                      yaw.squeeze(-1).cpu().numpy(), j.cpu().numpy()], 1).astype(np.float32)

        o, v = env.origins, env.velocities
        live = ~done
        sp = np.linalg.norm(v[:, :2], axis=1)
        peak = np.where(live, np.maximum(peak, sp), peak)
        # Cross-track is the deviation from the corridor's own axis, which here is x.
        cross = np.where(live, np.maximum(cross, np.abs(o[:, 0] - START[0])), cross)
        reverse += (live & (v[:, 1] < -1.0)).astype(np.int64)
        ticks += live.astype(np.int64)
        speeds.append(sp[live])

        obs, parts, dones = env.step(a)
        parts = np.asarray(parts)
        for i in np.flatnonzero(live & np.asarray(dones)):
            done[i] = True
            arrived[i] = parts[i, 4] > 0
        if done.all():
            break

    allsp = np.concatenate([x for x in speeds if x.size]) if speeds else np.zeros(1)
    return {
        "n": n, "greedy": greedy,
        "peak_max": round(float(peak.max()), 1),
        "peak_median": round(float(np.median(peak)), 1),
        "peak_p10": round(float(np.percentile(peak, 10)), 1),
        "arrival_rate": round(float(arrived.mean()), 3),
        "median_time_s": round(float(np.median(ticks[arrived]) * 0.014), 2) if arrived.any() else None,
        "median_speed_ups": round(float(np.median(allsp)), 1),
        "frac_above_320": round(float((allsp > 320).mean()), 3),
        "frac_above_790": round(float((allsp > PEAK_GATE).mean()), 4),
        "max_cross_track_u": round(float(cross.max()), 1),
        "reverse_frames": int(reverse.sum()),
        "passes_peak_gate": bool(peak.max() >= PEAK_GATE),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ckpt")
    ap.add_argument("--n", type=int, default=64)
    ap.add_argument("--dev", default="cuda")
    a = ap.parse_args()

    import torch

    from . import policy as P

    ck = torch.load(a.ckpt, map_location=a.dev, weights_only=False)
    actor = P.make_disc_actor(14, ck.get("width", 512), ck.get("depth", 3))().to(a.dev)
    actor.load_state_dict(ck["actor"])
    actor.eval()

    rows = []
    for greedy in (True, False):
        r = run(actor, a.n if not greedy else min(a.n, 8), dev=a.dev, greedy=greedy)
        r["ckpt"] = a.ckpt
        rows.append(r)
        print(f"{'greedy ' if greedy else 'samplad'}  topp max {r['peak_max']:7.1f}  "
              f"median {r['peak_median']:7.1f}  p10 {r['peak_p10']:7.1f}  "
              f"| ankomst {r['arrival_rate'] * 100:5.1f}%  tid {r['median_time_s']}  "
              f"| >320 {r['frac_above_320'] * 100:4.1f}%  drift {r['max_cross_track_u']:6.1f} u  "
              f"back {r['reverse_frames']}", flush=True)

    best = max(r["peak_max"] for r in rows)
    print(f"\ntoppfart {best:.1f} u/s mot grinden {PEAK_GATE:.0f} — "
          f"{'KLARAR' if best >= PEAK_GATE else 'KLARAR INTE'}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"map": MAP, "start": START, "end": END,
                               "peak_gate_ups": PEAK_GATE, "runs": rows}, indent=1))
    print(f"skrev {OUT}")


if __name__ == "__main__":
    main()
