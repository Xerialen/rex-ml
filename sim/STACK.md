# RL training stack status (Sample Factory / APPO)

Datum: 2026-07-30. Maskin: vmonster (H100 NVL 96 GB, driver 595.71.05, 64 kärnor).

## Venv-val

| venv | syfte | python | torch | numpy |
|---|---|---|---|---|
| `~/rex-ml/.venv` | pipeline/ (befintlig, uv-skapad) | 3.12.3 | 2.13.0+cu130 | 2.5.1 |
| `~/rex-ml/sim/.venv-sf` | **Sample Factory-träning (ny)** | 3.12.3 | 2.13.0+cu130 | 1.26.4 |

**Varför separat venv:** `uv pip install --dry-run sample-factory` i huvud-venven lämnade
torch orörd men ville **nedgradera numpy 2.5.1 -> 1.26.4** (sample-factory 2.1.1 pinnar
numpy<2). Att nedgradera numpy i pipeline-venven bryter regeln "riv inget befintligt",
så SF fick egen venv med identisk torch (2.13.0+cu130, hardlänkad ur uv-cachen — 5.0 GB
på disk men nästan noll extra block).

## Versioner i sim/.venv-sf

- sample-factory **2.1.1** (API v2.x)
- torch 2.13.0+cu130 — CUDA OK: `torch.cuda.get_device_name(0)` = "NVIDIA H100 NVL",
  matmul-smoke 10x 4096^3 på 0.149 s
- gymnasium 0.29.1 (SF pinnar <1.0)
- numpy 1.26.4, pybind11 3.0.4
- Byggkedja (system): gcc/g++ 13.3.0, OpenMP OK (64 trådar), **cmake SAKNAS i PATH**
  (installera vid behov: `uv pip install cmake ninja` i .venv-sf eller apt)

## Smoke-test (godkänt)

```
sim/.venv-sf/bin/python -m sf_examples.train_custom_env_custom_model \
  --algo=APPO --env=my_custom_env_v1 --experiment=sf_smoke \
  --train_for_env_steps=20000 --num_workers=4 --num_envs_per_worker=4 \
  --batch_size=1024 --device=gpu
```
Resultat: 21 504 env-steg på ~18 s (FPS 1197.8), learner på GPU, ren avslutning.

## Custom env-registrering (SF 2.x API)

```python
import gymnasium as gym
import numpy as np
from sample_factory.envs.env_utils import register_env
from sample_factory.cfg.arguments import parse_sf_args, parse_full_cfg
from sample_factory.train import run_rl

class RexMoveEnv(gym.Env):
    def __init__(self, full_env_name, cfg, render_mode=None):
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, (OBS_DIM,), np.float32)
        # HYBRID kontinuerlig + diskret: STÖDS NATIVT via gym.spaces.Tuple.
        # SF:s TupleActionDistribution splittar en gemensam logit-vektor i
        # oberoende huvuden (log-prob = summa, entropi = summa). Ingen workaround.
        # OBS: Box-delen måste vara platt 1-D ("Non-trivial shape Box action
        # spaces not currently supported"). Dict-space stöds INTE för actions.
        self.action_space = gym.spaces.Tuple((
            gym.spaces.Box(-1.0, 1.0, (3,), np.float32),  # yaw/pitch/…-delta
            gym.spaces.Discrete(2),                        # jump
            gym.spaces.Discrete(2),                        # fire/rj
        ))
    def reset(self, **kw): return obs, {}
    def step(self, action):
        # action = platt np-array [box0,box1,box2, disc0, disc1] (Tuple konkateneras)
        return obs, rew, terminated, truncated, {}

def make_env(full_env_name, cfg=None, env_config=None, render_mode=None):
    return RexMoveEnv(full_env_name, cfg, render_mode)

def main():
    register_env("rex_move_v1", make_env)          # <-- hela registreringen
    parser, _ = parse_sf_args()                    # + ev. egna flaggor via parser
    cfg = parse_full_cfg(parser)
    return run_rl(cfg)                             # startar APPO
```

Körs: `python -m <modul> --algo=APPO --env=rex_move_v1 --experiment=...`.
Egen encoder (MLP) registreras vid behov med
`global_model_factory().register_encoder_factory(fn)`
(se `sf_examples/train_custom_env_custom_model.py` i site-packages för fullt mönster).
C++-vektoriserad miljö exponeras enklast per-env via pybind11 bakom detta gym-API;
SF:s rollout-workers ger processparallellism ovanpå.
