"""SPEC F1.2 -- PPO on top of the behaviour-cloned policy.

The environment (`rex_env.PyVecEnv`, a thin PyO3 shell over `rtx_nav::pmove::pm_step_report`)
is done and lives under `rtx/`; this module is the only new code, entirely under `pipeline/`.

Three things live here, matching the spec's three deliverables:

  * `bench`  -- the throughput breakdown the spec demands BEFORE any training conclusion:
    seconds in env.step(), seconds in the policy forward pass, seconds in backward+optimiser,
    for a real PPO iteration at N=4096 and N=16384. See the module docstring on `bench_iteration`
    for what "real" means here and exactly what each bucket counts.
  * `train`  -- PPO (clipped surrogate + GAE), actor warm-started from
    `pipeline/out/policy/actor_disc_3x512.pt` (`policy.make_disc_actor`, depth=3 width=512),
    critic trained from scratch (no warm start exists for a value function). Runs one job per
    `RewardWeights` configuration -- the spec requires >= 3, run separately so each is a clean,
    reproducible checkpoint plus its own reward-term log.
  * `eval`   -- the per-route table: arrival rate, median/p90 completion time, fraction of moving
    ticks above 320 u/s, median horizontal speed, wall-contact episodes, over >= 30 episodes/route,
    reported for every constructible `kind = "goto"` dm3 scenario (excluding `dash_100m` and
    `rj_*`), including routes the policy fails outright.

Action space is the policy's own: 3-way `fwd`, 3-way `side` (`Categorical` over classes
{-1,0,+1}), continuous `dyaw` (`Normal`, warm-started mean = `tanh(yaw_head)*a_scale[2]`, a fresh
learnable state-independent log-std), binary `jump` (`Bernoulli`). This mirrors
`policy.make_disc_actor`'s own forward exactly for the mean/logits, so loading the BC checkpoint's
state dict warm-starts every actor parameter with no shape surprises.
"""

from __future__ import annotations

import argparse
import json
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import policy as P

OUT = Path("/home/benjamin-adm/rex-ml/pipeline/out/ppo")
POLICY_DIR = Path("/home/benjamin-adm/rex-ml/pipeline/out/policy")
MAP = "/home/benjamin-adm/rex-ml/rtx/playground/qw/maps/dm3.bsp"
SCEN_DIR = Path("/home/benjamin-adm/rtx-mltest/testsuite/scenarios/dm3")
WARM_START = POLICY_DIR / "actor_disc_3x512.pt"
TICK_DT = 1.0 / 77.0
BHOP_GATE_UPS = 320.0
HUMAN_REF_UPS = 331.0

S_SCALE = P.S_SCALE
A_SCALE = P.A_SCALE
STATE_COLS = P.STATE_COLS

EXCLUDED_SCENARIOS = {"dash_100m", "rj_pent_to_lifts_to_window_to_quad", "rj_pent_window"}

# The bench route: the exact start/goal `rex-env`'s own test suite and `evidence/f1.1_vecenv.json`
# use, so the throughput numbers here are comparable to that evidence file's rather than being a
# different measurement wearing the same units.
BENCH_START = (-880.0, -232.0, -16.0)
BENCH_GOAL = (-720.0, -232.0, -16.0)


# ==========================================================================
# reward weightings -- data, not constants (SPEC F1.2)
# ==========================================================================

@dataclass(frozen=True)
class RewardWeights:
    progress: float
    speed: float
    wall: float
    timeout: float
    arrive: float

    def vec(self) -> np.ndarray:
        return np.array([self.progress, self.speed, self.wall, self.timeout, self.arrive], dtype=np.float32)


# Matches `rex_env::RewardWeights::default()` exactly (progress 0.01, speed 0.02, wall 1.0,
# timeout 1.0, arrive 10.0) -- the environment's own default is weighting #1, not invented here.
REWARD_WEIGHTINGS = {
    "rtx_default": RewardWeights(progress=0.01, speed=0.02, wall=1.0, timeout=1.0, arrive=10.0),
    # speed's coefficient is the term the owner's finding points at (routes are speed-gated); 10x
    # the default puts it on a scale comparable to `arrive` per-episode rather than a rounding
    # error next to it.
    "speed_emphasis": RewardWeights(progress=0.01, speed=0.20, wall=1.0, timeout=1.0, arrive=10.0),
    # progress and arrive both up, timeout doubled: a policy that dawdles should feel it twice --
    # once every tick it isn't closing distance, once hard at the deadline.
    "arrival_emphasis": RewardWeights(progress=0.05, speed=0.02, wall=1.0, timeout=2.0, arrive=20.0),
    # The three above all keep `wall` at 1.0, and that is why all three collapse to standing still.
    # One contact tick costs as much as fifty ticks of maximum speed, while arrival is unreachable
    # without first surviving the exploration that earns contacts — so a policy that simply stops
    # scores ~0 and beats every policy that moves. The first run proved it: the speed term fell from
    # 0.39 (BC, frozen) to 0.10 within twenty iterations while arrivals stayed at zero.
    #
    # The fix is not to weaken the requirement. Zero wall contacts is an *acceptance* criterion in
    # the owner's protocol — checked over 20 consecutive runs at evaluation — not a per-tick training
    # signal. Penalising contact at a scale that forbids exploration teaches the policy never to
    # try, which is the one behaviour that can never satisfy the criterion either.
    "explore": RewardWeights(progress=0.05, speed=0.20, wall=0.02, timeout=1.0, arrive=20.0),
    # `explore` fixed standing-still and created the opposite failure: the policy runs fast forever
    # and stops arriving. The arithmetic is what matters, not the intuition. Arriving ENDS the
    # episode, so it forfeits every remaining tick of speed reward — about 140 over a 700-tick budget
    # at speed 0.20 — against an arrival bonus of 20. Arrival was actively punished, and the measured
    # run shows exactly that: arrivals appeared around iteration 30 and were gone by 150 while the
    # speed term climbed to 1.01.
    #
    # The deeper hole this exposes: the reward had no notion of TIME, yet completion time is the
    # gate. Arriving at tick 100 and at tick 690 scored the same. `timeout` only fires at the
    # deadline, so nothing made finishing sooner better than dawdling until just before it.
    #
    # `sprint` is the standard shortest-time shape: every tick costs (`living_cost`, applied in the
    # trainer, not the environment), speed offsets that cost, and arrival both pays and stops the
    # bleeding. The living cost must exceed the per-tick speed reward or running forever still pays.
    "sprint": RewardWeights(progress=0.05, speed=0.20, wall=0.02, timeout=1.0, arrive=200.0),
}

