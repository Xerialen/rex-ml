"""Train on the states the policy actually visits, labelled by what humans did in states like them.

Behaviour cloning trains on the human's states. The policy then acts, drifts into states no human was
in, and has nothing to say there — so the next error is larger. That compounding is what every patch
of the last day was working around: measured, the behaviour-cloned jump head fires at p = 0.230 in
human states and p = 0.006 in the state this environment starts the policy in. The network was never
broken; it was somewhere else.

The loop closes that gap directly:

  1. roll the current policy out and keep the states it actually reaches;
  2. ask the corpus what a human did in comparable states;
  3. add those pairs to the training set;
  4. retrain, and repeat.

**The expert is the corpus, not the network.** Querying the behaviour-cloned net would be circular —
it is the learner. A k-nearest-neighbour lookup over 26.9 M recorded transitions is different in the
one way that matters here: it is non-parametric, so it *knows when it does not know*. The distance to
the nearest human states is a measurement of whether the policy has wandered somewhere the corpus can
speak about at all, and the fraction of visited states that fall beyond that is the diagnostic this
project has never had.

There is no reward. The target is the human's action. Every hand-set number from the reward work —
living cost, arrival bonus, jump floor, curriculum window — is gone, because each of them existed to
compensate for this same drift.

**Two deliberate exclusions in the distance metric**, both because the environment cannot produce the
channel and matching on it would be matching on noise:

  * `pitch` is pinned at 0.0 in this environment and varies across the corpus.
  * `omega_prev` on the first tick of an episode is 0 by construction, not by choice.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

from . import cohort_routes as C
from . import policy as P
from . import race

OUT = Path("/home/benjamin-adm/rex-ml/pipeline/out/dagger")
POLICY_DIR = Path("/home/benjamin-adm/rex-ml/pipeline/out/policy")

# Channel weights for the nearest-neighbour metric. Everything is already divided by `S_SCALE`, so
# the space is comparable; these zero out what the environment cannot express rather than reweight
# what it can.
IDX_PITCH = P.STATE_COLS.index("pitch")
METRIC_W = np.ones(len(P.STATE_COLS), dtype=np.float32)
METRIC_W[IDX_PITCH] = 0.0


def _scaled(a: np.ndarray) -> np.ndarray:
    return (a / P.S_SCALE).astype(np.float32)


class CorpusExpert:
    """k-NN over the corpus in the policy's own observation space.

    Holds the reference set on the GPU in fp16 (26.9 M x 14 would be 1.5 GB in fp32 and is 0.75 GB
    here) and answers batched queries with both an action and a distance. The distance is the point:
    an answer from 300 units away in observation space is not an answer.
    """

    def __init__(self, n_ref: int = 8_000_000, k: int = 16, dev: str = "cuda", seed: int = 0,
                 min_speed: float = 0.0):
        S = np.load(POLICY_DIR / "S.npy", mmap_mode="r")
        A = np.load(POLICY_DIR / "A.npy", mmap_mode="r")
        SP = np.load(POLICY_DIR / "SP.npy", mmap_mode="r")
        train = np.flatnonzero(np.asarray(SP) == 0)
        if min_speed > 0:
            # Only humans who were *going somewhere* may answer.
            #
            # Round 1 of this loop produced a policy that stands still, and the reason is in the
            # expert: asked about the states the bot is actually in, it answered `fwd = 0` for 99.4 %
            # of the slow ones and p(jump) = 0.001. That answer is correct and useless. The only
            # humans in the corpus at under 20 u/s are humans who chose to stop — waiting, aiming,
            # picking a fight — and the lookup matches kinematics, not intent. It cannot tell that
            # our bot is at 0 u/s because it is stuck on the way somewhere.
            #
            # Excluding stationary humans from the reference set makes the expert unable to give that
            # answer at all. States where the bot is stuck then fall outside the calibrated distance
            # and are dropped as unanswerable — which is honest: the corpus genuinely does not
            # contain "how to get unstuck", because humans do not get stuck.
            sp = np.asarray(S[:, 3])[train]
            train = train[sp > min_speed]
            print(f"expert begränsad till människor i rörelse (>{min_speed:.0f} u/s): "
                  f"{len(train):,} kandidater", flush=True)
        rng = np.random.default_rng(seed)
        pick = np.sort(rng.choice(train, size=min(n_ref, len(train)), replace=False))
        self.dev, self.k = dev, k
        w = torch.tensor(METRIC_W, device=dev)
        self.ref = (torch.tensor(_scaled(np.asarray(S[pick])), device=dev) * w).half()
        act = np.asarray(A[pick])
        self.act_f = torch.tensor(P._sign_class(act[:, 0]), device=dev)
        self.act_s = torch.tensor(P._sign_class(act[:, 1]), device=dev)
        self.act_yaw = torch.tensor(np.clip(act[:, 2] / P.A_SCALE[2], -1, 1),
                                    device=dev, dtype=torch.float32)
        self.act_jmp = torch.tensor((act[:, 3] > 0.5).astype(np.float32), device=dev)
        self.w = w
        self.ref_sq = (self.ref.float() ** 2).sum(1)
        print(f"expert: {len(pick):,} referenstransitioner på GPU, k={k}", flush=True)

    def query(self, obs: np.ndarray, q_chunk: int = 4096, r_chunk: int = 500_000):
        """`obs` is (N, 14) already scaled. Returns (f, s, yaw, jump, distance)."""
        # Identical query states are common in a rollout (a stalled bot emits the same observation
        # for hundreds of ticks) and each duplicate would pay the full search. Deduplicating first
        # and scattering the answers back cuts the work by whatever the redundancy happens to be,
        # without changing a single returned label.
        obs = np.ascontiguousarray(obs, dtype=np.float32)
        uniq, inv = np.unique(np.round(obs, 4), axis=0, return_inverse=True)
        Q = (torch.tensor(uniq, device=self.dev, dtype=torch.float32) * self.w)
        n = Q.shape[0]
        f = torch.empty(n, dtype=torch.long, device=self.dev)
        s = torch.empty(n, dtype=torch.long, device=self.dev)
        yaw = torch.empty(n, device=self.dev)
        jmp = torch.empty(n, device=self.dev)
        dist = torch.empty(n, device=self.dev)
        for a in range(0, n, q_chunk):
            q = Q[a:a + q_chunk]
            qs = (q ** 2).sum(1, keepdim=True)
            best_d = None
            best_i = None
            for b in range(0, self.ref.shape[0], r_chunk):
                r = self.ref[b:b + r_chunk]
                # squared distance without materialising differences
                d = qs + self.ref_sq[b:b + r_chunk].unsqueeze(0) - 2.0 * (q @ r.float().T)
                dk, ik = torch.topk(d, self.k, dim=1, largest=False)
                ik = ik + b
                if best_d is None:
                    best_d, best_i = dk, ik
                else:
                    cd = torch.cat([best_d, dk], 1)
                    ci = torch.cat([best_i, ik], 1)
                    sel = torch.topk(cd, self.k, dim=1, largest=False)
                    best_d = sel.values
                    best_i = torch.gather(ci, 1, sel.indices)
            nb = best_i
            # discrete heads: majority among the neighbours; continuous: their mean
            fc = self.act_f[nb]
            sc = self.act_s[nb]
            f[a:a + q_chunk] = torch.mode(fc, dim=1).values
            s[a:a + q_chunk] = torch.mode(sc, dim=1).values
            yaw[a:a + q_chunk] = self.act_yaw[nb].mean(1)
            jmp[a:a + q_chunk] = self.act_jmp[nb].mean(1)
            dist[a:a + q_chunk] = best_d.clamp_min(0).sqrt().mean(1)
        return (f.cpu().numpy()[inv], s.cpu().numpy()[inv], yaw.cpu().numpy()[inv],
                jmp.cpu().numpy()[inv], dist.cpu().numpy()[inv])

    def calibrate(self, n: int = 100_000, seed: int = 1) -> float:
        """The distance beyond which a state is unlike anything the corpus holds.

        Measured, not chosen: held-out corpus rows are queried against the reference set and the 99th
        percentile of their own neighbour distance is the cut. A rollout state further away than the
        corpus is from itself has no human answer, and using it as a label would be inventing one.
        """
        S = np.load(POLICY_DIR / "S.npy", mmap_mode="r")
        SP = np.load(POLICY_DIR / "SP.npy", mmap_mode="r")
        test = np.flatnonzero(np.asarray(SP) == 2)
        rng = np.random.default_rng(seed)
        pick = np.sort(rng.choice(test, size=min(n, len(test)), replace=False))
        _, _, _, _, d = self.query(_scaled(np.asarray(S[pick])))
        q = np.percentile(d, [50, 90, 99])
        print(f"kalibrering på held-out korpus: grannavstånd p50 {q[0]:.4f} "
              f"p90 {q[1]:.4f} p99 {q[2]:.4f}", flush=True)
        return float(q[2])


def rollout_states(actor, routes, n_per_route: int, ticks: int, dev: str = "cuda") -> np.ndarray:
    """States the current policy actually reaches, from the true starts, sampling its own actions.

    Sampling rather than greedy on purpose: the aggregate has to cover the states the policy can
    reach, not the single line one decode rule produces.
    """
    import rex_env
    envs = [rex_env.PyVecEnv(race.MAP, r.start, r.target, n_per_route, C.ARRIVE_BOX, r.max_ticks)
            for r in routes]
    obs = [e.reset() for e in envs]
    keep = []
    for _ in range(ticks):
        cat = np.concatenate(obs, 0)
        keep.append(cat.copy())
        t = torch.tensor(cat, device=dev, dtype=torch.float32)
        with torch.no_grad():
            fl, sl, yaw, jl = actor(t)
            f = torch.distributions.Categorical(logits=fl).sample()
            s = torch.distributions.Categorical(logits=sl).sample()
            j = (torch.rand_like(jl.squeeze(-1)) < torch.sigmoid(jl.squeeze(-1))).float()
        a = np.stack([(f.cpu().numpy() - 1).astype(np.float32),
                      (s.cpu().numpy() - 1).astype(np.float32),
                      yaw.squeeze(-1).cpu().numpy(), j.cpu().numpy()], 1).astype(np.float32)
        off = 0
        for i, e in enumerate(envs):
            m = len(obs[i])
            obs[i], _, _ = e.step(a[off:off + m])
            off += m
    return np.concatenate(keep, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--n-per-route", type=int, default=192)
    ap.add_argument("--ticks", type=int, default=420)
    ap.add_argument("--keep-per-round", type=int, default=250_000)
    ap.add_argument("--n-ref", type=int, default=8_000_000)
    ap.add_argument("--k", type=int, default=16)
    ap.add_argument("--steps", type=int, default=12_000)
    ap.add_argument("--batch", type=int, default=8192)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--min-expert-speed", type=float, default=100.0,
                    help="exclude stationary humans from the expert; 0 restores the old behaviour")
    ap.add_argument("--dedup-grid", type=float, default=0.02,
                    help="quantisation for weighting the aggregate per state instead of per tick")
    ap.add_argument("--bc-mix", type=float, default=0.5,
                    help="share of each training batch drawn from the original corpus, so the "
                         "aggregate cannot make the policy forget what it already does well")
    ap.add_argument("--ckpt", default="dagger.pt")
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    dev = "cuda"
    torch_nn = torch.nn

    actor = P.make_disc_actor(14, 512, 3)().to(dev)
    warm = torch.load(POLICY_DIR / "actor_disc_3x512.pt", map_location=dev, weights_only=False)
    actor.load_state_dict(warm["actor"])

    expert = CorpusExpert(n_ref=a.n_ref, k=a.k, dev=dev, min_speed=a.min_expert_speed)
    cut = expert.calibrate()

    # a slice of the original corpus, to mix into every batch
    S = np.load(POLICY_DIR / "S.npy", mmap_mode="r")
    A = np.load(POLICY_DIR / "A.npy", mmap_mode="r")
    SP = np.load(POLICY_DIR / "SP.npy", mmap_mode="r")
    tr = np.flatnonzero(np.asarray(SP) == 0)
    rng = np.random.default_rng(7)
    bc_idx = np.sort(rng.choice(tr, size=2_000_000, replace=False))
    bc_S = torch.tensor(_scaled(np.asarray(S[bc_idx])), device=dev)
    bc_A = np.asarray(A[bc_idx])
    bc_f = torch.tensor(P._sign_class(bc_A[:, 0]), device=dev)
    bc_s = torch.tensor(P._sign_class(bc_A[:, 1]), device=dev)
    bc_y = torch.tensor(np.clip(bc_A[:, 2] / P.A_SCALE[2], -1, 1), device=dev,
                        dtype=torch.float32).unsqueeze(1)
    bc_j = torch.tensor((bc_A[:, 3] > 0.5).astype(np.float32), device=dev).unsqueeze(1)

    routes = race.training_routes()
    opt = torch.optim.Adam(actor.parameters(), lr=a.lr)
    ce, mse, bce = torch_nn.CrossEntropyLoss(), torch_nn.MSELoss(), torch_nn.BCEWithLogitsLoss()

    agg = {"S": [], "f": [], "s": [], "y": [], "j": []}
    log = []
    t0 = time.time()
    for rnd in range(1, a.rounds + 1):
        st = rollout_states(actor, routes, a.n_per_route, a.ticks, dev)
        sel = np.random.default_rng(rnd).choice(len(st), size=min(a.keep_per_round, len(st)),
                                                replace=False)
        st = st[sel]
        f, s, y, j, d = expert.query(st)
        inside = d <= cut
        frac_out = float(1.0 - inside.mean())
        agg["S"].append(st[inside])
        agg["f"].append(f[inside]); agg["s"].append(s[inside])
        agg["y"].append(y[inside]); agg["j"].append(j[inside])

        # Weight the aggregate per *state*, not per tick. A stalled policy emits the same
        # observation for thousands of consecutive ticks; without this the training set is a
        # headcount of how long the bot was stuck, and gradient descent obliges by learning to be
        # stuck. Deduplication was already being done for compute inside `query`; not doing it here
        # too is what let round 1 collapse.
        rawS = np.concatenate(agg["S"])
        _, keep_idx = np.unique(np.round(rawS / a.dedup_grid).astype(np.int32), axis=0,
                                return_index=True)
        AS = torch.tensor(rawS[keep_idx], device=dev)
        Af = torch.tensor(np.concatenate(agg["f"])[keep_idx], device=dev)
        As = torch.tensor(np.concatenate(agg["s"])[keep_idx], device=dev)
        Ay = torch.tensor(np.concatenate(agg["y"])[keep_idx], device=dev,
                          dtype=torch.float32).unsqueeze(1)
        Aj = torch.tensor(np.concatenate(agg["j"])[keep_idx], device=dev,
                          dtype=torch.float32).unsqueeze(1)

        n_new = int(a.batch * (1 - a.bc_mix))
        n_bc = a.batch - n_new
        losses = []
        for _ in range(a.steps):
            i = torch.randint(0, AS.shape[0], (n_new,), device=dev)
            b = torch.randint(0, bc_S.shape[0], (n_bc,), device=dev)
            x = torch.cat([AS[i], bc_S[b]], 0)
            lf, ls, ly, lj = actor(x)
            loss = (ce(lf, torch.cat([Af[i], bc_f[b]])) +
                    ce(ls, torch.cat([As[i], bc_s[b]])) +
                    10.0 * mse(ly, torch.cat([Ay[i], bc_y[b]])) +
                    bce(lj, torch.cat([Aj[i], bc_j[b]])))
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            losses.append(float(loss.detach()))
        entry = {"round": rnd, "visited": int(len(st)), "aggregate": int(AS.shape[0]),
                 "aggregate_before_dedup": int(len(rawS)),
                 "frac_no_human_answer": round(frac_out, 4),
                 "neighbour_dist_p50": round(float(np.percentile(d, 50)), 4),
                 "neighbour_dist_p90": round(float(np.percentile(d, 90)), 4),
                 "cut": round(cut, 4), "loss": round(float(np.mean(losses[-500:])), 4),
                 "s": round(time.time() - t0, 1)}
        log.append(entry)
        print(f"[runda {rnd}/{a.rounds}] besökta {entry['visited']:,}  "
              f"utan mänskligt svar {frac_out * 100:5.1f}%  aggregat {entry['aggregate']:,}  "
              f"loss {entry['loss']:.4f}  {entry['s']:.0f}s", flush=True)
        torch.save({"actor": actor.state_dict(), "width": 512, "depth": 3,
                    "s_scale": P.S_SCALE, "state_cols": P.STATE_COLS, "kind": "disc",
                    "round": rnd, "log": log}, OUT / a.ckpt)
        (OUT / f"log_{a.ckpt.replace('.pt', '')}.json").write_text(json.dumps(log, indent=1))
    print(f"sparade {OUT / a.ckpt}")


if __name__ == "__main__":
    main()
