"""The 100m corridor runs, packed for the replay page: the analytic ceiling against the policy.

The owner's gate is a peak of 790 u/s down the runway. Two runs answer it side by side on the same
4308 u of straight floor — a hand-written strafe-jumper that reaches it, and the trained policy that
does not — so the gap is something to scrub through rather than a pair of numbers in a table.

Frames are the page's 25-byte layout (`x, y, z, yaw` f32, flags u8, `speed` f32, `pitch` f32). Neither
subject has a view pitch here, so that column is zero for both and the first-person camera is level.
"""

from __future__ import annotations

import struct

import numpy as np

from . import strafe_expert as SE
from .record_replay import air_segments

TICK_DT = 1.0 / 77.0
FMT = "<ffffBff"


def _pack(frames: list[tuple]) -> bytes:
    b = bytearray()
    for (x, y, z, yaw, og, jmp, spd) in frames:
        b += struct.pack(FMT, x, y, z, yaw, (1 if og else 0) | (2 if jmp else 0), spd, 0.0)
    return bytes(b)


def _rollout(n: int, policy=None, dev: str = "cuda") -> tuple[list[list[tuple]], np.ndarray]:
    """One batch down the corridor. `policy=None` runs the analytic strafe-jumper."""
    import rex_env

    env = rex_env.PyVecEnv.from_path(SE.MAP, [SE.START, SE.END], n, 24.0, 1600)
    obs = env.reset()
    side = -np.ones(n, np.float32)
    launched = np.zeros(n, bool)
    done = np.zeros(n, bool)
    arrived = np.zeros(n, bool)
    frames: list[list[tuple]] = [[] for _ in range(n)]

    for _ in range(1602):
        o, v, g, y = env.origins, env.velocities, env.on_ground, env.view_yaws
        sp = np.linalg.norm(v[:, :2], axis=1)
        if policy is None:
            a, side, launched = SE.act(o, v, g, y, side, launched)
        else:
            a = policy(obs)
        for i in np.flatnonzero(~done):
            frames[i].append((float(o[i, 0]), float(o[i, 1]), float(o[i, 2]), float(y[i]),
                              bool(g[i] > 0.5), bool(a[i, 3] > 0.5), float(sp[i])))
        obs, parts, dn = env.step(a)
        parts = np.asarray(parts)
        ts = env.terminal_states
        for i in np.flatnonzero((~done) & np.asarray(dn)):
            done[i] = True
            arrived[i] = parts[i, 4] > 0
            # The arriving tick, from the environment's kept copy — `origins` has already been
            # advanced past it by the auto-reset.
            frames[i].append((float(ts[i, 0]), float(ts[i, 1]), float(ts[i, 2]), float(ts[i, 3]),
                              True, False, float(np.linalg.norm(ts[i, 4:6]))))
        if done.all():
            break
    return frames, arrived


def _record(label: str, note: str, frames: list[list[tuple]], arrived: np.ndarray,
            base: int) -> tuple[bytes, dict]:
    blob = bytearray()
    runs = []
    order = np.argsort([-max(f[6] for f in fr) for fr in frames])
    for i in order:
        fr = frames[i]
        off = base + len(blob)
        blob += _pack(fr)
        sp = np.array([f[6] for f in fr], np.float32)
        moving = sp[sp > 1.0]
        runs.append({
            "count": 1, "attempt_ids": [int(i)],
            "outcome": "arrived" if arrived[i] else "timeout",
            "ticks": len(fr), "time_s": round(len(fr) * TICK_DT, 3),
            "wall_contact": False, "offset": off, "n_frames": len(fr),
            "label": f"topp {sp.max():.0f} u/s",
            "note": f"{len(fr)} tick, {len(fr) * TICK_DT:.2f} s, "
                    f"{'kom fram' if arrived[i] else 'kom inte fram'}",
            "median_speed_ups": round(float(np.median(moving)), 1) if moving.size else 0.0,
            "peak_speed_ups": round(float(sp.max()), 1),
            "frac_above_320": round(float((moving > 320).mean()), 3) if moving.size else 0.0,
            "frac_airborne": round(float(np.mean([not f[4] for f in fr])), 3),
            "jump_presses": int(sum(1 for k in range(1, len(fr)) if fr[k][5] and not fr[k - 1][5])),
            "segments": air_segments(fr),
        })
    peak = max(r["peak_speed_ups"] for r in runs)
    rec = {
        "route": "100m_korridor", "map": "100m", "decode": label,
        "geometry": note, "attempts": len(frames), "distinct_trajectories": len(runs),
        "arrival_rate": float(arrived.mean()),
        "median_s": round(float(np.median([r["time_s"] for r in runs if r["outcome"] == "arrived"])), 3)
        if arrived.any() else None,
        "peak_speed_ups": peak,
        "gate_s": None, "pass_s": None,
        "path": [list(SE.START), list(SE.END)],
        # The page draws the arrival box from this; a record without it took the frame loop down on
        # every tick, which reads as a broken run rather than a missing field.
        "goal": list(SE.END),
        "start": list(SE.START),
        "group_label": f"{label} — topp {peak:.0f} u/s mot grinden {SE.PEAK_GATE:.0f} "
                       f"({'klarar' if peak >= SE.PEAK_GATE else 'klarar inte'})",
        "runs": runs,
    }
    return bytes(blob), rec


def build(base: int, ckpt: str | None, n: int = 8, dev: str = "cuda") -> tuple[bytes, list[dict]]:
    """Both corridor records, ready to append to the page's frame blob at byte offset `base`."""
    blob = bytearray()
    records = []

    fr, ar = _rollout(n)
    b, rec = _record("analytisk", "analytisk strafe-jumper", fr, ar, base + len(blob))
    blob += b
    records.append(rec)

    if ckpt:
        import torch

        from . import policy as P

        ck = torch.load(ckpt, map_location=dev, weights_only=False)
        actor = P.make_disc_actor(14, ck.get("width", 512), ck.get("depth", 3))().to(dev)
        actor.load_state_dict(ck["actor"])
        actor.eval()

        def run_policy(obs):
            t = torch.tensor(obs, device=dev, dtype=torch.float32)
            with torch.no_grad():
                fl, sl, yaw, jl = actor(t)
                f = torch.distributions.Categorical(logits=fl).sample()
                s = torch.distributions.Categorical(logits=sl).sample()
                j = (torch.rand_like(jl.squeeze(-1)) < torch.sigmoid(jl.squeeze(-1))).float()
            return np.stack([(f.cpu().numpy() - 1).astype(np.float32),
                             (s.cpu().numpy() - 1).astype(np.float32),
                             yaw.squeeze(-1).cpu().numpy(), j.cpu().numpy()], 1).astype(np.float32)

        fr, ar = _rollout(n, policy=run_policy, dev=dev)
        b, rec = _record(f"policy {Path_name(ckpt)}", f"ML-policy {Path_name(ckpt)}",
                         fr, ar, base + len(blob))
        blob += b
        records.append(rec)

    return bytes(blob), records


def Path_name(p: str) -> str:
    from pathlib import Path

    return Path(p).stem