# Per-tick cost subtracted from every reward, expressed here rather than in `rex-env` because it is a
# property of the objective we are optimising, not of the simulation. Set above the per-tick speed
# reward at full speed (0.20 x ~1.0) so that continuing to run is never free.
LIVING_COST = {"sprint": 0.25}


# ==========================================================================
# routes
# ==========================================================================

@dataclass
class ScenarioSpec:
    name: str
    start: tuple
    target: tuple
    arrive_box: float
    timeout_s: float
    max_ticks: int


def load_goto_scenarios() -> list[ScenarioSpec]:
    """Every `kind = "goto"` dm3 scenario, minus `dash_100m` and `rj_*` (SPEC F1.2's own
    exclusions -- rocket jumps are out of scope for the movement policy and the environment has
    no rocket launcher)."""
    specs = []
    for f in sorted(SCEN_DIR.glob("*.toml")):
        cfg = tomllib.loads(f.read_text())
        if cfg.get("kind") != "goto" or f.stem in EXCLUDED_SCENARIOS:
            continue
        run = cfg["run"]
        timeout_s = float(run.get("timeout_s", 20.0))
        specs.append(ScenarioSpec(
            name=f.stem,
            start=tuple(float(v) for v in run["start"]),
            target=tuple(float(v) for v in run["target"]),
            arrive_box=float(run.get("arrive_box", 70.0)),
            timeout_s=timeout_s,
            max_ticks=int(timeout_s / TICK_DT) + 50,
        ))
    return specs


def probe_constructible(specs: list[ScenarioSpec], n_probe: int = 2) -> tuple[list[ScenarioSpec], list[dict]]:
    """Try to build each scenario's route via `rex_env.PyVecEnv` (which calls `Route::planned`
    internally). Returns (constructible specs, failure records) -- SPEC F1.2 requires reporting
    which scenarios fail to construct and why, not skipping them quietly."""
    import rex_env
    ok, failed = [], []
    for s in specs:
        try:
            rex_env.PyVecEnv(MAP, s.start, s.target, n_probe, s.arrive_box, s.max_ticks)
            ok.append(s)
        except Exception as e:
            failed.append({"name": s.name, "start": s.start, "target": s.target, "error": str(e)})
    return ok, failed


# ==========================================================================
# actor-critic
# ==========================================================================

def _torch():
    import torch
    import torch.nn as nn
    return torch, nn


