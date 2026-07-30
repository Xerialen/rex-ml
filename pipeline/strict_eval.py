"""The same routes, graded harder — every weakness the previous protocol was found to have.

What the old evaluation did and why each part of it was too kind:

  * **Greedy decode from one fixed start.** Deterministic, so 64 episodes were one trajectory. p90
    equalled the median on every route, which read as consistency and was an absence of sampling.
    Here the policy's own distribution is sampled, and the effective sample size is measured and
    reported rather than assumed.
  * **One approach per target.** Measured 2026-07-29: the navmesh models 1-4 distinct approaches per
    target and the old test used one. Here episodes start from every modelled approach, and the
    result is reported per approach — a route passes only if it passes from all of them.
  * **Arrival at 70 u horizontal and 64 u vertical.** The live server's own gate is 24 and 48, and
    every arrival under the loose box would have been rejected by it. The server's gate is used.
  * **Wall contact reported but not gating.** Wall contact gates here — but *not* at zero.
    Measured 2026-07-29 against the corpus: on six of the seven cohort routes every single human
    run comes within a unit of a wall, at a median episode-minimum clearance of 0.5 u. Zero wall
    contact is not a property of fast play; it is a threshold nobody had checked, and it would
    reject every human demonstration we own. The gate is the corpus's own upper tail instead —
    a policy's median run may not scrape more than the human p95 for that route — measured on both
    sides with the identical static probe in `pipeline.clearance`, since `pm_step`'s flag cannot be
    evaluated on humans without their usercmds.
  * **Time compared against a median with no interval.** A median over n episodes is an estimate;
    a bootstrap interval is reported so "beat the gate" is a claim with a width.

A route passes only if all of: every episode arrives, from every modelled approach; the median time
is inside the owner's band; and its scraping rate stays inside the corpus's band.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from . import cohort_routes as C
from . import envelope as EV
from . import clearance as CL
from . import coverage as CV
from . import policy as P
from . import race
from . import ratop_gate as RG

OUT = Path("/home/benjamin-adm/rex-ml/pipeline/out/strict")
BOOT = 2000


def _approach_starts(route: C.CohortRoute, approaches: dict, per: int = 3) -> list[tuple]:
    """A start point for each modelled approach: points on the routes that come in that way.

    The route's own start is always included, so the strict result stays comparable with the old one
    rather than being a different measurement wearing the same name.
    """
    starts = [tuple(route.start)]
    for c in approaches.get("centres", []):
        starts.append(tuple(c["centre"]))
    return starts[:1 + per]


def run(actor, route: C.CohortRoute, start: tuple, n: int, dev: str = "cuda",
        greedy: bool = False, cloud=None, env_band: float | None = None) -> dict:
    import rex_env
    try:
        env = rex_env.PyVecEnv(race.MAP, start, route.target, n, C.ARRIVE_BOX, route.max_ticks)
    except Exception as e:                                        # noqa: BLE001
        return {"start": list(start), "error": str(e)}
    obs = env.reset()
    done = np.zeros(n, bool)
    ticks = np.zeros(n, np.int64)
    outcome = np.array(["unfinished"] * n, dtype=object)
    wall = np.zeros(n, bool)
    speeds: list[list[float]] = [[] for _ in range(n)]
    air = np.zeros(n, np.int64)
    traces: list[list] = [[] for _ in range(n)]

    for _ in range(route.max_ticks + 2):
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
        live = ~done
        sp = obs[:, 3] * P.S_SCALE[3]
        Pp = env.origins
        for i in np.flatnonzero(live):
            ticks[i] += 1
            if sp[i] > 1.0:
                speeds[i].append(float(sp[i]))
            if obs[i, 8] < 0.5:
                air[i] += 1
            # Column 4 is the ground flag, kept so the RA-top manoeuvre gate can cut the episode
            # into airborne segments; columns 0-3 are unchanged for every older consumer.
            traces[i].append((float(Pp[i, 0]), float(Pp[i, 1]), float(Pp[i, 2]), float(sp[i]),
                              float(obs[i, 8] >= 0.5)))
        obs, parts, dones = env.step(a)
        parts = np.asarray(parts)
        wall[live] |= parts[live, 2] < 0
        for i in np.flatnonzero(live & np.asarray(dones)):
            done[i] = True
            outcome[i] = ("arrived" if parts[i, 4] > 0
                          else ("timeout" if parts[i, 3] < 0 else "void"))
        if done.all():
            break

    arrived = outcome == "arrived"
    # Scraping measured with the same static probe used on the corpus, on moving ticks only, so the
    # two sides of the comparison are the same measurement rather than two things sharing a name.
    moving = []
    for t in traces:
        a_ = np.asarray(t, np.float32) if t else np.zeros((0, 4), np.float32)
        a_ = a_[a_[:, 3] >= CL.MOVING_UPS]
        if len(a_):
            moving.append(a_)
    scrape = CL.episode_scrape_rates(moving) if moving else []
    # How far off the corpus's own braid of lines the episodes stray. Added 2026-07-30 after the
    # owner found that the "passing" window_to_rl runs never go through the window: arrival and time
    # graded a 350 u eastern detour no human has ever taken as a pass.
    tr3 = [np.asarray(t, np.float32)[:, :3] for t in traces if t]
    env_d = EV.episode_max_dists(tr3, cloud, join_band_u=env_band) \
        if cloud is not None and tr3 else []
    # The RA-top edge jump, where the route requires one. Added 2026-07-30 after
    # evidence/ratop_edge_jump.json measured that the envelope cannot fail the go-around (the
    # cloud covers the corridor, 43-63 u vs bands of 48-111 u), so the requirement is the
    # manoeuvre itself: one airborne segment over >=96 u of void, human takeoff to human landing.
    man_rate, man_gate, man_worst = None, None, None
    if route.name in RG.MANOEUVRE_GATES:
        checks = []
        for i in np.flatnonzero(arrived):
            tr = np.asarray(traces[i], np.float32)
            if len(tr):
                checks.append(RG.check(route.name, tr[:, :3], tr[:, 4] > 0.5, tr[:, 3]))
        if checks:
            ex = [c["executed"] for c in checks]
            man_rate = round(float(np.mean(ex)), 3)
            man_gate = bool(all(ex))
            worst = [c["best"]["worst_u"] for c in checks if c["best"] is not None]
            man_worst = round(max(worst), 1) if worst else None
    t_s = ticks * C.TICK_DT
    at = t_s[arrived]
    allsp = np.concatenate([np.array(x) for x in speeds if x]) if any(speeds) else np.array([0.0])
    rng = np.random.default_rng(0)
    if at.size:
        boots = np.array([np.median(rng.choice(at, at.size)) for _ in range(BOOT)])
        ci = [round(float(np.percentile(boots, 2.5)), 3), round(float(np.percentile(boots, 97.5)), 3)]
    else:
        ci = [None, None]
    return {
        "start": [round(v, 1) for v in start],
        "n": n,
        "arrival_rate": float(arrived.mean()),
        "median_s": float(np.median(at)) if at.size else None,
        "median_ci95": ci,
        "p90_s": float(np.percentile(at, 90)) if at.size else None,
        "worst_s": float(at.max()) if at.size else None,
        "wall_contact_episodes": int(wall.sum()),
        "scrape_median": round(float(np.median(scrape)), 4) if scrape else None,
        "scrape_p95": round(float(np.percentile(scrape, 95)), 4) if scrape else None,
        "envelope_median_u": round(float(np.median(env_d)), 1) if env_d else None,
        "envelope_p95_u": round(float(np.percentile(env_d, 95)), 1) if env_d else None,
        "manoeuvre_rate": man_rate,
        "manoeuvre_gate": man_gate,
        "manoeuvre_worst_u": man_worst,
        "frac_airborne": round(float(air.sum() / max(ticks.sum(), 1)), 3),
        "frac_above_320": round(float((allsp > 320).mean()), 3),
        "median_speed_ups": round(float(np.median(allsp)), 1),
        "effective_n": CV.effective_n(
            [np.asarray(t, dtype=np.float32)[:, :3] for t in traces if t]),
        "outcomes": {k: int((outcome == k).sum()) for k in sorted(set(outcome.tolist()))},
    }


def evaluate(ckpt: Path, n: int, dev: str = "cuda", greedy: bool = False,
             out_name: str = "strict.json") -> dict:
    ck = torch.load(ckpt, map_location=dev, weights_only=False)
    actor = P.make_disc_actor(14, ck.get("width", 512), ck.get("depth", 3))().to(dev)
    actor.load_state_dict(ck["actor"])
    actor.eval()

    band = CL.load_band()
    ev_band = EV.load_band()
    rows = []
    print(f"{'rutt':22s} {'ingång':>7} {'arr%':>6} {'median':>7} {'ci95':>15} {'p90':>7} "
          f"{'värsta':>7} {'skrap':>7} {'band':>7} {'hölje':>7} {'ev.band':>7} {'luft%':>6} "
          f"{'n_eff':>6} {'manöv':>7}")
    for r in race.training_routes():
        ap = CV.mesh_approaches(race.MAP, r.target, n_probes=2500, seed=1)
        cloud = EV.route_cloud(r.name)
        per_start = []
        for k, st in enumerate(_approach_starts(r, ap)):
            res = run(actor, r, st, n, dev=dev, greedy=greedy, cloud=cloud,
                      env_band=ev_band.get(r.name))
            if "error" in res:
                print(f"{r.name:22s} {k:7d}   {res['error'][:48]}")
                continue
            per_start.append(res)
            fm = lambda v: f"{v:7.2f}" if v is not None else "      -"
            pct = lambda v: f"{v * 100:6.2f}%" if v is not None else "      -"
            print(f"{r.name:22s} {k:7d} {res['arrival_rate'] * 100:6.1f} {fm(res['median_s'])} "
                  f"{str(res['median_ci95']):>15} {fm(res['p90_s'])} {fm(res['worst_s'])} "
                  f"{pct(res['scrape_median'])} {pct(band.get(r.name)):>7} "
                  f"{res['envelope_median_u'] if res['envelope_median_u'] is not None else '-':>7} "
                  f"{ev_band.get(r.name, '-'):>7} "
                  f"{res['frac_airborne'] * 100:5.1f}% {res['effective_n']:6d} "
                  f"{pct(res['manoeuvre_rate'])}", flush=True)
        if not per_start:
            continue
        meds = [x["median_s"] for x in per_start if x["median_s"] is not None]
        scr = [x["scrape_median"] for x in per_start if x["scrape_median"] is not None]
        row = {
            "name": r.name, "gate_s": r.gate_s, "pass_s": r.pass_s, "owner_s": r.owner_s,
            "starts_tested": len(per_start), "approaches_modelled": ap["approaches"],
            "arrival_rate_min": min(x["arrival_rate"] for x in per_start),
            "median_worst_start_s": max(meds) if meds else None,
            "wall_contact_total": sum(x["wall_contact_episodes"] for x in per_start),
            "scrape_worst_start": max(scr) if scr else None,
            "scrape_band_p95": band.get(r.name),
            "envelope_worst_start_u": max((x["envelope_median_u"] for x in per_start
                                           if x["envelope_median_u"] is not None), default=None),
            "envelope_band_u": ev_band.get(r.name),
            "manoeuvre_gated": r.name in RG.MANOEUVRE_GATES,
            "manoeuvre_rate_min": min((x["manoeuvre_rate"] for x in per_start
                                       if x["manoeuvre_rate"] is not None), default=None),
            "effective_n_min": min(x["effective_n"] for x in per_start),
            "per_start": per_start,
        }
        row["inside_corpus_scrape_band"] = bool(
            row["scrape_worst_start"] is not None and row["scrape_band_p95"] is not None
            and row["scrape_worst_start"] <= row["scrape_band_p95"])
        row["inside_corpus_envelope"] = bool(
            row["envelope_worst_start_u"] is not None and row["envelope_band_u"] is not None
            and row["envelope_worst_start_u"] <= row["envelope_band_u"])
        # The manoeuvre requirement fails the route if ANY arrived episode skipped the edge jump —
        # same spirit as the other gates: a line no human takes is a fail even if it is fast.
        # Ungated routes pass vacuously; a gated route with no arrivals is already failed by the
        # arrival gate, so only an explicit skip (manoeuvre_gate is False) fails here.
        row["manoeuvre_gate"] = bool(
            not row["manoeuvre_gated"]
            or not any(x["manoeuvre_gate"] is False for x in per_start))
        row["passes_strict"] = bool(
            row["arrival_rate_min"] >= 1.0
            and row["median_worst_start_s"] is not None
            and row["median_worst_start_s"] <= r.pass_s
            and row["inside_corpus_scrape_band"]
            and row["inside_corpus_envelope"]
            and row["manoeuvre_gate"])
        CV.attach(row, attempts=n * len(per_start), distinct=row["effective_n_min"],
                  approaches_modelled=ap["approaches"], approaches_tested=len(per_start),
                  note="sampled decode; one start per modelled approach")
        rows.append(row)

    print("\n" + CV.banner(rows))
    passed = [r["name"] for r in rows if r["passes_strict"]]
    OUT.mkdir(parents=True, exist_ok=True)
    CV.require(rows, OUT / f"rows_{out_name}")
    (OUT / out_name).write_text(json.dumps(
        {"ckpt": str(ckpt), "n_per_start": n, "greedy": greedy,
         "gate": {"arrive_box": C.ARRIVE_BOX, "arrive_z": C.ARRIVE_Z,
                  "tolerance_s": C.TOLERANCE_S,
                  "wall_scrape_band": "corpus human p95 per route, see evidence/wall_band.json",
                  "manoeuvre": "RA-top routes require the human edge jump per episode, "
                               "see pipeline/ratop_gate.py and evidence/ratop_edge_jump.json"},
         "passed": passed, "n_passed": len(passed), "n_routes": len(rows), "routes": rows},
        indent=1, default=float))
    print(f"\n{len(passed)}/{len(rows)} rutter klarar det strikta provet; "
          f"skrev {OUT / out_name}")
    return {"passed": passed, "rows": rows}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("ckpt")
    ap.add_argument("--n", type=int, default=48)
    ap.add_argument("--greedy", action="store_true")
    ap.add_argument("--out", default="strict.json")
    a = ap.parse_args()
    evaluate(Path(a.ckpt), a.n, greedy=a.greedy, out_name=a.out)
