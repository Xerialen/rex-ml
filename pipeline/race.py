"""Phase 1 training against the owner's cohort gates.

This replaces `ppo.train_one_weighting` for the gate run rather than editing it, so the evidence
`ppo.py` already produced keeps meaning what it meant. Three things are different, and the first two
are corrections to defects that would have capped the old loop no matter how long it ran:

**1. The discount was shorter than the routes.** `ppo.gae` defaults to `gamma = 0.99`. At a 14 ms
tick that is an effective horizon of ~100 ticks — 1.4 s — while these routes are 300–900 ticks long.
An arrival bonus 700 ticks away arrives at the value function multiplied by `0.99 ** 700 ≈ 0.001`:
not small, *absent*. Every previous run was optimising a reward whose terminal term it could not
see. `GAMMA = 0.999` here (horizon ~1000 ticks ≈ 14 s) covers the longest route's budget.

**2. Progress was measured toward the goal in a straight line.** `RewardParts::progress` used to be
the per-tick reduction in Euclidean distance to the endpoint. On `ring_to_ratop` the planned path is
2842 u long between endpoints 725 u apart, so a policy walking the route correctly moves *away* from
the goal in a straight line for much of it and was penalised for the whole stretch. `rex-env` now
reports arclength advanced along the planned path instead; this file's weights assume that.

**3. The reward is scaled so an episode's return is O(10), not O(100).** The old `sprint` shape put
`arrive` at 200 with a 0.25/tick living cost, which — combined with a 0.999 discount — produces
returns in the hundreds and a value loss that swamps the policy gradient. Scale is chosen from the
arithmetic in `RACE`'s comment, not by taste.

The gate is `cohort_routes`: the owner's own route set, ending at the items' origins, graded against
route-lab's median-without-combat plus the 2.0 s band he set on 2026-07-29.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import cohort_routes as C
from . import coverage as CV
from . import ppo
from .ppo import PPOActorCritic, actions_to_env, obs_to_state, _torch, S_SCALE

OUT = Path("/home/benjamin-adm/rex-ml/pipeline/out/race")
MAP = ppo.MAP
TICK_DT = C.TICK_DT
BHOP_GATE_UPS = 320.0

# Horizon ~1000 ticks = 14.0 s of game time — longer than the longest route's episode budget, so a
# terminal arrival is visible from the start of every route. See the module docstring.
GAMMA = 0.999
LAM = 0.95


@dataclass(frozen=True)
class RaceWeights:
    """Per-tick reward terms.

    **Rescaled 2026-07-29 after two 3000-iteration runs measured a mean reward of -0.015..+0.004 for
    their whole length.** The first version was tuned so that running fast netted +0.001/tick, which
    was elegant and was the defect: the entire time signal sat three orders of magnitude below the
    wall penalty and four below the arrival bonus, so the value function had to resolve thousandths
    against noise ten times larger, and never did. A shaping term you cannot measure above the noise
    is not a weak signal, it is no signal.

    The arithmetic now, on a 2600 u route (`progress` is the per-tick reduction in
    `remaining_to_goal`, so it sums to the route's length over a completed episode):

        run it at 400 u/s -> 465 ticks:  progress +26.0   living -23.3   net  +2.7,  plus arrive +20
        run it at 250 u/s -> 743 ticks:  progress +26.0   living -37.2   net -11.2,  plus arrive +20
        never finish      -> 900 ticks:  progress +18.0   living -45.0   net -27.0,  plus timeout -10

    Halving the speed costs 14 reward, against an arrival bonus of 20 and a total episode range of
    about 60. That is a gradient a critic can see. The `progress` sum is fixed by the route's length
    rather than by how the agent runs it, which is exactly what makes `living` the time term: the
    only way to keep more of the progress is to spend fewer ticks collecting it.

    `speed` is kept small and separate. It is not the objective — running fast in the wrong
    direction is not progress — but it is the one term that distinguishes bunny-hopping from
    ground-strafing at the margin, and G1.5 is stated in it.

    `wall` stays small for the same reason as before: zero wall contact is an acceptance criterion
    checked over consecutive runs at evaluation, not a per-tick training signal. At 1.0 it made every
    early run collapse to standing still. (Measured 2026-07-29, the acceptance criterion itself was
    wrong: on six of seven routes every human run in the corpus touches a wall. The gate is now the
    corpus's own p95 — see `pipeline/clearance.py`.)

    `track` is new, and sized against the same 2600 u arithmetic. The environment returns it as 0
    inside a 24 u deadband, falling linearly to -1 at 96 u off the path:

        50 u off the path for a whole 465-tick run -> -10.0
        96 u off for the whole run                 -> -27.9

    That puts a persistent 50 u excursion on a par with halving the speed (-14), against an arrival
    bonus of 20. It exists because `race_v5` ran a median 50 u off the path in the corridor west of
    the SNG mega, where the path's own margin to a 200 u drop was 8 u, and lost all 48 of 48
    episodes there. Nothing in the reward had ever asked it to stay on the path.
    """

    progress: float = 0.010
    speed: float = 0.005
    wall: float = 0.010
    timeout: float = 10.0
    arrive: float = 20.0
    living: float = 0.050
    track: float = 0.0        # measured 2026-07-29: penalising path deviation punishes strafe-jumping itself

    def vec(self) -> np.ndarray:
        # column order matches rex_env's RewardParts:
        # (progress, speed, wall, timeout, arrive, track)
        return np.array([self.progress, self.speed, -abs(self.wall), -abs(self.timeout),
                         self.arrive, -abs(self.track)], dtype=np.float32)


RACE = RaceWeights()

# `wall` comes back from the environment as -1.0 on a contact tick and `timeout` as -1.0 at the
# deadline, so both weights above are applied with an explicit sign flip in `vec()` — a positive
# weight on a negative signal is a penalty, and writing it as `-abs(...)` makes a sign typo in the
# dataclass unable to turn a penalty into a bonus.


def _teleport_dependent() -> set[str]:
    """Routes whose planned mesh path is so much longer than the straight line between endpoints
    that the human's own route must be using a connection the mesh does not model.

    Measured 2026-07-29 (`evidence/f1_route_geometry.json`): `sngspawn_*_to_quad` plan 6772 / 6190 u
    between endpoints 1908 / 1862 u apart and are gated at 4.27 s, which would demand ~1586 u/s —
    about five times what QuakeWorld permits. `quad_to_ra` plans 5064 u against 1248 u straight and
    needs 565 u/s sustained. The SNG spawns are literally named for the teleporter next to them.

    These are excluded from training until teleport links exist in the mesh *and* teleport triggers
    exist in the physics. Excluding them is recorded here and reported in the results rather than
    done quietly: a silently skipped route reads exactly like a route we passed.
    """
    return {"sngspawn_a_to_quad", "sngspawn_b_to_quad", "quad_to_ra"}


# `quad_to_ra` is excluded from *navmesh* training only. Its mesh path is 5064 u against a 1248 u
# straight line and would need 565 u/s sustained to make an 8.96 s gate — but a human ran it in
# 6.705 s over 3176 u without a rocket, and that track is available. On human geometry the route is
# trainable, so it must not be silently dropped there.
_NO_HUMAN_GEOMETRY = {"sngspawn_a_to_quad", "sngspawn_b_to_quad"}


def training_routes(include_teleport_dependent: bool = False, human_k: int = 0) -> list[C.CohortRoute]:
    skip = _NO_HUMAN_GEOMETRY if human_k else _teleport_dependent()
    if include_teleport_dependent:
        skip = set()
    return [r for r in C.ROUTES if r.name not in skip]


PATHS_DIR = Path("/home/benjamin-adm/rex-ml/pipeline/out/paths")

# cohort route name -> the route-lab registry file its human paths were extracted into
_REGISTRY_OF = {
    "window_to_rl": "zip-window-to-rl",
    "ralow_to_ratop": "zip-ralow-to-ratop-v2",  # RJ-filterrevisionen 2026-07-30: golvprob i stället for stigningsheuristik
    "lifts_to_sng_mega": "lifts-to-sng-mega",
    "quad_to_ra": "quad-to-ra",
    "ring_to_ratop": "zip-ring-to-ratop",
    "sngspawn_a_to_mega": "sngspawn-to-mega",
    "sngspawn_b_to_mega": "sngspawn-to-mega",
    "tunnel_to_ra": "tunnel-to-ra-v2",  # 8 -> 24 banor efter samma revision (evidence/rj_filter_audit.json)
    "sngspawn_a_to_quad": "sngspawn-to-quad",
    "sngspawn_b_to_quad": "sngspawn-to-quad",
    "sng_to_quad": "zip-hex-sng-to-quad",
}


# A human track whose first point is further than this from `Route.start` is another spawn's line,
# not a run of this route. Measured 2026-07-30 (`evidence/sngspawn_regression.json`): the
# `sngspawn-to-mega` registry's 24 tracks ALL start at spawn a (-880,-232,-16), 512 u from spawn b
# (-632,-680,-16), so race_v8 never trained a single sngspawn_b episode from spawn b while its log
# reported "sngspa b 80 %" — measured on spawn-a geometry. 96 u is ~4x the arrive box and well under
# any two spawn points' separation.
START_TOL_U = 96.0
_WARNED_WRONG_START: set[str] = set()


def human_paths_for(route: C.CohortRoute, k: int) -> list[dict]:
    """Up to `k` human runs of this route, fastest first, from `human_paths.py`'s extraction.

    Empty if the route has no usable human geometry — `sngspawn_*_to_quad` is the case, where every
    candidate run contains a position jump larger than any player movement, i.e. the teleporter.
    Tracks that do not start at this route's own start (within `START_TOL_U`) are dropped: a
    registry may pool several spawn points, and a wrong-spawn line trains a different route while
    reporting this one's name.
    """
    reg = _REGISTRY_OF.get(route.name)
    f = PATHS_DIR / f"{reg}.json" if reg else None
    if not f or not f.exists():
        return []
    paths = json.loads(f.read_text()).get("paths", [])
    ok = [p for p in paths if math.dist(p["path"][0], route.start) <= START_TOL_U]
    if len(ok) < len(paths) and route.name not in _WARNED_WRONG_START:
        _WARNED_WRONG_START.add(route.name)
        bad = next(p for p in paths if math.dist(p["path"][0], route.start) > START_TOL_U)
        print(f"human_paths_for({route.name}): dropped {len(paths) - len(ok)}/{len(paths)} tracks "
              f"starting >{START_TOL_U:.0f} u from route start {route.start} "
              f"(e.g. track[0]={bad['path'][0]})"
              + ("" if ok else " — no spawn-correct tracks, falling back to navmesh geometry"),
              flush=True)
    return ok[:k]


class Roller:
    """One `PyVecEnv` per route (or per human path, in human-geometry mode), all stepped every tick
    and served by a single forward pass over the concatenated batch.

    Two geometries, chosen by `human_k`:

      * `human_k == 0` — one environment per route, running the **navmesh's** planned path.
      * `human_k > 0`  — `human_k` environments per route, each running a different **human** run's
        recorded track, **plus one environment running the navmesh's planned path**, with
        `n_per_route` split between them. Several tracks rather than one so the policy learns the
        route rather than one player's particular line through it, and because a single track's
        start state is one sample of where the binding fired. The navmesh env rides in the same
        batch because it is the geometry every strict evaluation builds: race_v8, trained on human
        lines alone, logged 77-80 % arrival while scoring 0/48 on the navmesh env — a line-
        overfitted follower, not a route policy (`evidence/sngspawn_regression.json`). Exception:
        routes in `_teleport_dependent()` get no navmesh env here either — their mesh path needs a
        teleporter the mesh does not model, exactly as in navmesh-only mode.

    In human-geometry mode a route with no usable human track falls back to its navmesh path rather
    than vanishing from the batch — a route that silently left the training set would read, in the
    results, exactly like a route we trained on and passed.
    """

    def __init__(self, routes: list[C.CohortRoute], n_per_route: int, dev: str, human_k: int = 0):
        import rex_env
        self.torch, _ = _torch()
        self.dev = dev
        self.routes = []          # one entry per environment, so index i names env i's route
        self.envs = []
        self.geometry = []        # 'navmesh' | 'human:<demo_key>@<duration_s>'
        self.route_of_env = []    # env index -> index into the caller's `routes`
        self.has_restarts = []    # env index -> whether it has recorded states to restart from
        self.dev = dev

        sizes = []
        for ri, r in enumerate(routes):
            tracks = human_paths_for(r, human_k) if human_k else []
            if tracks:
                add_nav = r.name not in _teleport_dependent()
                per = max(1, n_per_route // (len(tracks) + (1 if add_nav else 0)))
                for tr in tracks:
                    self.envs.append(rex_env.PyVecEnv.from_path(
                        MAP, [tuple(p) for p in tr["path"]], per, C.ARRIVE_BOX, r.max_ticks))
                    self.routes.append(r)
                    self.route_of_env.append(ri)
                    self.geometry.append(f"human:{tr['demo_key']}@{tr['duration_s']}")
                    sizes.append(per)
                    rs = np.asarray(tr.get("restart_states") or [], dtype=np.float32)
                    if rs.size:
                        self.envs[-1].set_restarts(rs, 0.0, 0.92)
                        self.has_restarts.append(True)
                    else:
                        self.has_restarts.append(False)
                if add_nav:
                    self._add_navmesh_env(rex_env, r, ri, per, sizes)
            else:
                self._add_navmesh_env(rex_env, r, ri, n_per_route, sizes)

        self.base_routes = routes
        self.n_per_env = sizes
        self.path_len = [e.path_len for e in self.envs]
        self.obs_np = [e.reset() for e in self.envs]
        acc = 0
        self.slices = []
        for s in sizes:
            self.slices.append(slice(acc, acc + s))
            acc += s
        self.total_n = acc
        self.n = n_per_route
        # Episode bookkeeping for the live arrival/time readout during training. `ticks` counts the
        # current episode's length per slot; a slot that finishes is auto-reset by the environment,
        # so the counter is zeroed on the same tick the outcome is recorded.
        self.ticks = [np.zeros(s, dtype=np.int64) for s in sizes]
        # Accumulated per *base route*, not per environment, so the readout reports one line per
        # route whether that route is running one navmesh path or eight human tracks.
        self.done_times = [[] for _ in routes]     # arrival times, seconds
        self.done_outcomes = [[] for _ in routes]  # 'arrived' | 'timeout' | 'void'

    def _add_navmesh_env(self, rex_env, r: C.CohortRoute, ri: int, n: int, sizes: list[int]):
        self.envs.append(rex_env.PyVecEnv(MAP, r.start, r.target, n, C.ARRIVE_BOX, r.max_ticks))
        self.routes.append(r)
        self.route_of_env.append(ri)
        self.geometry.append("navmesh")
        sizes.append(n)
        # A navmesh env has no recorded states of its own, but the human runs of the same route
        # were run through the same rooms — their states are still in-distribution places to
        # restart, even though the path being followed is the mesh's. (`human_paths_for` filters
        # by start point, so a route with only wrong-spawn tracks pools nothing here.)
        pooled = np.asarray([st for t in human_paths_for(r, 24)
                             for st in (t.get("restart_states") or [])], dtype=np.float32)
        if pooled.size:
            self.envs[-1].set_restarts(pooled, 0.0, 0.92)
            self.has_restarts.append(True)
        else:
            self.has_restarts.append(False)

    def step(self, ac, sample: bool = True):
        torch = self.torch
        obs_cat = np.concatenate(self.obs_np, axis=0)
        obs_t = obs_to_state(obs_cat, torch, self.dev)
        with torch.no_grad():
            if sample:
                ac_tuple, logp, _, value = ac.act(obs_t)
            else:
                f_logit, s_logit, yaw_mean, jump_logit = ac.actor(obs_t)
                ac_tuple = (f_logit.argmax(-1), s_logit.argmax(-1), yaw_mean.squeeze(-1),
                            (jump_logit.squeeze(-1) > 0).float())
                logp = torch.zeros(obs_t.shape[0], device=self.dev)
                value = ac.critic(obs_t).squeeze(-1)
        actions_np = actions_to_env(ac_tuple)

        parts_all, dones_all = [], []
        for i, env in enumerate(self.envs):
            o, parts, dones = env.step(actions_np[self.slices[i]])
            self.obs_np[i] = o
            parts = np.array(parts, copy=True)
            dones = np.array(dones, copy=True)
            self.ticks[i] += 1
            if dones.any():
                ri = self.route_of_env[i]
                fin = np.flatnonzero(dones)
                for j in fin:
                    if parts[j, 4] > 0:
                        self.done_outcomes[ri].append("arrived")
                        self.done_times[ri].append(self.ticks[i][j] * TICK_DT)
                    elif parts[j, 3] < 0:
                        self.done_outcomes[ri].append("timeout")
                    else:
                        self.done_outcomes[ri].append("void")
                self.ticks[i][fin] = 0
            parts_all.append(parts)
            dones_all.append(dones)
        return obs_t, ac_tuple, logp, value, np.concatenate(parts_all), np.concatenate(dones_all)

    def set_restart_window(self, lo: float, hi: float, prob: float) -> None:
        for e in self.envs:
            e.set_restart_window(lo, hi, prob)

    def drain_stats(self) -> list[dict]:
        """Per-route episode outcomes since the last call, then reset the accumulators."""
        rows = []
        for i, r in enumerate(self.base_routes):
            outs = self.done_outcomes[i]
            times = np.array(self.done_times[i], dtype=np.float64)
            n = len(outs)
            rows.append(dict(
                name=r.name, episodes=n,
                arrival_rate=float(sum(o == "arrived" for o in outs) / n) if n else 0.0,
                median_s=float(np.median(times)) if times.size else None,
                best_s=float(times.min()) if times.size else None,
                gate_s=r.gate_s, pass_s=r.pass_s,
            ))
            self.done_outcomes[i] = []
            self.done_times[i] = []
        return rows


PROBE_EVERY = 100   # iterations between in-training strict probes; also runs at it == 1


class StrictProbe:
    """A miniature of the strict protocol, run during training: sampled episodes on the NAVMESH
    env from each route's TRUE start, decoded exactly as `strict_eval.run` decodes — categorical
    forward/side, yaw mean (not a Normal sample), Bernoulli jump from the raw logit (no jump
    floor) — and with no restart states, so every episode begins where every evaluation begins.

    Exists because race_v8's training log reported 77-80 % arrival for its whole run while the
    strict protocol scored it 0/48: the two numbers were measured on different `Route.path`
    geometries, and nothing in the log could show it (`evidence/sngspawn_regression.json`,
    `training_vs_strict_discrepancy`). This puts the strict-geometry number in the same log, so the
    rollout curve and the probe curve diverging IS the line-overfit signal, at iteration N instead
    of after 2500. Teleport-dependent routes are excluded — their navmesh path is not runnable, so
    a probe on it measures the mesh's defect, not the policy."""

    def __init__(self, routes: list[C.CohortRoute], n: int, dev: str):
        import rex_env
        self.torch, _ = _torch()
        self.dev = dev
        self.n = n
        self.routes = [r for r in routes if r.name not in _teleport_dependent()]
        self.envs = [rex_env.PyVecEnv(MAP, r.start, r.target, n, C.ARRIVE_BOX, r.max_ticks)
                     for r in self.routes]

    def run(self, ac) -> list[dict]:
        torch = self.torch
        rows = []
        for r, env in zip(self.routes, self.envs):
            obs = env.reset()
            done = np.zeros(self.n, dtype=bool)
            ticks = np.zeros(self.n, dtype=np.int64)
            arrive_s: list[float] = []
            for _ in range(r.max_ticks + 2):
                t = obs_to_state(obs, torch, self.dev)
                with torch.no_grad():
                    fl, sl, yaw, jl = ac.actor(t)
                    f = torch.distributions.Categorical(logits=fl).sample()
                    s = torch.distributions.Categorical(logits=sl).sample()
                    jz = jl.squeeze(-1)
                    j = (torch.rand_like(jz) < torch.sigmoid(jz)).float()
                a = actions_to_env((f, s, yaw.squeeze(-1), j))
                live = ~done
                ticks[live] += 1
                obs, parts, dones = env.step(a)
                parts = np.asarray(parts)
                for i in np.flatnonzero(live & np.asarray(dones)):
                    done[i] = True
                    if parts[i, 4] > 0:
                        arrive_s.append(float(ticks[i]) * TICK_DT)
                if done.all():
                    break
            rows.append(dict(name=r.name, n=self.n,
                             arrival_rate=len(arrive_s) / self.n,
                             median_s=float(np.median(arrive_s)) if arrive_s else None))
        return rows


def gae(rewards, values, dones, last_value, gamma=GAMMA, lam=LAM):
    return ppo.gae(rewards, values, dones, last_value, gamma=gamma, lam=lam)


def train(iterations: int, n_per_route: int, T: int, epochs: int, minibatches: int,
          lr: float, lr_final: float, ent_coef: float, ent_coef_final: float,
          critic_warmup_iters: int, weights: RaceWeights, routes: list[C.CohortRoute],
          ckpt_name: str, dev: str = "cuda", seed: int = 0, log_every: int = 10,
          resume: Path | None = None, human_k: int = 0,
          jump_floor: float = 0.0, jump_floor_final: float = 0.0,
          jump_bias_target: float | None = None,
          restart_curriculum: bool = True, restart_prob_final: float = 0.35,
          curriculum_end_frac: float = 0.6) -> dict:
    torch, nn = _torch()
    torch.manual_seed(seed)
    OUT.mkdir(parents=True, exist_ok=True)

    ac = PPOActorCritic(dev=dev)
    if resume is not None and Path(resume).exists():
        ac.load(Path(resume))
        print(f"resumed from {resume}", flush=True)
    else:
        ac.load_warm_start(ppo.WARM_START)

    actor_params = list(ac.actor.parameters()) + [ac.log_std]
    opt_actor = torch.optim.Adam(actor_params, lr=lr)
    opt_critic = torch.optim.Adam(list(ac.critic.parameters()), lr=lr)

    roller = Roller(routes, n_per_route, dev, human_k=human_k)
    # The strict-geometry arrival % is logged next to the rollout arrival % every PROBE_EVERY
    # iterations (and at it 1, as the resumed checkpoint's baseline) — see StrictProbe.
    probe = StrictProbe(routes, n=16, dev=dev)

    # Recalibrate the behaviour-cloned jump head before the first rollout. Measured on this
    # environment's own states, the warm start emits a jump logit of -6.10 — p = 0.002 — against a
    # human corpus base rate of 6.6 % over 29,899,266 usercmd ticks. The head is also flat (-6.10 on
    # the ground, -5.60 in the air), so it carries no information about *when* to jump that a shift
    # could destroy; all it carries is a level, and the level is wrong by a factor of thirty.
    # Shifting the output bias so the mean probability starts at `jump_bias_target` leaves every
    # weight untouched and lets PPO learn the timing from data instead of from a broken prior.
    if jump_bias_target is not None and resume is None:
        with torch.no_grad():
            obs0 = obs_to_state(np.concatenate(roller.obs_np, axis=0), torch, dev)
            z = ac.actor(obs0)[3]
            before = float(torch.sigmoid(z).mean())
            lo, hi = -20.0, 20.0
            for _ in range(60):  # bisection: no scipy in this venv, and 60 halvings is exact enough
                mid = 0.5 * (lo + hi)
                if float(torch.sigmoid(z + mid).mean()) < jump_bias_target:
                    lo = mid
                else:
                    hi = mid
            delta = 0.5 * (lo + hi)
            ac.actor.jump_head.bias.add_(delta)
            after = float(torch.sigmoid(ac.actor(obs0)[3]).mean())
        print(f"jump head recalibrated: p(jump) {before:.4f} -> {after:.4f} (bias {delta:+.3f})",
              flush=True)

    wvec = weights.vec()
    print(f"routes={[r.name for r in routes]}  n_per_route={n_per_route}  human_k={human_k}  "
          f"envs={len(roller.envs)}  total_slots={roller.total_n}  T={T}  gamma={GAMMA}", flush=True)
    for r, L, g, n in zip(roller.routes, roller.path_len, roller.geometry, roller.n_per_env):
        print(f"  {r.name:22s} {g:28s} path {L:7.0f} u  n={n:5d}  gate {r.gate_s:5.2f}s  "
              f"needs {L / max(r.gate_s, 1e-6):6.0f} u/s average", flush=True)

    log, t0 = [], time.time()
    for it in range(1, iterations + 1):
        frac = (it - 1) / max(1, iterations - 1)
        cur_lr = lr + (lr_final - lr) * frac
        cur_ent = ent_coef + (ent_coef_final - ent_coef) * frac
        # The jump floor is exploration scaffolding, not part of the shipped policy: it anneals to
        # its final value so the last iterations train — and the evaluation grades — the policy's own
        # Bernoulli head, unassisted.
        ac.jump_floor = jump_floor + (jump_floor_final - jump_floor) * frac

        # Reverse curriculum over where episodes begin. `lo` walks from 0.85 of the way along the
        # route down to 0.0 over the first `curriculum_end_frac` of training, so the policy first
        # learns the last stretch — where the arrival bonus is actually reachable — and only then the
        # whole route. `prob` walks from 1.0 down to `restart_prob_final` at the same time, so by the
        # end most episodes begin where every *evaluation* begins: at the route's own start, at rest.
        # Without that second anneal the policy would be trained on a distribution it is not graded
        # on, which is the exact failure this whole mechanism exists to fix.
        if restart_curriculum:
            c = min(1.0, frac / max(curriculum_end_frac, 1e-6))
            lo = 0.75 * (1.0 - c)
            prob = 1.0 + (restart_prob_final - 1.0) * c
            # `hi` stops at 0.92, not 1.0: a state sampled from the last 8 % of the route can sit
            # inside the 70 u arrival box already, and an episode that arrives on tick 0 teaches
            # nothing while counting as a 100 % arrival rate in the readout.
            roller.set_restart_window(lo, 0.92, prob)
        for opt in (opt_actor, opt_critic):
            for g in opt.param_groups:
                g["lr"] = cur_lr

        buf = {k: [] for k in ("obs", "f", "s", "yaw", "jump", "logp", "value", "parts", "dones")}
        for _ in range(T):
            obs_t, ac_tuple, logp, value, parts, dones = roller.step(ac)
            buf["obs"].append(obs_t); buf["f"].append(ac_tuple[0]); buf["s"].append(ac_tuple[1])
            buf["yaw"].append(ac_tuple[2]); buf["jump"].append(ac_tuple[3])
            buf["logp"].append(logp); buf["value"].append(value)
            buf["parts"].append(parts); buf["dones"].append(dones)

        parts_arr = np.stack(buf["parts"], axis=0)                 # (T, N, 5)
        rewards = parts_arr @ wvec - weights.living                # (T, N)
        dones_arr = np.stack(buf["dones"], axis=0).astype(np.float32)
        values_arr = torch.stack(buf["value"], dim=0).detach().cpu().numpy()
        with torch.no_grad():
            last_v = ac.critic(obs_to_state(np.concatenate(roller.obs_np, axis=0), torch, dev)
                               ).squeeze(-1).cpu().numpy()
        adv = gae(rewards, values_arr, dones_arr, last_v)
        ret = adv + values_arr

        obs_all = torch.cat(buf["obs"], dim=0)
        f_all = torch.cat(buf["f"], dim=0); s_all = torch.cat(buf["s"], dim=0)
        yaw_all = torch.cat(buf["yaw"], dim=0); jump_all = torch.cat(buf["jump"], dim=0)
        logp_all = torch.cat(buf["logp"], dim=0)
        adv_t = torch.tensor(adv.reshape(-1), device=dev, dtype=torch.float32)
        ret_t = torch.tensor(ret.reshape(-1), device=dev, dtype=torch.float32)
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

        update_actor = it > critic_warmup_iters
        total = obs_all.shape[0]
        mb = max(1, total // minibatches)
        pl, vl, el, kl = [], [], [], []
        for _ in range(epochs):
            perm = torch.randperm(total, device=dev)
            for k in range(minibatches):
                idx = perm[k * mb:(k + 1) * mb]
                _, new_logp, entropy, new_value = ac.act(
                    obs_all[idx], actions=(f_all[idx], s_all[idx], yaw_all[idx], jump_all[idx]))
                logratio = new_logp - logp_all[idx]
                ratio = logratio.exp()
                surr1 = ratio * adv_t[idx]
                surr2 = ratio.clamp(0.8, 1.2) * adv_t[idx]
                policy_loss = -torch.min(surr1, surr2).mean()
                value_loss = nn.functional.mse_loss(new_value, ret_t[idx])
                ent = entropy.mean()
                loss = (policy_loss - cur_ent * ent) + 0.5 * value_loss

                opt_critic.zero_grad(set_to_none=True)
                if update_actor:
                    opt_actor.zero_grad(set_to_none=True)
                loss.backward()
                nn.utils.clip_grad_norm_(list(ac.critic.parameters()), 1.0)
                if update_actor:
                    nn.utils.clip_grad_norm_(actor_params, 1.0)
                opt_critic.step()
                if update_actor:
                    opt_actor.step()
                pl.append(float(policy_loss.detach())); vl.append(float(value_loss.detach()))
                el.append(float(ent.detach()))
                with torch.no_grad():
                    kl.append(float(((ratio - 1) - logratio).mean()))

        term = parts_arr.reshape(-1, parts_arr.shape[-1]).mean(axis=0)
        entry = dict(it=it, phase="critic_warmup" if not update_actor else "ppo",
                     lr=cur_lr, ent_coef=cur_ent,
                     policy_loss=float(np.mean(pl)), value_loss=float(np.mean(vl)),
                     entropy=float(np.mean(el)), approx_kl=float(np.mean(kl)),
                     reward_mean=float(rewards.mean()),
                     term_progress=float(term[0]), term_speed=float(term[1]),
                     term_wall=float(term[2]), term_timeout=float(term[3]),
                     term_arrive=float(term[4]), term_track=float(term[5]),
                     jump_floor=ac.jump_floor,
                     restart_lo=(0.75 * (1.0 - min(1.0, frac / max(curriculum_end_frac, 1e-6)))
                                 if restart_curriculum else None),
                     jump_rate=float(np.mean([float(x.float().mean()) for x in buf["jump"]])),
                     s=round(time.time() - t0, 1))
        if it == 1 or it % PROBE_EVERY == 0:
            entry["strict_probe"] = probe.run(ac)
            p_hits = [f"{p['name'].split('_to_')[0][:6]}:{p['arrival_rate'] * 100:3.0f}%/"
                      f"{('%.2f' % p['median_s']) if p['median_s'] else '  -  '}"
                      for p in entry["strict_probe"]]
            print(f"[probe it {it:>5}] strict-navmesh sampled n=16 | " + " ".join(p_hits),
                  flush=True)
        if it % log_every == 0 or it == 1:
            entry["routes"] = roller.drain_stats()
            hits = [f"{r['name'].split('_to_')[0][:6]}:"
                    f"{r['arrival_rate'] * 100:3.0f}%/"
                    f"{('%.2f' % r['median_s']) if r['median_s'] else '  -  '}"
                    for r in entry["routes"]]
            print(f"[it {it:>5}/{iterations} {entry['phase']:>13}] rew {entry['reward_mean']:+.4f} "
                  f"vl {entry['value_loss']:8.3f} ent {entry['entropy']:+.3f} kl {entry['approx_kl']:.4f} "
                  f"spd {term[1]:.3f} jmp {entry['jump_rate']:.3f} "
                  f"lo {entry['restart_lo'] if entry['restart_lo'] is None else round(entry['restart_lo'], 2)} "
                  f"{entry['s']:.0f}s | " + " ".join(hits), flush=True)
            ac.save(OUT / ckpt_name, extra=dict(iteration=it, weights=wvec.tolist(),
                                                living=weights.living, gamma=GAMMA,
                                                routes=[r.name for r in routes],
                                                human_k=human_k, geometry=roller.geometry,
                                                width=512, depth=3))
            (OUT / f"train_log_{ckpt_name.replace('.pt', '')}.json").write_text(
                json.dumps(log + [entry], indent=1, default=float))
        log.append(entry)

    ac.save(OUT / ckpt_name, extra=dict(iteration=iterations, weights=wvec.tolist(),
                                        living=weights.living, gamma=GAMMA,
                                        routes=[r.name for r in routes], human_k=human_k,
                                        geometry=roller.geometry, width=512, depth=3))
    (OUT / f"train_log_{ckpt_name.replace('.pt', '')}.json").write_text(
        json.dumps(log, indent=1, default=float))
    print(f"saved {OUT / ckpt_name}", flush=True)
    return dict(ckpt=str(OUT / ckpt_name), log=log)


# ==========================================================================
# evaluation against the owner's gates
# ==========================================================================

def evaluate_route(ac, route: C.CohortRoute, n_episodes: int, dev: str = "cuda",
                   greedy: bool = True, human_path: dict | None = None) -> dict:
    """`n_episodes` independent episodes of one route, scored on each slot's FIRST completed
    episode so a fast route cannot contribute more samples than a slow one.

    `human_path`, when given, grades the policy on that recorded track's geometry instead of the
    navmesh's. Which geometry a number came from is carried in the result row, because a time on a
    1334 u human line and a time on a 2002 u navmesh detour are not the same measurement and must
    never be averaged together."""
    import rex_env
    torch, _ = _torch()
    if human_path is not None:
        env = rex_env.PyVecEnv.from_path(MAP, [tuple(p) for p in human_path["path"]],
                                         n_episodes, C.ARRIVE_BOX, route.max_ticks)
        geometry = f"human:{human_path['demo_key']}@{human_path['duration_s']}"
    else:
        env = rex_env.PyVecEnv(MAP, route.start, route.target, n_episodes, C.ARRIVE_BOX,
                               route.max_ticks)
        geometry = "navmesh"
    path_len = env.path_len
    obs_np = env.reset()

    traces: list[list] = [[] for _ in range(n_episodes)]
    done = np.zeros(n_episodes, dtype=bool)
    ticks = np.zeros(n_episodes, dtype=np.int64)
    finish_tick = np.full(n_episodes, -1, dtype=np.int64)
    outcome = np.array(["running"] * n_episodes, dtype=object)
    wall_hit = np.zeros(n_episodes, dtype=bool)
    speeds: list[list[float]] = [[] for _ in range(n_episodes)]

    for _ in range(route.max_ticks + 5):
        obs_t = obs_to_state(obs_np, torch, dev)
        with torch.no_grad():
            if greedy:
                f_l, s_l, yaw, j_l = ac.actor(obs_t)
                ac_tuple = (f_l.argmax(-1), s_l.argmax(-1), yaw.squeeze(-1),
                            (j_l.squeeze(-1) > 0).float())
            else:
                ac_tuple, _, _, _ = ac.act(obs_t)
        actions_np = actions_to_env(ac_tuple)

        speed_xy = obs_np[:, 3] * S_SCALE[3]
        live = ~done
        ticks[live] += 1
        P = env.origins
        for i in np.flatnonzero(live):
            if speed_xy[i] > 1.0:
                speeds[i].append(float(speed_xy[i]))
            traces[i].append((float(P[i, 0]), float(P[i, 1]), float(P[i, 2])))

        obs_np, parts, dones = env.step(actions_np)
        parts = np.asarray(parts)
        wall_hit |= live & (parts[:, 2] < 0)
        just = live & np.asarray(dones)
        for i in np.flatnonzero(just):
            done[i] = True
            finish_tick[i] = ticks[i]
            outcome[i] = "arrived" if parts[i, 4] > 0 else ("timeout" if parts[i, 3] < 0 else "void")
        if done.all():
            break

    unfinished = ~done
    outcome[unfinished] = "unfinished"
    finish_tick[unfinished] = ticks[unfinished]

    arrived = outcome == "arrived"
    t_s = finish_tick * TICK_DT
    # The effective sample size, computed rather than assumed. Greedy decoding from a fixed start is
    # deterministic: 64 episodes collapse to one trajectory, and every spread statistic below is then
    # a property of the decode rule instead of the policy. Measured before it is reported.
    n_eff = CV.effective_n([np.asarray(t, dtype=np.float32) for t in traces])
    at = t_s[arrived]
    allspd = np.concatenate([np.array(s) for s in speeds if s]) if any(speeds) else np.array([0.0])

    med = float(np.median(at)) if at.size else None
    return {
        "name": route.name,
        "geometry": geometry,
        "path_len_u": round(path_len, 1),
        "n_episodes": n_episodes,
        "gate_s": route.gate_s,
        "pass_s": route.pass_s,
        "owner_s": route.owner_s,
        "arrival_rate": float(arrived.mean()),
        "outcome_counts": {k: int((outcome == k).sum()) for k in sorted(set(outcome.tolist()))},
        "median_s": med,
        "best_s": float(at.min()) if at.size else None,
        "p90_s": float(np.percentile(at, 90)) if at.size else None,
        "delta_vs_gate_s": (round(med - route.gate_s, 3) if med is not None else None),
        "passes_gate": bool(med is not None and med <= route.pass_s and arrived.all()),
        "frac_moving_ticks_above_320ups": float((allspd > BHOP_GATE_UPS).mean()),
        "median_speed_ups": float(np.median(allspd)),
        "wall_contact_episodes": int(wall_hit.sum()),
        "effective_n": n_eff,
    }


def evaluate(ckpt: Path, n_episodes: int = 100, dev: str = "cuda",
             routes: list[C.CohortRoute] | None = None, out_name: str = "eval.json",
             greedy: bool = True, human_k: int = 0) -> dict:
    ac = PPOActorCritic(dev=dev)
    ac.load(Path(ckpt))
    routes = routes if routes is not None else training_routes(human_k=human_k)
    rows = []
    print(f"{'route':22s} {'arr%':>5} {'median':>7} {'best':>7} {'p90':>7} {'gate':>6} "
          f"{'pass<=':>7} {'d':>7} {'>320':>6} {'medspd':>7} {'wall':>5}")
    for r in routes:
        tracks = human_paths_for(r, human_k) if human_k else []
        if tracks:
            # Every track is graded separately and the route's line is the best of them: the policy
            # is one policy, but the tracks are different journeys, and pooling their times would
            # report a number no single run ever achieved.
            per = [evaluate_route(ac, r, n_episodes, dev=dev, greedy=greedy, human_path=t)
                   for t in tracks]
            arrived = [x for x in per if x["median_s"] is not None]
            row = min(arrived, key=lambda x: x["median_s"]) if arrived else per[0]
            # The best track's time is the best time the policy achieved — but its arrival rate is
            # the arrival rate *on that one line*, and reporting it as the route's would be the same
            # kind of true-and-misleading number as passing G1.5 by ground-strafing. A policy that
            # finishes 1 of 8 human lines has not learned the route, it has learned a line. So the
            # route's arrival rate is pooled over every track and episode, and the count of tracks it
            # can finish at all is carried alongside.
            pooled = float(np.mean([x["arrival_rate"] for x in per]))
            row = dict(row,
                       best_track_median_s=row["median_s"],
                       best_track_arrival_rate=row["arrival_rate"],
                       arrival_rate=pooled,
                       tracks_evaluated=len(per),
                       tracks_with_any_arrival=len(arrived),
                       per_track=[{k: x[k] for k in ("geometry", "path_len_u", "arrival_rate",
                                                     "median_s", "best_s")} for x in per])
            # `passes_gate` was computed inside `evaluate_route` against that one track's own
            # all-arrived condition; recompute it against the pooled rate.
            row["passes_gate"] = bool(row["median_s"] is not None
                                      and row["median_s"] <= r.pass_s and pooled >= 1.0)
        else:
            row = evaluate_route(ac, r, n_episodes, dev=dev, greedy=greedy)
        rows.append(row)
        f = lambda v: f"{v:7.2f}" if v is not None else "      -"
        print(f"{r.name:22s} {row['arrival_rate'] * 100:5.1f} {f(row['median_s'])} "
              f"{f(row['best_s'])} {f(row['p90_s'])} {r.gate_s:6.2f} {r.pass_s:7.2f} "
              f"{f(row['delta_vs_gate_s'])} {row['frac_moving_ticks_above_320ups'] * 100:5.1f}% "
              f"{row['median_speed_ups']:7.1f} {row['wall_contact_episodes']:5d}"
              f"  n_eff {row.get('effective_n', '?')}"
              f"{('  tracks %d/%d' % (row['tracks_with_any_arrival'], row['tracks_evaluated'])) if 'tracks_evaluated' in row else ''}"
              f"{'  PASS' if row['passes_gate'] else ''}", flush=True)

    # Coverage is attached to every row before anything is written, and `CV.require` refuses to
    # serialise a row without it. This is the structural half of the 2026-07-29 finding: the numbers
    # were never wrong, they were unqualified — 64 attempts that were one trajectory, and one
    # approach to each target out of the several the map has.
    approaches = {}
    for r in routes:
        key = tuple(r.target)
        if key not in approaches:
            approaches[key] = CV.mesh_approaches(MAP, r.target, n_probes=2500, seed=1)
    for row, r in zip(rows, routes):
        a = approaches[tuple(r.target)]
        CV.attach(row, attempts=row["n_episodes"], distinct=row.get("effective_n", 1),
                  approaches_modelled=a["approaches"], approaches_tested=1,
                  note=f"one start point; the mesh models {a['approaches']} approach(es) to this target")
    print("\n" + CV.banner(rows), flush=True)

    passed = [r["name"] for r in rows if r["passes_gate"]]
    result = {"ckpt": str(ckpt), "n_episodes": n_episodes, "greedy": greedy,
              "tolerance_s": C.TOLERANCE_S, "routes": rows,
              "passed": passed, "n_passed": len(passed), "n_routes": len(rows),
              "excluded_teleport_dependent": sorted(_teleport_dependent())}
    OUT.mkdir(parents=True, exist_ok=True)
    CV.require(rows, OUT / f"rows_{out_name}")
    (OUT / out_name).write_text(json.dumps(result, indent=1))
    print(f"\n{len(passed)}/{len(rows)} routes inside the owner's band; wrote {OUT / out_name}")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["train", "eval", "geometry"])
    ap.add_argument("--iterations", type=int, default=1500)
    ap.add_argument("--n-per-route", type=int, default=1024)
    ap.add_argument("--T", type=int, default=64)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--minibatches", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--lr-final", type=float, default=5e-5)
    ap.add_argument("--ent-coef", type=float, default=0.010)
    ap.add_argument("--ent-coef-final", type=float, default=0.001)
    ap.add_argument("--critic-warmup", type=int, default=10)
    ap.add_argument("--ckpt", default="race.pt")
    ap.add_argument("--resume", default=None)
    ap.add_argument("--n-episodes", type=int, default=100)
    ap.add_argument("--all-routes", action="store_true")
    ap.add_argument("--human-k", type=int, default=0,
                    help="train/grade on this many recorded human tracks per route instead of the "
                         "navmesh's planned path (0 = navmesh)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--jump-floor", type=float, default=0.0,
                    help="minimum jump probability during rollout, annealed to --jump-floor-final")
    ap.add_argument("--jump-floor-final", type=float, default=0.0)
    ap.add_argument("--jump-bias-target", type=float, default=None,
                    help="shift the warm start's jump-head bias so p(jump) starts here")
    ap.add_argument("--no-restart-curriculum", action="store_true",
                    help="always start episodes at the route's own start, at rest (the old behaviour)")
    ap.add_argument("--restart-prob-final", type=float, default=0.35)
    ap.add_argument("--curriculum-end-frac", type=float, default=0.6)
    a = ap.parse_args()

    rts = training_routes(include_teleport_dependent=a.all_routes, human_k=a.human_k)

    if a.cmd == "geometry":
        import rex_env, math
        rows = []
        for r in C.ROUTES:
            e = rex_env.PyVecEnv(MAP, r.start, r.target, 2, C.ARRIVE_BOX, r.max_ticks)
            p = e.path
            rows.append(dict(name=r.name, nodes=len(p), path_len_u=round(e.path_len, 1),
                             euclid_u=round(math.dist(p[0], p[-1]), 1), gate_s=r.gate_s,
                             required_avg_ups=round(e.path_len / r.gate_s, 1),
                             start=r.start, target=r.target, snapped_goal=p[-1]))
            print(rows[-1], flush=True)
        Path("/home/benjamin-adm/rex-ml/evidence").mkdir(exist_ok=True)
        Path("/home/benjamin-adm/rex-ml/evidence/f1_route_geometry.json").write_text(
            json.dumps({"routes": rows}, indent=1))
    elif a.cmd == "train":
        train(iterations=a.iterations, n_per_route=a.n_per_route, T=a.T, epochs=a.epochs,
              minibatches=a.minibatches, lr=a.lr, lr_final=a.lr_final, ent_coef=a.ent_coef,
              ent_coef_final=a.ent_coef_final, critic_warmup_iters=a.critic_warmup,
              weights=RACE, routes=rts, ckpt_name=a.ckpt, seed=a.seed,
              resume=Path(a.resume) if a.resume else None, human_k=a.human_k,
              jump_floor=a.jump_floor, jump_floor_final=a.jump_floor_final,
              jump_bias_target=a.jump_bias_target,
              restart_curriculum=not a.no_restart_curriculum,
              restart_prob_final=a.restart_prob_final,
              curriculum_end_frac=a.curriculum_end_frac)
    elif a.cmd == "eval":
        evaluate(OUT / a.ckpt, n_episodes=a.n_episodes, routes=rts, human_k=a.human_k,
                 out_name=f"eval_{a.ckpt.replace('.pt', '')}.json")