class PPOActorCritic:
    """Wraps `policy.make_disc_actor`'s `DiscActor` (the warm-start source) with the sampling
    distributions PPO needs, plus a freshly-initialised critic (SPEC F1.2: "the value function has
    no warm start and must be learned"). The critic is a *separate* network, not a head bolted onto
    the actor's trunk -- deliberately, so noisy early value gradients (expected, per the spec, while
    advantage estimates are still mostly noise) cannot corrupt the warm-started actor trunk through
    a shared optimiser step.
    """

    def __init__(self, sdim=14, width=512, depth=3, critic_width=256, critic_depth=2, dev="cuda"):
        torch, nn = _torch()
        self.torch, self.nn = torch, nn
        self.dev = dev
        DiscActor = P.make_disc_actor(sdim, width, depth)
        self.actor = DiscActor().to(dev)
        # State-independent log-std for dyaw. Initialised small (std ~ 0.05 rad) so the warm-started
        # mean (== the BC policy's own deterministic action) dominates behaviour at iteration 0 --
        # PPO then learns whether to widen or narrow it from data, not from an arbitrary prior.
        self.log_std = nn.Parameter(torch.full((1,), np.log(0.05), device=dev))

        # Floor on the jump probability, mixed into the Bernoulli head *inside the policy* so the
        # log-probs PPO clips against are the ones actually sampled from (an epsilon applied outside
        # the policy would make the rollout off-policy and silently break the importance ratio).
        #
        #     p_jump = jump_floor / 2 + (1 - jump_floor) * sigmoid(z)
        #
        # Why this exists, measured 2026-07-29: the behaviour-cloned jump head emits a logit of
        # -6.10 on this environment's states — p = 0.002 — and is flat across them (-6.10 on the
        # ground, -5.60 in the air), i.e. it learned "never jump" and learned nothing about *when*.
        # Under greedy decoding it therefore never jumps at all, and under sampling it jumps once
        # every 450 ticks, which is not enough for PPO to ever discover that jumping is what makes
        # a climb or a bunny-hop possible. The measured consequence: the agent is on the ground on
        # 99.8 % of ticks and stalls at the foot of every ascent on the route set, while the human
        # corpus presses jump on 6.6 % of its 29,899,266 recorded usercmd ticks.
        #
        # 0.0 reproduces the plain Bernoulli exactly, so this is inert unless a caller sets it.
        self.jump_floor = 0.0

        # Floor on the steering noise. Measured 2026-07-29 across two 3000-iteration runs: the
        # summed policy entropy fell monotonically from +0.6 to -3.8 regardless of `ent_coef`,
        # because the term is dominated by this Gaussian and a Gaussian's entropy is unbounded below
        # as its std shrinks. The entropy bonus could not hold it up, and a policy with no steering
        # noise stops exploring turns entirely — which is most of what movement is. Clamping the std
        # from below bounds that entropy and makes `ent_coef` act on the discrete heads, where it
        # was supposed to act. log(0.03) is ~1.7 degrees of yaw per 14 ms tick: enough to perturb a
        # line, far too little to steer with.
        self.log_std_min = float(np.log(0.03))

        critic_layers = []
        d_in = sdim
        for _ in range(critic_depth):
            critic_layers += [nn.Linear(d_in, critic_width), nn.Tanh()]
            d_in = critic_width
        critic_layers += [nn.Linear(d_in, 1)]
        self.critic = nn.Sequential(*critic_layers).to(dev)

    def load_warm_start(self, path: Path):
        ck = self.torch.load(path, map_location=self.dev, weights_only=False)
        self.actor.load_state_dict(ck["actor"])
        return ck

    def parameters(self):
        return list(self.actor.parameters()) + [self.log_std] + list(self.critic.parameters())

    def act(self, obs: "torch.Tensor", actions=None):
        """`obs`: (B,14) already scaled. Returns (actions_tuple, logp, entropy, value) where
        actions_tuple = (f_cls, s_cls, dyaw, jump) -- f_cls/s_cls in {0,1,2}, dyaw radians, jump in
        {0.,1.}. If `actions` is given (same tuple shape), computes logp/entropy for those instead
        of sampling -- the PPO-update path re-evaluating the rollout's own stored actions."""
        torch, nn = self.torch, self.nn
        f_logit, s_logit, yaw_mean, jump_logit = self.actor(obs)
        f_dist = torch.distributions.Categorical(logits=f_logit)
        s_dist = torch.distributions.Categorical(logits=s_logit)
        yaw_std = self.log_std.clamp(min=self.log_std_min).exp().expand_as(yaw_mean)
        yaw_dist = torch.distributions.Normal(yaw_mean, yaw_std)
        if self.jump_floor > 0.0:
            p = torch.sigmoid(jump_logit)
            p = self.jump_floor * 0.5 + (1.0 - self.jump_floor) * p
            jump_dist = torch.distributions.Bernoulli(probs=p)
        else:
            jump_dist = torch.distributions.Bernoulli(logits=jump_logit)

        if actions is None:
            f_a = f_dist.sample()        # (B,)
            s_a = s_dist.sample()        # (B,)
            yaw_a = yaw_dist.sample()    # (B,1) -- kept unsqueezed so the recompute path below
            jump_a = jump_dist.sample()  # (B,1)    receives exactly the same shape it stored.
        else:
            f_a, s_a, yaw_a, jump_a = actions

        logp = (f_dist.log_prob(f_a) + s_dist.log_prob(s_a)
                + yaw_dist.log_prob(yaw_a).squeeze(-1) + jump_dist.log_prob(jump_a).squeeze(-1))
        entropy = (f_dist.entropy() + s_dist.entropy()
                   + yaw_dist.entropy().squeeze(-1) + jump_dist.entropy().squeeze(-1))
        value = self.critic(obs).squeeze(-1)
        # yaw_a/jump_a returned as (B,1): callers that feed this straight back into `act(actions=...)`
        # (the PPO update's recompute pass) need the exact shape `Normal`/`Bernoulli` produced it in,
        # not a squeezed one -- `actions_to_env` below is the only place that needs it flat, and it
        # reshapes(-1) itself rather than relying on this tuple's shape.
        return (f_a, s_a, yaw_a, jump_a), logp, entropy, value

    def state_dict(self):
        return dict(actor=self.actor.state_dict(), critic=self.critic.state_dict(),
                     log_std=self.log_std.detach().cpu())

    def save(self, path: Path, extra: dict | None = None):
        d = self.state_dict()
        d.update(extra or {})
        self.torch.save(d, path)

    def load(self, path: Path):
        ck = self.torch.load(path, map_location=self.dev, weights_only=False)
        self.actor.load_state_dict(ck["actor"])
        self.critic.load_state_dict(ck["critic"])
        with self.torch.no_grad():
            self.log_std.copy_(ck["log_std"].to(self.dev))
        return ck


