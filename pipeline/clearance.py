"""How close to a wall does a *fast human* actually run — and is "zero wall contact" a real gate?

The strict protocol rejects any episode in which `pm_step` reports a non-floor plane contact. That
criterion came from the acceptance protocol, but nothing had ever checked it against the corpus. It
is worth checking, because in QuakeWorld a strafing player who is not touching walls is usually a
player taking the wide line: hugging the inside of a corner is how the fast route is run.

`pm_step`'s wall flag cannot be evaluated on humans — that would need their usercmds, which the
protocol forbids as an input. So both sides are measured by the same *static* property instead:

    clearance(P) = the smallest lateral distance d at which the player hull can no longer stand,
                   probed in 8 horizontal directions and capped at CAP.

It depends only on where the player is, not on how densely the demo was sampled, so a human at 29 Hz
and a bot at 77 Hz are compared on equal terms. A player whose hull is within a unit or two of a wall
while moving parallel to it will clip that plane on essentially every tick, so the low tail of this
distribution is what the wall-contact flag is reporting.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from . import cohort_routes as C  # noqa: F401  (route constants; imported for parity with callers)
from . import race

# A ladder rather than a bisection: one batched call answers every point at every rung, and the
# rungs are dense where the answer matters (a hull that clears 8 u is not scraping anything).
LADDER = np.array([0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0], np.float32)
CAP = float(LADDER[-1])
N_DIRS = 8
MOVING_UPS = 100.0  # below this a human is standing, aiming or waiting — not running a route


def _dirs() -> np.ndarray:
    a = np.arange(N_DIRS, dtype=np.float32) * (2.0 * np.pi / N_DIRS)
    return np.stack([np.cos(a), np.sin(a), np.zeros_like(a)], 1)


def clearance(points: np.ndarray, map_path: str = race.MAP, chunk: int = 400_000) -> np.ndarray:
    """Minimum lateral clearance per point, in units, capped at :data:`CAP`.

    Points at which the hull cannot stand at all return ``nan`` — a human sample that lands inside
    geometry is a sampling artefact, not a zero-clearance run, and must not be counted as either.
    """
    import rex_env

    pts = np.ascontiguousarray(points, np.float32)
    n = len(pts)
    here = rex_env.PyVecEnv.points_open(map_path, pts)

    dirs = _dirs()
    probes = (pts[:, None, None, :] + dirs[None, :, None, :] * LADDER[None, None, :, None])
    probes = probes.reshape(-1, 3).astype(np.float32)

    open_ = np.empty(len(probes), bool)
    for i in range(0, len(probes), chunk):
        open_[i:i + chunk] = rex_env.PyVecEnv.points_open(map_path, probes[i:i + chunk])
    open_ = open_.reshape(n, N_DIRS, len(LADDER))

    # First rung that is blocked, per direction; a direction that clears every rung reports CAP.
    blocked = ~open_
    first = np.where(blocked.any(2), LADDER[blocked.argmax(2)], CAP)
    out = first.min(1).astype(np.float32)
    out[~here] = np.nan
    return out


def human_points(route_names: list[str] | None = None) -> dict[str, list[np.ndarray]]:
    """Fast-moving human samples per cohort route, kept split per run: ``(N, 4)`` of ``x,y,z,speed``.

    Runs stay separate because the gate's unit is the episode, not the tick: "no episode touches a
    wall" is a different question from "few ticks are near a wall", and only the first is the gate.
    """
    out: dict[str, list[np.ndarray]] = {}
    for r in race.training_routes():
        if route_names and r.name not in route_names:
            continue
        runs = []
        for rec in race.human_paths_for(r, 10_000):
            s = np.asarray(rec["restart_states"], np.float32)
            if not len(s):
                continue
            sp = np.linalg.norm(s[:, 3:5], axis=1)
            a = np.column_stack([s[:, :3], sp])
            a = a[a[:, 3] >= MOVING_UPS]
            if len(a):
                runs.append(a)
        if runs:
            out[r.name] = runs
    return out


def bot_points(ckpt: Path, n: int, dev: str = "cuda") -> dict[str, list[np.ndarray]]:
    """Sampled-decode rollouts of a checkpoint from each route's own start, split per episode."""
    import torch

    from . import policy as P
    from . import strict_eval as SE  # noqa: F401  (kept in step with the grading protocol)

    ck = torch.load(ckpt, map_location=dev, weights_only=False)
    actor = P.make_disc_actor(14, ck.get("width", 512), ck.get("depth", 3))().to(dev)
    actor.load_state_dict(ck["actor"])
    actor.eval()

    import rex_env
    out: dict[str, list[np.ndarray]] = {}
    for r in race.training_routes():
        env = rex_env.PyVecEnv(race.MAP, tuple(r.start), r.target, n, C.ARRIVE_BOX, r.max_ticks)
        obs = env.reset()
        done = np.zeros(n, bool)
        per_ep: list[list] = [[] for _ in range(n)]
        for _ in range(r.max_ticks + 2):
            t = torch.tensor(obs, device=dev, dtype=torch.float32)
            with torch.no_grad():
                fl, sl, yaw, jl = actor(t)
                f = torch.distributions.Categorical(logits=fl).sample()
                s = torch.distributions.Categorical(logits=sl).sample()
                j = (torch.rand_like(jl.squeeze(-1)) < torch.sigmoid(jl.squeeze(-1))).float()
            a = np.stack([(f.cpu().numpy() - 1).astype(np.float32),
                          (s.cpu().numpy() - 1).astype(np.float32),
                          yaw.squeeze(-1).cpu().numpy(), j.cpu().numpy()], 1).astype(np.float32)
            sp = np.linalg.norm(env.velocities[:, :2], axis=1)
            o = env.origins
            for i in np.flatnonzero(~done):
                per_ep[i].append((o[i, 0], o[i, 1], o[i, 2], sp[i]))
            obs, _parts, dones = env.step(a)
            done |= np.asarray(dones)
            if done.all():
                break
        runs = []
        for ep in per_ep:
            if not ep:
                continue
            arr = np.asarray(ep, np.float32)
            arr = arr[arr[:, 3] >= MOVING_UPS]
            if len(arr):
                runs.append(arr)
        out[r.name] = runs
    return out


