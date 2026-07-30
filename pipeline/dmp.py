"""STEP 2c — Dynamic Movement Primitives for rocket jumps.

Standard Ijspeert/Schaal DMP, one per Cartesian DOF, in the SE(2) body frame of
the blast tick:

  Canonical system      tau * s_dot = -alpha_s * s                (s: 1 -> ~0)
  Transformation system tau * v_dot = alpha (beta (g - y) - v) + f(s)
                        tau * y_dot = v
  Forcing term          f(s) = (sum_i psi_i(s) w_i / sum_i psi_i(s)) * s

The textbook forcing term carries a `(g - y0)` factor so the shape rescales with
the goal. That factor is a trap here and it was measured to be one: a rocket jump
that goes straight up has |g - y0| ~ 0 in the horizontal DOFs, the per-demo
weights divide by it, and W explodes. Cross-demonstration regression on those
weights then produced a median landing error of 5,528 units against a 4.08-unit
per-demo reconstruction ceiling. Dropping the scaling costs amplitude
generalisation -- which the cross-demo regression on task features supplies
anyway -- and makes W finite and regressable.

Fitting is exactly the linear regression BRIEF 2c asks for, twice over:

  1. **per demonstration** -- given a recorded path, the target forcing term is
     algebraic, so w is a weighted least-squares solve. Closed form, no search.
  2. **across demonstrations** -- ridge regression from the SE(2)-invariant task
     parameters to the stacked weights, `W = A phi(task) + b`, which is what
     lets the planner ask for a jump it has never seen.

Held-out landing accuracy is the number that matters and the one 2a's widening
decision was deferred to: if val error is sample-limited it will sit well above
train error and fall as data grows; if it is model-limited the two converge.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from . import config as C
from . import maneuvers

OUT = C.OUT_DIR / "dmp"

ALPHA_S = 4.0          # canonical decay; s(1) ~ e^-4 = 0.018
ALPHA_Y = 25.0         # critically damped when beta = alpha/4
BETA_Y = ALPHA_Y / 4.0
DOF = 3                # forward, right, up -- in the blast-tick body frame


def psi(s, centers, widths):
    """Gaussian basis in canonical-system phase, shape (T, K)."""
    return np.exp(-widths[None, :] * (s[:, None] - centers[None, :]) ** 2)


def basis(n_basis: int):
    """Centres spaced evenly in *time*, mapped through the canonical system."""
    t = np.linspace(0.0, 1.0, n_basis)
    centers = np.exp(-ALPHA_S * t)
    widths = np.zeros(n_basis)
    widths[:-1] = 1.0 / ((centers[1:] - centers[:-1]) ** 2 + 1e-12)
    widths[-1] = widths[-2]
    return centers, widths


def resample(y, t, n):
    """Uniform-time resample of a ragged trajectory to n samples."""
    tt = np.linspace(t[0], t[-1], n)
    return np.interp(tt, t, y), tt


def fit_one(path, dt, n_basis=12, n_resample=64):
    """Per-demonstration weights. `path` is (T, DOF); returns (n_basis, DOF), y0, g, tau."""
    T = len(path)
    t = np.concatenate([[0.0], np.cumsum(dt[:T - 1])])
    tau = float(t[-1]) if t[-1] > 1e-6 else 1e-6

    Y = np.stack([resample(path[:, d], t, n_resample)[0] for d in range(DOF)], 1)
    tt = np.linspace(0, tau, n_resample)
    h = tt[1] - tt[0]
    Yd = np.gradient(Y, h, axis=0)
    Ydd = np.gradient(Yd, h, axis=0)

    s = np.exp(-ALPHA_S * tt / tau)
    centers, widths = basis(n_basis)
    P = psi(s, centers, widths)
    Pn = P / np.maximum(P.sum(1, keepdims=True), 1e-12)

    y0, g = Y[0], Y[-1]
    W = np.zeros((n_basis, DOF))
    for d in range(DOF):
        # f_target from the transformation system, solved for the forcing term
        f_t = (tau ** 2 * Ydd[:, d] - ALPHA_Y * (BETA_Y * (g[d] - Y[:, d]) - tau * Yd[:, d]))
        # locally weighted regression, one scalar per basis function, unscaled
        for k in range(n_basis):
            den = float((P[:, k] * s * s).sum())
            W[k, d] = float((P[:, k] * s * f_t).sum()) / den if den > 1e-9 else 0.0
    return W, y0, g, tau


def integrate(W, y0, g, tau, n_steps=64, n_basis=None, substeps=4):
    """Roll the DMP forward. Returns (n_steps, DOF).

    `substeps` guards the Euler integration: alpha=25 with tau ~ 1 s and 64
    output samples sits close to the stability edge, and a diverged rollout is
    indistinguishable from a bad fit in the error metric.
    """
    n_basis = n_basis if n_basis is not None else W.shape[0]
    centers, widths = basis(n_basis)
    g = np.asarray(g, float)
    y = np.asarray(y0, float).copy()
    v = np.zeros(DOF)
    out = np.empty((n_steps, DOF))
    out[0] = y
    dt = tau / (n_steps - 1) / substeps
    s = 1.0
    for i in range(1, n_steps):
        for _ in range(substeps):
            p = np.exp(-widths * (s - centers) ** 2)
            fs = (p @ W) / max(p.sum(), 1e-12) * s
            vd = (ALPHA_Y * (BETA_Y * (g - y) - v) + fs) / tau
            v = v + vd * dt
            y = y + v / tau * dt
            s = s + (-ALPHA_S * s / tau) * dt
        out[i] = y
    return out


# --------------------------------------------------------------------------
# task parameters and the cross-demonstration regression
# --------------------------------------------------------------------------

def task_features(j):
    """SE(2)-invariant task descriptor known at the moment of the blast."""
    return np.array([
        j["speed0"] / 400.0,
        float(j["vf"][0]) / 400.0,
        float(j["vr"][0]) / 400.0,
        float(j["vz"][0]) / 400.0,
        float(j["pitch0"]) / 90.0,
        1.0,
    ], dtype=np.float64)


def goal_features(j):
    """Where the jump is asked to land, body frame of the blast."""
    return np.array([j["px"][-1], j["py"][-1], j["pz"][-1]], dtype=np.float64)


def build(n_basis=12, n_resample=64, ridge=1.0, out: Path = OUT):
    out.mkdir(parents=True, exist_ok=True)
    js = maneuvers.jump_frames()
    js = [j for j in js if j["n"] >= 8]
    print(f"{len(js)} rocket jumps with >= 8 ticks", flush=True)

    Ws, Y0, G, TAU, PHI, SPL, NT = [], [], [], [], [], [], []
    for j in js:
        path = np.stack([j["px"], j["py"], j["pz"]], 1)
        W, y0, g, tau = fit_one(path, j["dt"], n_basis, n_resample)
        if not np.isfinite(W).all():
            continue
        Ws.append(W.reshape(-1)); Y0.append(y0); G.append(g); TAU.append(tau)
        PHI.append(np.concatenate([task_features(j), goal_features(j) / 400.0]))
        SPL.append(j["split"]); NT.append(j["n"])
    W = np.stack(Ws); PHI = np.stack(PHI); G = np.stack(G)
    TAU = np.array(TAU); SPL = np.array(SPL, dtype=object); NT = np.array(NT)
    print(f"fitted {W.shape[0]} demonstrations, W dim {W.shape[1]}, phi dim {PHI.shape[1]}")

    np.savez(out / "fits.npz", W=W, PHI=PHI, G=G, TAU=TAU,
             SPL=SPL.astype(str), NT=NT, n_basis=n_basis, n_resample=n_resample)
    return js, W, PHI, G, TAU, SPL


def ridge_fit(X, Y, lam):
    Xb = np.concatenate([X, np.ones((len(X), 1))], 1)
    A = Xb.T @ Xb + lam * np.eye(Xb.shape[1])
    return np.linalg.solve(A, Xb.T @ Y)


def _path_err(yhat, path):
    """Deviation of a rolled DMP from the recorded path, resampled to match."""
    n = len(yhat)
    t = np.linspace(0, 1, len(path))
    tt = np.linspace(0, 1, n)
    ref = np.stack([np.interp(tt, t, path[:, d]) for d in range(DOF)], 1)
    e = np.linalg.norm(yhat - ref, axis=1)
    return float(e.mean()), float(e.max()), float(np.linalg.norm(yhat[-1] - path[-1]))


def evaluate(n_basis=12, n_resample=64, lams=(0.1, 1.0, 10.0, 100.0, 1000.0),
             out: Path = OUT):
    """Two regimes, because they answer different questions.

    **A. goal given** — the BRIEF step 3 planner picks the landing spot and the
    DMP has to produce the path to it. Landing error is then near-trivial (the
    goal is the attractor), so the number that matters is deviation from the
    human path *along the way*, which is exactly the quantity the step 4
    Tracking Guard trips on at 32 units.

    **B. goal predicted** — nothing but the state at the blast is known, and the
    DMP must say where the jump ends up. This is what tells the planner which
    rocket jumps are reachable at all, and it is the honest "landing accuracy".
    """
    js, W, PHI, G, TAU, SPL = build(n_basis, n_resample, out=out)
    tr, va, te = SPL == "train", SPL == "val", SPL == "test"
    print(f"train {tr.sum()}  val {va.sum()}  test {te.sum()}\n")

    PHI_A = PHI                      # includes the goal
    PHI_B = PHI[:, :6]               # task features only, no goal leakage

    rows = []
    for mode, X, use_goal in (("A goal given", PHI_A, True),
                              ("B goal predicted", PHI_B, False)):
        print(f"--- mode {mode} ---")
        for lam in lams:
            Cw = ridge_fit(X[tr], W[tr], lam)
            Ct = ridge_fit(X[tr], TAU[tr][:, None], lam)
            Cg = ridge_fit(X[tr], G[tr], lam) if not use_goal else None
            res = {}
            for nm, m in (("train", tr), ("val", va), ("test", te)):
                if not m.any():
                    continue
                Xb = np.concatenate([X[m], np.ones((m.sum(), 1))], 1)
                Wp, Tp = Xb @ Cw, (Xb @ Ct).ravel()
                Gp = G[m] if use_goal else Xb @ Cg
                mean_e, max_e, land_e = [], [], []
                for k, i in enumerate(np.flatnonzero(m)):
                    j = js[i]
                    path = np.stack([j["px"], j["py"], j["pz"]], 1)
                    yhat = integrate(Wp[k].reshape(n_basis, DOF), path[0], Gp[k],
                                     float(np.clip(Tp[k], 0.05, 5.0)), n_resample, n_basis)
                    a, b, c = _path_err(yhat, path)
                    mean_e.append(a); max_e.append(b); land_e.append(c)
                mean_e, max_e, land_e = map(np.array, (mean_e, max_e, land_e))
                res[nm] = dict(n=int(m.sum()),
                               path_mean_p50=float(np.percentile(mean_e, 50)),
                               path_max_p50=float(np.percentile(max_e, 50)),
                               path_max_p90=float(np.percentile(max_e, 90)),
                               land_p50=float(np.percentile(land_e, 50)),
                               land_p90=float(np.percentile(land_e, 90)),
                               frac_max_under_32=float((max_e < 32).mean()),
                               frac_land_under_32=float((land_e < 32).mean()))
            rows.append(dict(mode=mode, lam=lam, **res))
            print(f"  lam={lam:<7} " + " | ".join(
                f"{k}: path_mean {v['path_mean_p50']:5.1f} max {v['path_max_p50']:5.1f} "
                f"land {v['land_p50']:5.1f} (<32u {100*v['frac_land_under_32']:.0f}%)"
                for k, v in res.items()), flush=True)
        print()

    # ceiling: each demo rolled with its own W, tau and goal
    mean_c, max_c, land_c = [], [], []
    for i, j in enumerate(js):
        path = np.stack([j["px"], j["py"], j["pz"]], 1)
        yhat = integrate(W[i].reshape(n_basis, DOF), path[0], G[i], TAU[i],
                         n_resample, n_basis)
        a, b, c = _path_err(yhat, path)
        mean_c.append(a); max_c.append(b); land_c.append(c)
    ceil = dict(path_mean_p50=float(np.percentile(mean_c, 50)),
                path_max_p50=float(np.percentile(max_c, 50)),
                land_p50=float(np.percentile(land_c, 50)))
    print(f"per-demonstration ceiling (own W, tau, goal): path_mean {ceil['path_mean_p50']:.2f}  "
          f"path_max {ceil['path_max_p50']:.2f}  land {ceil['land_p50']:.2f} u")

    (out / "eval.json").write_text(json.dumps(
        dict(n_basis=n_basis, n_resample=n_resample, rows=rows, ceiling=ceil), indent=2))
    return rows, ceil


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-basis", type=int, default=12)
    ap.add_argument("--n-resample", type=int, default=64)
    a = ap.parse_args()
    evaluate(a.n_basis, a.n_resample)