def actions_to_env(ac_tuple) -> np.ndarray:
    """(f_cls, s_cls, dyaw, jump) torch tensors -> (N,4) float32 numpy for `PyVecEnv.step`:
    columns (fwd, side, dyaw, jump). f_cls/s_cls in {0,1,2} decode to {-1,0,+1} exactly like
    `policy.evaluate_disc`'s own decode. `dyaw`/`jump` are accepted either as (B,) or (B,1) --
    `reshape(-1)` rather than a fixed `.squeeze(-1)` so this works whether the caller kept the raw
    `Normal`/`Bernoulli` sample shape (training's recompute path) or already flattened it (eval's
    greedy path)."""
    f_cls, s_cls, dyaw, jump = ac_tuple
    f = (f_cls.detach().cpu().numpy().reshape(-1).astype(np.float32) - 1.0)
    s = (s_cls.detach().cpu().numpy().reshape(-1).astype(np.float32) - 1.0)
    yaw = dyaw.detach().cpu().numpy().reshape(-1).astype(np.float32)
    j = jump.detach().cpu().numpy().reshape(-1).astype(np.float32)
    return np.stack([f, s, yaw, j], axis=1).astype(np.float32)


def obs_to_state(obs_np: np.ndarray, torch, dev) -> "torch.Tensor":
    """Raw `(N,14)` observation from the env is **already** scaled by `Env::observe` (division by
    `s_scale` happens Rust-side, see `rex-env/src/lib.rs`), so this is just a host->device copy, no
    further scaling -- doing it twice would silently double-shrink every channel."""
    return torch.tensor(obs_np, device=dev, dtype=torch.float32)


# ==========================================================================
# throughput breakdown -- SPEC F1.2's first deliverable
# ==========================================================================

