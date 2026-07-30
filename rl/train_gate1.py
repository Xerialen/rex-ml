"""Gate 1-träningsentré (Sample Factory APPO, sim/.venv-sf).

Körs:  sim/.venv-sf/bin/python -m rl.train_gate1 --algo=APPO --env=qw_gate1 \
           --experiment=<namn> --use_rnn=True --device=gpu [--qw_backend=stub]

--qw_backend=stub finns ENDAST för pipeline-smoke (fysikfri stubb);
all riktig träning kräver qwsim (bit-exakta pmove.c, libqwsim).
Checkpoints hamnar under train_dir/<experiment>/ (SF-standard).
"""
from __future__ import annotations

import sys

from sample_factory.cfg.arguments import parse_full_cfg, parse_sf_args
from sample_factory.envs.env_utils import register_env
from sample_factory.train import run_rl

from rl.sf_env import make_env


def main(argv=None):
    register_env("qw_gate1", make_env)
    parser, _ = parse_sf_args(argv=argv)
    parser.add_argument("--qw_backend", default="qwsim", choices=["qwsim", "stub"],
                        help="qwsim = libqwsim (riktig fysik); stub = endast smoke")
    cfg = parse_full_cfg(parser, argv=argv)
    return run_rl(cfg)


if __name__ == "__main__":
    sys.exit(main())