BAND = Path("/home/benjamin-adm/rex-ml/evidence/wall_band.json")


def load_band() -> dict[str, float]:
    """Per-route ceiling on the near-wall tick rate, taken from the corpus's own upper tail.

    Measured 2026-07-29: on six of seven cohort routes **every** human run comes within a unit of a
    wall, median episode-minimum clearance 0.5 u. "No episode touches a wall" is therefore not a
    property of fast play — no human demonstration in the corpus would pass it. What the corpus does
    support is a bound on *how much* scraping is normal, so that is what gates.
    """
    if not BAND.exists():
        raise FileNotFoundError(
            f"{BAND} saknas — kör `python -m pipeline.clearance` som härleder bandet ur korpusen "
            "innan något betygsätts på väggkontakt")
    return {r["route"]: r["human_p95_gate"] for r in json.loads(BAND.read_text())["routes"]}


def episode_scrape_rates(runs: list[np.ndarray], map_path: str = race.MAP,
                         per_run: int = 150, seed: int = 0) -> list[float]:
    """Fraction of moving ticks within 1 u of a wall, per run, from a subsample of each run's ticks.

    Subsampled because the rate is a proportion and 150 draws pin it to a couple of points —
    far tighter than the spread between the human p50 and p95 the result is compared against.
    """
    rng = np.random.default_rng(seed)
    out = []
    for x in runs:
        pts = x[:, :3]
        if len(pts) > per_run:
            pts = pts[rng.choice(len(pts), per_run, replace=False)]
        c = clearance(pts, map_path)
        v = c[~np.isnan(c)]
        if v.size:
            out.append(float((v < 1.0).mean()))
    return out