def bench_iteration(n: int, T: int = 128, epochs: int = 4, minibatches: int = 4,
                     warmup_steps: int | None = None, dev: str = "cuda") -> dict:
    """One real PPO iteration at batch size `n`: a `T`-step rollout through `PyVecEnv`, then
    `epochs` passes of minibatch PPO updates over the T*n transitions collected. Times three
    buckets exactly as SPEC F1.2 asks:

      env_s      -- wall time inside `PyVecEnv.step()` calls only (the Rust/PyO3/rayon path).
      forward_s  -- wall time for everything that produces the *next* action: host->device obs
                    copy, actor+critic forward, sampling, device->host action copy. This is where
                    the Python-boundary data movement the F1.1 evidence measured actually lives, so
                    it is reported here rather than folded silently into "env".
      update_s   -- wall time for GAE (cheap) plus every epoch's forward+backward+optimiser.step()
                    over the collected rollout. The update's own forward pass (recomputing log
                    probs under the new parameters) is inseparable from backward+optimiser in any
                    real PPO implementation, so it is counted here, not split out again.

    A short warmup iteration (same N, discarded) runs first and is NOT the recommended reading --
    do NOT read the very first bench_iteration call's rollout as representative; rayon's thread
    pool and CUDA's kernel caches both pay a one-time cost that is not part of steady-state
    training. `bench()` below runs the warmup explicitly for exactly this reason.
    """
    import rex_env
    torch, nn = _torch()
    if warmup_steps is None:
        warmup_steps = max(4, T // 8)

    env = rex_env.PyVecEnv(MAP, BENCH_START, BENCH_GOAL, n)
    ac = PPOActorCritic(dev=dev)
    ac.load_warm_start(WARM_START)
    opt = torch.optim.Adam(ac.parameters(), lr=3e-4)

    obs_np = env.reset()

    def rollout_step(store: dict | None):
        nonlocal obs_np
        t0 = time.perf_counter()
        obs_t = obs_to_state(obs_np, torch, dev)
        with torch.no_grad():
            ac_tuple, logp, _, value = ac.act(obs_t)
        actions_np = actions_to_env(ac_tuple)
        torch.cuda.synchronize() if dev == "cuda" else None
        t1 = time.perf_counter()
        next_obs, parts, dones = env.step(actions_np)
        t2 = time.perf_counter()
        if store is not None:
            store["obs"].append(obs_t.cpu())
            store["f"].append(ac_tuple[0].cpu()); store["s"].append(ac_tuple[1].cpu())
            store["yaw"].append(ac_tuple[2].cpu()); store["jump"].append(ac_tuple[3].cpu())
            store["logp"].append(logp.cpu()); store["value"].append(value.cpu())
            store["parts"].append(np.array(parts, copy=True))
            store["dones"].append(np.array(dones, copy=True))
        obs_np = next_obs
        return (t1 - t0), (t2 - t1)

    # Warmup: pays for rayon thread-pool spin-up and CUDA kernel/context caching, off the clock.
    for _ in range(warmup_steps):
        rollout_step(None)

    store = {k: [] for k in ("obs", "f", "s", "yaw", "jump", "logp", "value", "parts", "dones")}
    env_s = 0.0
    fwd_s = 0.0
    for _ in range(T):
        f, e = rollout_step(store)
        fwd_s += f
        env_s += e

    weights = REWARD_WEIGHTINGS["rtx_default"].vec()
    rewards = np.stack([p @ weights for p in store["parts"]], axis=0)  # (T, n)
    dones = np.stack(store["dones"], axis=0).astype(np.float32)
    values = torch.stack(store["value"], dim=0).numpy()  # (T, n)
    with torch.no_grad():
        last_obs_t = obs_to_state(obs_np, torch, dev)
        last_value = ac.critic(last_obs_t).squeeze(-1).cpu().numpy()

    t0 = time.perf_counter()
    adv = gae(rewards, values, dones, last_value)
    ret = adv + values

    obs_all = torch.cat(store["obs"], dim=0).to(dev)
    f_all = torch.cat(store["f"], dim=0).to(dev)
    s_all = torch.cat(store["s"], dim=0).to(dev)
    yaw_all = torch.cat(store["yaw"], dim=0).to(dev)
    jump_all = torch.cat(store["jump"], dim=0).to(dev)
    logp_all = torch.cat(store["logp"], dim=0).to(dev)
    adv_t = torch.tensor(adv.reshape(-1), device=dev, dtype=torch.float32)
    ret_t = torch.tensor(ret.reshape(-1), device=dev, dtype=torch.float32)
    adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

    total = obs_all.shape[0]
    mb_size = max(1, total // minibatches)
    for _ in range(epochs):
        perm = torch.randperm(total, device=dev)
        for mb in range(minibatches):
            idx = perm[mb * mb_size: (mb + 1) * mb_size]
            _, new_logp, entropy, new_value = ac.act(
                obs_all[idx], actions=(f_all[idx], s_all[idx], yaw_all[idx], jump_all[idx]))
            ratio = (new_logp - logp_all[idx]).exp()
            surr1 = ratio * adv_t[idx]
            surr2 = ratio.clamp(0.8, 1.2) * adv_t[idx]
            policy_loss = -torch.min(surr1, surr2).mean()
            value_loss = nn.functional.mse_loss(new_value, ret_t[idx])
            loss = policy_loss + 0.5 * value_loss - 0.005 * entropy.mean()
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
    if dev == "cuda":
        torch.cuda.synchronize()
    update_s = time.perf_counter() - t0

    total_env_steps = T * n
    total_wall = env_s + fwd_s + update_s
    return {
        "n": n, "T": T, "epochs": epochs, "minibatches": minibatches,
        "env_s": env_s, "forward_s": fwd_s, "update_s": update_s,
        "total_wall_s": total_wall, "total_env_steps": total_env_steps,
        "steps_per_s": total_env_steps / total_wall,
        "env_frac": env_s / total_wall, "forward_frac": fwd_s / total_wall, "update_frac": update_s / total_wall,
    }


def bench(out_path: Path = OUT / "throughput.json", repeats: int = 3) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    for n in (4096, 16384):
        # One full discarded warmup iteration (its own T-step rollout + update) beyond
        # bench_iteration's internal per-step warmup, so CUDA's very first optimiser.step()
        # (cudnn/cublas workspace allocation) isn't charged to the first measured repeat either.
        bench_iteration(n, T=32, epochs=1, minibatches=2)
        reps = [bench_iteration(n) for _ in range(repeats)]
        rates = sorted(r["steps_per_s"] for r in reps)
        median = reps[sorted(range(len(reps)), key=lambda i: reps[i]["steps_per_s"])[len(reps) // 2]]
        results[str(n)] = {
            "repeats": reps,
            "median_steps_per_s": rates[len(rates) // 2],
            "median_env_s": float(np.median([r["env_s"] for r in reps])),
            "median_forward_s": float(np.median([r["forward_s"] for r in reps])),
            "median_update_s": float(np.median([r["update_s"] for r in reps])),
            "median_env_frac": float(np.median([r["env_frac"] for r in reps])),
            "median_forward_frac": float(np.median([r["forward_frac"] for r in reps])),
            "median_update_frac": float(np.median([r["update_frac"] for r in reps])),
        }
        r = results[str(n)]
        print(f"N={n}: env {r['median_env_s']*1000:.1f}ms ({r['median_env_frac']*100:.1f}%)  "
              f"forward {r['median_forward_s']*1000:.1f}ms ({r['median_forward_frac']*100:.1f}%)  "
              f"update {r['median_update_s']*1000:.1f}ms ({r['median_update_frac']*100:.1f}%)  "
              f"-> {r['median_steps_per_s']/1e6:.3f} M steps/s", flush=True)
    binding = max(("env", "forward", "update"),
                  key=lambda k: sum(results[n][f"median_{k}_frac"] for n in results) / len(results))
    results["_binding_constraint"] = binding
    out_path.write_text(json.dumps(results, indent=2))
    print(f"binding constraint: {binding}")
    print(f"wrote {out_path}")
    return results


# ==========================================================================
# GAE
# ==========================================================================

def gae(rewards: np.ndarray, values: np.ndarray, dones: np.ndarray, last_value: np.ndarray,
        gamma: float = 0.99, lam: float = 0.95) -> np.ndarray:
    """`rewards`/`values`/`dones`: (T, N). `dones[t, i]` means env i's episode that produced
    `rewards[t, i]` ended at step t (VecEnv auto-reset semantics: `values[t+1, i]` -- if it existed
    -- would already be the *new* episode's value, so the bootstrap must be masked to zero exactly
    where `dones` is set, per `VecEnv::step`'s own doc comment on what dones/obs mean together)."""
    T, N = rewards.shape
    adv = np.zeros((T, N), dtype=np.float32)
    last_gae = np.zeros(N, dtype=np.float32)
    next_value = last_value
    for t in reversed(range(T)):
        mask = 1.0 - dones[t]
        delta = rewards[t] + gamma * next_value * mask - values[t]
        last_gae = delta + gamma * lam * mask * last_gae
        adv[t] = last_gae
        next_value = values[t]
    return adv


# ==========================================================================
# multi-route rollout + PPO update (training)
# ==========================================================================

class MultiRouteRoller:
    """One `PyVecEnv` per training route, each sized `n_per_route`, stepped together every tick so
    a single forward pass on the concatenated batch serves every route at once. Keeps per-route
    reward-part sums for the reward-weighting attribution report."""

    def __init__(self, specs: list[ScenarioSpec], n_per_route: int, dev: str):
        import rex_env
        self.torch, _ = _torch()
        self.dev = dev
        self.specs = specs
        self.n_per_route = n_per_route
        self.envs = [rex_env.PyVecEnv(MAP, s.start, s.target, n_per_route, s.arrive_box, s.max_ticks) for s in specs]
        self.obs_np = [e.reset() for e in self.envs]
        self.slices = []
        acc = 0
        for _ in specs:
            self.slices.append(slice(acc, acc + n_per_route))
            acc += n_per_route
        self.total_n = acc

    def step(self, ac: PPOActorCritic, greedy: bool = False):
        torch = self.torch
        obs_cat = np.concatenate(self.obs_np, axis=0)
        obs_t = obs_to_state(obs_cat, torch, self.dev)
        if greedy:
            with torch.no_grad():
                f_logit, s_logit, yaw_mean, jump_logit = ac.actor(obs_t)
                ac_tuple = (f_logit.argmax(-1), s_logit.argmax(-1), yaw_mean.squeeze(-1),
                            (jump_logit.squeeze(-1) > 0).float())
                logp = torch.zeros(obs_t.shape[0], device=self.dev)
                value = ac.critic(obs_t).squeeze(-1)
        else:
            with torch.no_grad():
                ac_tuple, logp, _, value = ac.act(obs_t)
        actions_np = actions_to_env(ac_tuple)

        all_parts, all_dones = [], []
        for i, env in enumerate(self.envs):
            sl = self.slices[i]
            o, parts, dones = env.step(actions_np[sl])
            self.obs_np[i] = o
            all_parts.append(np.array(parts, copy=True))
            all_dones.append(np.array(dones, copy=True))
        parts_cat = np.concatenate(all_parts, axis=0)
        dones_cat = np.concatenate(all_dones, axis=0)
        return obs_t, ac_tuple, logp, value, parts_cat, dones_cat


def train_one_weighting(weight_name: str, weights: RewardWeights, specs: list[ScenarioSpec],
                         iterations: int, n_per_route: int = 256, T: int = 128,
                         epochs: int = 4, minibatches: int = 8, critic_warmup_iters: int = 15,
                         lr: float = 3e-4, ent_coef: float = 0.005, living_cost: float = 0.0,
                         dev: str = "cuda", seed: int = 0,
                         ckpt_name: str | None = None) -> dict:
    """PPO over every constructible training route at once (`MultiRouteRoller`), with a
    `critic_warmup_iters`-iteration value-only warmup: the actor's optimiser step is skipped (only
    the critic + log_std... no, log_std belongs to the actor distribution, so it is excluded from
    the warmup-phase optimizer too) while the critic learns off the warm-started policy's own
    on-policy data. This is a decision taken here, not in the spec: the spec warns "expect the
    first iterations to be dominated by value error" and "do not read early policy collapse as a
    bug before checking whether advantage estimates are simply noise" -- a short critic-only warmup
    is the direct, measurable way to keep that expected noise from ever reaching the (warm-started,
    already-good) actor weights, rather than hoping the clip range absorbs it.
    """
    torch, nn = _torch()
    torch.manual_seed(seed)
    OUT.mkdir(parents=True, exist_ok=True)
    ac = PPOActorCritic(dev=dev)
    ac.load_warm_start(WARM_START)

    actor_critic_params = list(ac.actor.parameters()) + [ac.log_std]
    critic_params = list(ac.critic.parameters())
    opt_actor = torch.optim.Adam(actor_critic_params, lr=lr)
    opt_critic = torch.optim.Adam(critic_params, lr=lr)

    roller = MultiRouteRoller(specs, n_per_route, dev)
    weight_vec = torch.tensor(weights.vec(), device=dev)

    log = []
    t_start = time.time()
    for it in range(1, iterations + 1):
        buf = {k: [] for k in ("obs", "f", "s", "yaw", "jump", "logp", "value", "parts", "dones")}
        for _ in range(T):
            obs_t, ac_tuple, logp, value, parts, dones = roller.step(ac)
            buf["obs"].append(obs_t); buf["f"].append(ac_tuple[0]); buf["s"].append(ac_tuple[1])
            buf["yaw"].append(ac_tuple[2]); buf["jump"].append(ac_tuple[3])
            buf["logp"].append(logp); buf["value"].append(value)
            buf["parts"].append(parts); buf["dones"].append(dones)

        parts_arr = np.stack(buf["parts"], axis=0)          # (T, total_n, 5)
        rewards = parts_arr @ weights.vec() - living_cost    # (T, total_n)
        dones_arr = np.stack(buf["dones"], axis=0).astype(np.float32)
        values_arr = torch.stack(buf["value"], dim=0).detach().cpu().numpy()
        with torch.no_grad():
            last_obs_cat = np.concatenate(roller.obs_np, axis=0)
            last_obs_t = obs_to_state(last_obs_cat, torch, dev)
            last_value = ac.critic(last_obs_t).squeeze(-1).cpu().numpy()

        adv = gae(rewards, values_arr, dones_arr, last_value)
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
        mb_size = max(1, total // minibatches)
        ploss_log, vloss_log, ent_log = [], [], []
        for _ in range(epochs):
            perm = torch.randperm(total, device=dev)
            for mb in range(minibatches):
                idx = perm[mb * mb_size:(mb + 1) * mb_size]
                _, new_logp, entropy, new_value = ac.act(
                    obs_all[idx], actions=(f_all[idx], s_all[idx], yaw_all[idx], jump_all[idx]))
                ratio = (new_logp - logp_all[idx]).exp()
                surr1 = ratio * adv_t[idx]
                surr2 = ratio.clamp(0.8, 1.2) * adv_t[idx]
                policy_loss = -torch.min(surr1, surr2).mean()
                value_loss = nn.functional.mse_loss(new_value, ret_t[idx])
                ent = entropy.mean()

                opt_critic.zero_grad(set_to_none=True)
                if update_actor:
                    opt_actor.zero_grad(set_to_none=True)
                loss = (policy_loss - ent_coef * ent) + 0.5 * value_loss
                loss.backward()
                opt_critic.step()
                if update_actor:
                    opt_actor.step()
                ploss_log.append(float(policy_loss.detach())); vloss_log.append(float(value_loss.detach())); ent_log.append(float(ent.detach()))

        term_means = parts_arr.reshape(-1, 5).mean(axis=0)
        entry = dict(it=it, phase=("critic_warmup" if not update_actor else "ppo"),
                     policy_loss=float(np.mean(ploss_log)), value_loss=float(np.mean(vloss_log)),
                     entropy=float(np.mean(ent_log)), reward_mean=float(rewards.mean()),
                     adv_std_raw=float(adv.std()),
                     term_progress=float(term_means[0]), term_speed=float(term_means[1]),
                     term_wall=float(term_means[2]), term_timeout=float(term_means[3]),
                     term_arrive=float(term_means[4]), s=round(time.time() - t_start, 1))
        log.append(entry)
        if it % 5 == 0 or it == 1:
            print(f"[{weight_name} it {it:>4}/{iterations} {entry['phase']:>13}] "
                  f"reward {entry['reward_mean']:.4f}  vloss {entry['value_loss']:.4f}  "
                  f"ploss {entry['policy_loss']:.4f}  ent {entry['entropy']:.3f}  "
                  f"arrive {term_means[4]:.4f}  wall {term_means[2]:.4f}  speed {term_means[1]:.4f}  "
                  f"{entry['s']:.0f}s", flush=True)

    ckpt_name = ckpt_name or f"ppo_actor_{weight_name}.pt"
    ac.save(OUT / ckpt_name, extra=dict(weight_name=weight_name, weights=weights.vec().tolist(),
                                         width=512, depth=3, s_scale=S_SCALE, a_scale=A_SCALE,
                                         state_cols=STATE_COLS, routes=[s.name for s in specs],
                                         n_per_route=n_per_route, T=T, epochs=epochs,
                                         minibatches=minibatches, iterations=iterations,
                                         critic_warmup_iters=critic_warmup_iters, lr=lr, seed=seed))
    (OUT / f"train_log_{weight_name}.json").write_text(json.dumps(log, indent=2))
    print(f"saved {OUT / ckpt_name}")
    return dict(ckpt=str(OUT / ckpt_name), log=log)


# ==========================================================================
# per-route evaluation
# ==========================================================================

def evaluate_route(ac: PPOActorCritic, spec: ScenarioSpec, n_episodes: int = 30, dev: str = "cuda") -> dict:
    """Runs `n_episodes` (>= the spec's floor) of `spec` with the greedy (mode, not sampled) action,
    since a shipped policy is graded on its best behaviour, not its exploration noise. Uses one
    `PyVecEnv` of size `n_episodes` and steps until every slot has completed at least one full
    episode (auto-reset means a slot can complete more than one; only each slot's FIRST completed
    episode is scored, so every route contributes exactly `n_episodes` independent episodes rather
    than an uneven mix of fast-route reruns and slow-route stragglers)."""
    import rex_env
    torch, _ = _torch()
    env = rex_env.PyVecEnv(MAP, spec.start, spec.target, n_episodes, spec.arrive_box, spec.max_ticks)
    obs_np = env.reset()

    done_flag = np.zeros(n_episodes, dtype=bool)
    completion_ticks = np.full(n_episodes, -1, dtype=np.int64)
    outcome = np.array(["running"] * n_episodes, dtype=object)
    ticks_elapsed = np.zeros(n_episodes, dtype=np.int64)
    speed_samples = [[] for _ in range(n_episodes)]
    wall_hit = np.zeros(n_episodes, dtype=bool)

    max_steps = spec.max_ticks + 5
    for t in range(max_steps):
        obs_t = obs_to_state(obs_np, torch, dev)
        with torch.no_grad():
            f_logit, s_logit, yaw_mean, jump_logit = ac.actor(obs_t)
            f_cls = f_logit.argmax(-1); s_cls = s_logit.argmax(-1)
            jump = (jump_logit.squeeze(-1) > 0).float()
        ac_tuple = (f_cls, s_cls, yaw_mean.squeeze(-1), jump)
        actions_np = actions_to_env(ac_tuple)

        speed_xy = obs_np[:, 3] * S_SCALE[3]  # column 3 = speed_xy, already /400 in Env::observe
        for i in range(n_episodes):
            if not done_flag[i]:
                ticks_elapsed[i] += 1
                if speed_xy[i] > 1.0:  # "moving ticks" -- exclude ~stationary ticks from the speed floor stat
                    speed_samples[i].append(speed_xy[i])

        obs_np, parts, dones = env.step(actions_np)
        for i in range(n_episodes):
            if done_flag[i]:
                continue
            p = parts[i]
            if p[2] < 0:  # wall term is -1.0 on contact
                wall_hit[i] = True
            if dones[i]:
                done_flag[i] = True
                completion_ticks[i] = ticks_elapsed[i]
                if p[4] > 0:
                    outcome[i] = "arrived"
                elif p[3] < 0:
                    outcome[i] = "timeout"
                else:
                    outcome[i] = "void"
        if done_flag.all():
            break

    for i in range(n_episodes):
        if not done_flag[i]:
            outcome[i] = "unfinished_at_bench_horizon"
            completion_ticks[i] = ticks_elapsed[i]

    arrived_mask = outcome == "arrived"
    times_s = completion_ticks * TICK_DT
    all_speeds = np.concatenate([np.array(s) for s in speed_samples if len(s)]) if any(len(s) for s in speed_samples) else np.array([0.0])

    result = {
        "name": spec.name,
        "n_episodes": n_episodes,
        "arrival_rate": float(arrived_mask.mean()),
        "outcome_counts": {k: int((outcome == k).sum()) for k in np.unique(outcome)},
        "median_completion_time_s": float(np.median(times_s[arrived_mask])) if arrived_mask.any() else None,
        "p90_completion_time_s": float(np.percentile(times_s[arrived_mask], 90)) if arrived_mask.any() else None,
        "median_completion_time_s_all": float(np.median(times_s)),
        "frac_moving_ticks_above_320ups": float((all_speeds > BHOP_GATE_UPS).mean()),
        "median_horizontal_speed_ups": float(np.median(all_speeds)),
        "wall_contact_episodes": int(wall_hit.sum()),
        "human_ref_ups": HUMAN_REF_UPS,
        "reference_time_s": None,
    }
    return result


def evaluate_all(ckpt_path: Path, n_episodes: int = 30, dev: str = "cuda", out_name: str = "eval_routes.json") -> dict:
    ac = PPOActorCritic(dev=dev)
    ac.load(ckpt_path)
    specs = load_goto_scenarios()
    ok_specs, failed = probe_constructible(specs)

    # Attach the owner's reference_time_s from the scenario's own [threshold] block, when present.
    ref_times = {}
    for f in SCEN_DIR.glob("*.toml"):
        cfg = tomllib.loads(f.read_text())
        th = cfg.get("threshold", {})
        if "reference_time_s" in th:
            ref_times[f.stem] = th["reference_time_s"]

    rows = []
    for spec in ok_specs:
        r = evaluate_route(ac, spec, n_episodes=n_episodes, dev=dev)
        r["reference_time_s"] = ref_times.get(spec.name)
        rows.append(r)
        print(f"{spec.name:45s} arrive {r['arrival_rate']*100:5.1f}%  "
              f"med {str(r['median_completion_time_s'])[:6]:>6}s  p90 {str(r['p90_completion_time_s'])[:6]:>6}s  "
              f">320ups {r['frac_moving_ticks_above_320ups']*100:5.1f}%  "
              f"med_speed {r['median_horizontal_speed_ups']:6.1f}  wall {r['wall_contact_episodes']:3d}", flush=True)

    result = {"ckpt": str(ckpt_path), "n_episodes": n_episodes, "routes": rows, "construction_failures": failed}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / out_name).write_text(json.dumps(result, indent=2))
    print(f"wrote {OUT / out_name}")
    return result


# ==========================================================================
# CLI
# ==========================================================================

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["bench", "train", "eval", "probe"])
    ap.add_argument("--weighting", default="rtx_default", choices=list(REWARD_WEIGHTINGS))
    ap.add_argument("--iterations", type=int, default=200)
    ap.add_argument("--n-per-route", type=int, default=256)
    ap.add_argument("--ckpt", default=None)
    ap.add_argument("--n-episodes", type=int, default=30)
    a = ap.parse_args()

    if a.cmd == "probe":
        specs = load_goto_scenarios()
        ok, failed = probe_constructible(specs)
        print(f"{len(ok)} constructible, {len(failed)} failed")
        for f in failed:
            print(f"  FAIL {f['name']}: {f['error']}")
        (OUT / "route_probe.json").write_text(json.dumps({"ok": [s.name for s in ok], "failed": failed}, indent=2))
    elif a.cmd == "bench":
        bench()
    elif a.cmd == "train":
        specs = load_goto_scenarios()
        ok, failed = probe_constructible(specs)
        train_one_weighting(a.weighting, REWARD_WEIGHTINGS[a.weighting], ok,
                            iterations=a.iterations, n_per_route=a.n_per_route)
    elif a.cmd == "eval":
        ckpt = Path(a.ckpt) if a.ckpt else OUT / f"ppo_actor_{a.weighting}.pt"
        evaluate_all(ckpt, n_episodes=a.n_episodes, out_name=f"eval_routes_{a.weighting}.json")
