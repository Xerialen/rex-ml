"""Record the strict protocol itself, so the page shows the runs the numbers were computed from.

The earlier replay recorded from each route's own start only, which is a looser test than the one
being reported. A page built on that cannot prove a strict-protocol claim — it would show different
runs under the same name. So this drives the *same* protocol as `pipeline.strict_eval`: sampled
decode, one start per modelled approach, the live server's arrival gate (24 u horizontal, 48 u
vertical), 48 episodes per approach.

All 48 episodes are measured; a handful per approach are kept as frames. Storing 1300 trajectories
would be a 16 MB page, and the point of the replays is to be able to look at what a run *was* —
the fastest, the typical, the worst arrival, and a failure where there is one. The statistics in
each record come from the full 48, and every record says so.
"""

from __future__ import annotations

import numpy as np
import torch

from . import clearance as CL
from . import cohort_routes as C
from . import coverage as CV
from . import policy as P
from . import race
from . import strict_eval as SE
from .record_replay import air_segments

BOOT = 2000
KEEP_PER_APPROACH = 5


def _select(times: np.ndarray, arrived: np.ndarray, n_keep: int) -> list[int]:
    """Which episodes to keep frames for: the fastest, the median, the slowest arrival, a failure."""
    keep: list[int] = []
    ai = np.flatnonzero(arrived)
    if ai.size:
        order = ai[np.argsort(times[ai])]
        keep += [int(order[0]), int(order[len(order) // 2]), int(order[-1])]
    fi = np.flatnonzero(~arrived)
    keep += [int(i) for i in fi[:2]]
    seen: list[int] = []
    for i in keep:
        if i not in seen:
            seen.append(i)
    return seen[:n_keep]


def record_approach(actor, route: C.CohortRoute, start: tuple, n: int, band: float | None,
                    dev: str = "cuda") -> dict | None:
    import rex_env

    try:
        env = rex_env.PyVecEnv(race.MAP, start, route.target, n, C.ARRIVE_BOX, route.max_ticks)
    except Exception:                                             # noqa: BLE001
        return None
    obs = env.reset()
    done = np.zeros(n, bool)
    arrived = np.zeros(n, bool)
    ticks = np.zeros(n, np.int64)
    frames: list[list[tuple]] = [[] for _ in range(n)]

    for _ in range(route.max_ticks + 2):
        t = torch.tensor(obs, device=dev, dtype=torch.float32)
        with torch.no_grad():
            fl, sl, yaw, jl = actor(t)
            f = torch.distributions.Categorical(logits=fl).sample()
            s = torch.distributions.Categorical(logits=sl).sample()
            j = (torch.rand_like(jl.squeeze(-1)) < torch.sigmoid(jl.squeeze(-1))).float()
        a = np.stack([(f.cpu().numpy() - 1).astype(np.float32),
                      (s.cpu().numpy() - 1).astype(np.float32),
                      yaw.squeeze(-1).cpu().numpy(), j.cpu().numpy()], 1).astype(np.float32)
        o, v, g, y = env.origins, env.velocities, env.on_ground, env.view_yaws
        sp = np.linalg.norm(v[:, :2], axis=1)
        for i in np.flatnonzero(~done):
            frames[i].append((float(o[i, 0]), float(o[i, 1]), float(o[i, 2]), float(y[i]),
                              bool(g[i] > 0.5), bool(a[i, 3] > 0.5), float(sp[i])))
            ticks[i] += 1
        obs, parts, dn = env.step(a)
        parts = np.asarray(parts)
        ts = env.terminal_states
        for i in np.flatnonzero((~done) & np.asarray(dn)):
            done[i] = True
            arrived[i] = parts[i, 4] > 0
            frames[i].append((float(ts[i, 0]), float(ts[i, 1]), float(ts[i, 2]), float(ts[i, 3]),
                              True, False, float(np.linalg.norm(ts[i, 4:6]))))
            ticks[i] += 1
        if done.all():
            break

    t_s = ticks * C.TICK_DT
    at = t_s[arrived]
    rng = np.random.default_rng(0)
    if at.size:
        boots = np.array([np.median(rng.choice(at, at.size)) for _ in range(BOOT)])
        ci = [round(float(np.percentile(boots, 2.5)), 3), round(float(np.percentile(boots, 97.5)), 3)]
    else:
        ci = [None, None]

    # Scraping over the same moving ticks and the same static probe the band was derived from.
    moving = []
    for fr in frames:
        arr = np.asarray([(x[0], x[1], x[2], x[6]) for x in fr], np.float32)
        arr = arr[arr[:, 3] >= CL.MOVING_UPS]
        if len(arr):
            moving.append(arr)
    scrape = CL.episode_scrape_rates(moving) if moving else []

    return {
        "start": [round(v, 1) for v in start],
        "n": n,
        "arrival_rate": float(arrived.mean()),
        "median_s": round(float(np.median(at)), 3) if at.size else None,
        "median_ci95": ci,
        "worst_s": round(float(at.max()), 3) if at.size else None,
        "scrape_median": round(float(np.median(scrape)), 4) if scrape else None,
        "band_p95": band,
        "frames": frames,
        "arrived": arrived,
        "times": t_s,
    }


def build(base: int, ckpt: str, n: int = 48, dev: str = "cuda",
          keep: int = KEEP_PER_APPROACH) -> tuple[bytes, list[dict]]:
    """The strict protocol, recorded. Returns the frame blob and one record per route+approach."""
    import struct

    ck = torch.load(ckpt, map_location=dev, weights_only=False)
    actor = P.make_disc_actor(14, ck.get("width", 512), ck.get("depth", 3))().to(dev)
    actor.load_state_dict(ck["actor"])
    actor.eval()
    band = CL.load_band()

    blob = bytearray()
    records: list[dict] = []
    tag = ckpt.rstrip(".pt").split("/")[-1]

    for r in race.training_routes():
        ap = CV.mesh_approaches(race.MAP, r.target, n_probes=2500, seed=1)
        starts = SE._approach_starts(r, ap)
        import rex_env
        env0 = rex_env.PyVecEnv(race.MAP, tuple(r.start), r.target, 1, C.ARRIVE_BOX, r.max_ticks)
        path = [list(p) for p in env0.path]
        for k, st in enumerate(starts):
            res = record_approach(actor, r, st, n, band.get(r.name), dev=dev)
            if res is None:
                print(f"  {r.name:22s} ing.{k}  starten går inte att bygga — hoppas över")
                continue
            pick = _select(res["times"], res["arrived"], keep)
            runs = []
            for i in pick:
                fr = res["frames"][i]
                off = base + len(blob)
                for (x, y, z, yaw, og, jmp, spd) in fr:
                    blob += struct.pack("<ffffBff", x, y, z, yaw,
                                        (1 if og else 0) | (2 if jmp else 0), spd, 0.0)
                sp = np.array([q[6] for q in fr], np.float32)
                mv = sp[sp > 1.0]
                runs.append({
                    "count": 1, "attempt_ids": [int(i)],
                    "outcome": "arrived" if res["arrived"][i] else "timeout",
                    "ticks": len(fr), "time_s": round(len(fr) * C.TICK_DT, 3),
                    "wall_contact": False, "offset": off, "n_frames": len(fr),
                    "label": (f"{len(fr) * C.TICK_DT:.2f} s" if res["arrived"][i] else "ingen ankomst"),
                    "note": f"episod {i} av {n}",
                    "median_speed_ups": round(float(np.median(mv)), 1) if mv.size else 0.0,
                    "peak_speed_ups": round(float(sp.max()), 1),
                    "frac_above_320": round(float((mv > 320).mean()), 3) if mv.size else 0.0,
                    "frac_airborne": round(float(np.mean([not q[4] for q in fr])), 3),
                    "jump_presses": int(sum(1 for m in range(1, len(fr))
                                            if fr[m][5] and not fr[m - 1][5])),
                    "segments": air_segments(fr),
                })
            b = band.get(r.name)
            inside = res["scrape_median"] is not None and b is not None and res["scrape_median"] <= b
            passes = res["arrival_rate"] >= 1.0 and res["median_s"] is not None \
                and res["median_s"] <= r.pass_s and inside
            rec = {
                "route": r.name, "map": "dm3", "decode": f"{tag} ing.{k}",
                "geometry": f"strikt prov, ingång {k}, start {res['start']}",
                "attempts": n, "distinct_trajectories": len(runs),
                "arrival_rate": res["arrival_rate"],
                "median_s": res["median_s"], "median_ci95": res["median_ci95"],
                "worst_s": res["worst_s"],
                "scrape_median": res["scrape_median"], "band_p95": b,
                "gate_s": r.gate_s, "pass_s": r.pass_s, "owner_s": r.owner_s,
                "path": path, "goal": list(r.target), "start": list(st),
                "passes_strict": bool(passes),
                "group_label": (
                    f"{tag} ingång {k} — {res['arrival_rate'] * 100:.1f} % ankomst av {n}"
                    + (f", median {res['median_s']:.2f} s (KI {res['median_ci95']})"
                       if res["median_s"] is not None else ", ingen ankomst")
                    + (f", skrap {res['scrape_median'] * 100:.1f} % mot bandets {b * 100:.1f} %"
                       if res["scrape_median"] is not None and b is not None else "")
                    + f" — {'GODKÄND' if passes else 'ej godkänd'}"),
                "runs": runs,
            }
            CV.attach(rec, attempts=n, distinct=len(runs),
                      approaches_modelled=ap["approaches"], approaches_tested=len(starts),
                      note=f"48 episoder mätta, {len(runs)} sparade som bildrutor")
            records.append(rec)
            print(f"  {r.name:22s} ing.{k}  {res['arrival_rate'] * 100:5.1f} %  "
                  f"{str(res['median_s']):>7} s  skrap {res['scrape_median']}  "
                  f"{'GODKÄND' if passes else ''}", flush=True)
    return bytes(blob), records