def summarise(runs: list[np.ndarray], cls: list[np.ndarray]) -> dict:
    """Tick-level shape of the distribution, plus the episode-level statistic the gate applies."""
    flat = np.concatenate(cls) if cls else np.zeros(0, np.float32)
    v = flat[~np.isnan(flat)]
    if not v.size:
        return {"n": 0, "runs": len(runs)}
    ep_min = np.array([np.nanmin(c) if np.isfinite(c).any() else np.nan for c in cls])
    ok = ~np.isnan(ep_min)
    return {
        "runs": int(ok.sum()),
        "n": int(v.size),
        "unstandable": int(np.isnan(flat).sum()),
        "frac_lt_1": round(float((v < 1.0).mean()), 4),
        "frac_lt_2": round(float((v < 2.0).mean()), 4),
        "frac_lt_4": round(float((v < 4.0).mean()), 4),
        "p5": round(float(np.percentile(v, 5)), 2),
        "median": round(float(np.median(v)), 2),
        # The gate's own unit: an episode fails if it is ever this close to a wall.
        "eps_touch_lt_1": round(float((ep_min[ok] < 1.0).mean()), 4),
        "eps_touch_lt_2": round(float((ep_min[ok] < 2.0).mean()), 4),
        "eps_touch_lt_4": round(float((ep_min[ok] < 4.0).mean()), 4),
        "median_episode_min_clearance": round(float(np.median(ep_min[ok])), 2),
        # Per-run scraping rate. The corpus's own spread is what a defensible gate is built from:
        # a threshold set at the human upper tail asks the bot to be no worse than a fast human,
        # which is the question the protocol was reaching for when it said "never touch a wall".
        "run_frac_lt_1": [round(float(np.mean(c[~np.isnan(c)] < 1.0)), 4)
                          for c in cls if np.isfinite(c).any()],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="pipeline/out/race/race_v5.pt")
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--sample", type=int, default=60_000,
                    help="cap on points per side per route, so one long route cannot dominate")
    ap.add_argument("--out", default="/home/benjamin-adm/rex-ml/evidence/wall_clearance.json")
    a = ap.parse_args()

    rng = np.random.default_rng(0)

    def take(runs: list[np.ndarray]) -> list[np.ndarray]:
        """Cap by whole runs, never by ticks — dropping ticks would break the episode statistic."""
        total = sum(len(x) for x in runs)
        if total <= a.sample or len(runs) <= 1:
            return runs
        keep = max(1, int(len(runs) * a.sample / total))
        idx = rng.choice(len(runs), keep, replace=False)
        return [runs[i] for i in sorted(idx)]

    hp = human_points()
    bp = bot_points(Path(a.ckpt), a.n)

    rows = []
    print(f"{'rutt':22s} {'källa':9s} {'körn':>5} {'n':>7} {'tick<1u':>8} "
          f"{'EP<1u':>7} {'EP<2u':>7} {'EP<4u':>7} {'ep-min':>7}")
    for name in sorted(set(hp) | set(bp)):
        for src, runs in (("människa", hp.get(name)), ("bot", bp.get(name))):
            if not runs:
                continue
            sel = take(runs)
            cls = [clearance(x[:, :3]) for x in sel]
            s = summarise(sel, cls)
            s |= {"route": name, "source": src}
            rows.append(s)
            print(f"{name:22s} {src:9s} {s['runs']:5d} {s['n']:7d} "
                  f"{s['frac_lt_1'] * 100:7.2f}% {s['eps_touch_lt_1'] * 100:6.1f}% "
                  f"{s['eps_touch_lt_2'] * 100:6.1f}% {s['eps_touch_lt_4'] * 100:6.1f}% "
                  f"{s['median_episode_min_clearance']:7.1f}", flush=True)

    # The corpus-derived band, per route, and whether the bot sits inside it.
    by = {(r["route"], r["source"]): r for r in rows}
    band = []
    print(f"\n{'rutt':22s} {'H p50':>7} {'H p95':>7} {'BOT p50':>8} {'BOT p95':>8} {'utfall':>10}")
    for name in sorted({r["route"] for r in rows}):
        h, b = by.get((name, "människa")), by.get((name, "bot"))
        if not h or not b or not h["run_frac_lt_1"] or not b["run_frac_lt_1"]:
            continue
        hv, bv = np.array(h["run_frac_lt_1"]), np.array(b["run_frac_lt_1"])
        gate = float(np.percentile(hv, 95))
        med = float(np.median(bv))
        row = {"route": name, "human_p50": round(float(np.median(hv)), 4),
               "human_p95_gate": round(gate, 4), "bot_p50": round(med, 4),
               "bot_p95": round(float(np.percentile(bv, 95)), 4),
               "inside_human_band": bool(med <= gate)}
        band.append(row)
        print(f"{name:22s} {row['human_p50'] * 100:6.2f}% {gate * 100:6.2f}% "
              f"{med * 100:7.2f}% {row['bot_p95'] * 100:7.2f}% "
              f"{'INNANFÖR' if row['inside_human_band'] else 'utanför':>10}")

    BAND.parent.mkdir(parents=True, exist_ok=True)
    BAND.write_text(json.dumps({
        "derived": "human runs in the dm3 corpus, moving ticks only",
        "statistic": "fraction of moving ticks with lateral hull clearance < 1 u",
        "gate": "a policy's median run must not exceed the human p95 for that route",
        "moving_ups": MOVING_UPS,
        # Corpus only. A verdict about some policy has no business in the file that defines the
        # threshold that policy is judged against.
        "routes": [{k: v for k, v in r.items() if k in ("route", "human_p50", "human_p95_gate")}
                   for r in band],
    }, indent=1))
    print(f"skrev {BAND}")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "question": "is zero wall contact a property of fast human play, or an invented gate?",
        "method": {"probe": "hull1 standable at P + dir*d, 8 dirs", "ladder": LADDER.tolist(),
                   "cap_u": CAP, "moving_ups": MOVING_UPS, "ckpt": a.ckpt, "n_episodes": a.n},
        "corpus_band": band, "rows": rows}, indent=1))
    print(f"\nskrev {out}")


if __name__ == "__main__":
    main()
