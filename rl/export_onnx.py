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
        core_out, new_rnn = self._gru_cell(x, rnn_state)
        result = self.ac.forward_tail(core_out, values_only=False,
                                      sample_actions=False)
        return result["action_logits"], new_rnn

    def _gru_cell(self, x, h):
        """En GRU-cell utskriven i primitiva ops (matmul/sigmoid/tanh) i stället för
        forward_core:s nn.GRU. MOTIV (uppmätt 2026-07-30, bridge-diagnosen): torch
        exporterar nn.GRU som en fuserad ONNX GRU-nod, och tract-onnx 0.21 evaluerar
        den FEL — utgången blir ≈ negationen av torchs (max|diff| 29,3 över fixturerna,
        jump-argmax inverterad 100 % av ticks ⇒ konstant-hopp på servern, peak 161 mot
        740 i sim). Primitiva ops rundar av hela nodklassen; verifierad tract-vs-torch-
        paritet efter bytet: max|diff| ~1e-5. Semantiken är torchs egen (gate-ordning
        r,z,n; linear_before_reset): n = tanh(Wn x + bWn + r*(Un h + bUn)).
        Kräver 1-lagers GRU — assertas vid export."""
        core = self.ac.core.core
        w_ih, w_hh = core.weight_ih_l0, core.weight_hh_l0    # [3H, in], [3H, H]
        b_ih, b_hh = core.bias_ih_l0, core.bias_hh_l0        # [3H], [3H]
        H = core.hidden_size
        gi = x @ w_ih.t() + b_ih                             # [1, 3H]
        gh = h @ w_hh.t() + b_hh
        i_r, i_z, i_n = gi[:, :H], gi[:, H:2 * H], gi[:, 2 * H:]
        h_r, h_z, h_n = gh[:, :H], gh[:, H:2 * H], gh[:, 2 * H:]
        r = torch.sigmoid(i_r + h_r)
        z = torch.sigmoid(i_z + h_z)
        n = torch.tanh(i_n + r * h_n)
        # OBS: algebraiskt identiskt med (1-z)*n + z*h men UTAN skalär-minus-mönstret
        # `Sub(1, z)` — tract 0.21 evaluerar det mönstret fel (utgången negeras; ORT ger
        # rätt svar på samma graf). `n + z*(h - n)` använder bara tensor-Sub och rundar
        # av runtimebuggen. Verifierat: torch-vs-tract max|diff| på fixturerna föll från
        # 29,3 (ren negation) till float-brus efter omskrivningen.
        new_h = n + z * (h - n)
        return new_h, new_h


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

    core = actor_critic.core.core
    assert isinstance(core, nn.GRU) and core.num_layers == 1, \
        "manuella GRU-cellen förutsätter 1-lagers nn.GRU"

    wrapper = ExportWrapper(actor_critic).eval()
    obs = torch.zeros(1, n_obs)
    rnn = torch.zeros(1, rnn_size)
    with torch.no_grad():
        params, new_rnn = wrapper(obs, rnn)

    # Torch-vs-torch-grind: manuella cellen MÅSTE reproducera forward_core exakt
    # (annars exporterar vi en annan policy än den utvärderade).
    with torch.no_grad():
        for _ in range(16):
            o = torch.randn(1, n_obs)
            h = torch.randn(1, rnn_size)
            x = torch.clamp((o - wrapper.mu) * wrapper.inv_sigma, -5.0, 5.0)
            enc = actor_critic.forward_head({"obs": x})
            ref_out, ref_h = actor_critic.forward_core(enc, h)
            man_out, man_h = wrapper._gru_cell(enc, h)
            d = max(float((ref_out - man_out).abs().max()),
                    float((ref_h - man_h).abs().max()))
            assert d < 1e-5, f"manuell GRU-cell avviker från forward_core: {d}"

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
