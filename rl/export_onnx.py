"""Exportera en SF-checkpoint till ONNX för in-process-inferens i rtx-boten.

    PYTHONPATH=. sim/.venv-sf/bin/python -m rl.export_onnx \
        pipeline/out/rl/train_dir/<experiment> --out pipeline/out/rl/<namn>.onnx

Grafens kontrakt (Rust-sidan litar på detta, ändra ALDRIG utan versionsbump):
  in:  obs[1, 97] f32 (RÅ, onormaliserad — normalizern bakas in i grafen),
       rnn_state[1, R] f32
  ut:  action_params[1, P] f32 — konkatenerade huvuden i ordningen
       (box-means[2], box-logstd[2], fwd-logits[2], side-logits[3], jump-logits[2]),
       new_rnn_state[1, R] f32
  Greedy-avkodning: dyaw=means[0], dpitch=means[1] (redan i [-1,1]-skala),
  fwd=argmax(fwd-logits), side=argmax(side-logits), jump=argmax(jump-logits).
Vid sidan av .onnx skrivs en .json med metadata (obs-dim, rnn-dim, param-layout,
spec-konstanter ur rl/spec.py) som Rust-sidan validerar mot.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from rl import spec as S
from rl.eval_gate1 import load_policy


class ExportWrapper(nn.Module):
    """SF:s ObservationNormalizer är TorchScript och kan inte traceas — dess
    formel (clamp((x−μ)/√(σ²+eps), ±clip), running_mean_std.py) bakas i stället
    in aritmetiskt med buffertarna ur checkpointen."""

    def __init__(self, actor_critic):
        super().__init__()
        self.ac = actor_critic
        bufs = dict(actor_critic.named_buffers())
        mean_key = next(k for k in bufs if k.endswith("obs.running_mean"))
        var_key = next(k for k in bufs if k.endswith("obs.running_var"))
        self.register_buffer("mu", bufs[mean_key].float().view(1, -1))
        self.register_buffer("inv_sigma",
                             (1.0 / torch.sqrt(bufs[var_key].float() + 1e-5)).view(1, -1))

    def forward(self, obs, rnn_state):
        x_norm = torch.clamp((obs - self.mu) * self.inv_sigma, -5.0, 5.0)
        x = self.ac.forward_head({"obs": x_norm})
        core_out, new_rnn = self.ac.forward_core(x, rnn_state)
        result = self.ac.forward_tail(core_out, values_only=False,
                                      sample_actions=False)
        return result["action_logits"], new_rnn


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("exp_dir", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    # SF skriptar encoder/decoder-MLP:erna (torch.jit.script) vid konstruktion,
    # och ONNX-tracern vägrar skriptade submoduler. Neutralisera till identitet
    # INNAN modellen byggs — state_dict-layouten är identisk, vikterna laddar rent.
    torch.jit.script = lambda m, *a, **k: m

    cfg, env, actor_critic = load_policy(args.exp_dir, "cpu")
    from sample_factory.model.model_utils import get_rnn_size
    rnn_size = get_rnn_size(cfg)
    n_obs = env.observation_space.shape[0]

    wrapper = ExportWrapper(actor_critic).eval()
    obs = torch.zeros(1, n_obs)
    rnn = torch.zeros(1, rnn_size)
    with torch.no_grad():
        params, new_rnn = wrapper(obs, rnn)

    torch.onnx.export(
        wrapper, (obs, rnn), str(args.out),
        input_names=["obs", "rnn_state"],
        output_names=["action_params", "new_rnn_state"],
        opset_version=17, dynamo=False,
    )

    # sanity: onnxruntime saknas ofta — verifiera åtminstone mot torch igen
    with torch.no_grad():
        p2, r2 = wrapper(torch.randn(1, n_obs), torch.randn(1, rnn_size))

    meta = {
        "contract_version": 1,
        "n_obs": n_obs,
        "rnn_size": rnn_size,
        "n_action_params": int(params.shape[1]),
        "param_layout": ["box_mean_dyaw", "box_mean_dpitch",
                         "box_logstd_dyaw", "box_logstd_dpitch",
                         "fwd_logit_0", "fwd_logit_1",
                         "side_logit_none", "side_logit_left", "side_logit_right",
                         "jump_logit_0", "jump_logit_1"],
        "spec": {
            "tick_dt": S.TICK_DT, "max_dyaw_deg": S.MAX_DYAW_DEG,
            "max_dpitch_deg": S.MAX_DPITCH_DEG, "forwardmove": S.FORWARDMOVE,
            "sidemove": S.SIDEMOVE, "speed_norm": S.SPEED_NORM,
            "pitch_min": S.PITCH_MIN, "pitch_max": S.PITCH_MAX,
            "n_rays": S.ObsSpec().rays.n_rays, "ray_max_dist": S.ObsSpec().rays.max_dist,
        },
        "source_experiment": str(args.exp_dir),
    }
    args.out.with_suffix(".json").write_text(json.dumps(meta, indent=1))
    print(f"exporterade {args.out} | obs {n_obs}, rnn {rnn_size}, "
          f"params {int(params.shape[1])} (förväntat 11)")


if __name__ == "__main__":
    main()
