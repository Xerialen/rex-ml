"""Gate 2-träningsentré (fritt strövande dm3). Startas i FAS 2 — efter Gate 1.

    PYTHONPATH=. sim/.venv-sf/bin/python -m rl.train_gate2 --algo=APPO \
        --env=qw_gate2 --experiment=<namn> --use_rnn=True --device=gpu

Curriculum A–D (BRIEF §4) styrs INTE av rl.curriculum_daemon (den är Gate 1-
specifik); fas 2 får egen daemonkriterielogik när steg A–C-regionerna fastställts
ur zonrastret (spawn_region-stöd finns redan i Gate2Config). Tills dess tränar
denna entré steg D-formen: slumpade starter över hela kartan.
Init från Gate 1-checkpoint: --restart_behavior=restart + SF:s init_checkpoint
utvärderas i fas 2 (transfer av strafe-kärnan är sannolikt värdefull).
"""
from __future__ import annotations

import sys

from sample_factory.cfg.arguments import parse_full_cfg, parse_sf_args
from sample_factory.envs.env_utils import register_env
from sample_factory.train import run_rl

from rl.sf_env import make_env_gate2


def main(argv=None):
    register_env("qw_gate2", make_env_gate2)
    parser, _ = parse_sf_args(argv=argv)
    parser.add_argument("--qw_backend", default="qwsim", choices=["qwsim", "stub"],
                        help="qwsim = libqwsim (riktig fysik); stub = endast smoke")
    parser.add_argument("--qw_gate1_mix_workers", type=int, default=6,
                        help="workers < N kör 100m-repetition (extremfart-registret)")
    parser.add_argument("--qw_vertical_rewards", action="store_true",
                        help="V1a+V2: klätterbonus per landning + gap-crossing-bonus")
    parser.add_argument("--qw_cell_rarity", action="store_true",
                        help="V1b: voxelnovelty viktad med bottens egen cellsällsynthet")
    parser.add_argument("--qw_novelty_bonus", type=float, default=1.5,
                        help="poäng per ny voxel (fartskalad)")
    parser.add_argument("--qw_rarity_lo", type=float, default=0.5,
                        help="min-multiplikator för novelty i översittna celler")
    parser.add_argument("--qw_rarity_hi", type=float, default=4.0,
                        help="max-multiplikator för novelty i sällan besökta celler")
    parser.add_argument("--qw_climb_coef", type=float, default=0.08,
                        help="V1a: poäng per unit höjdvinst vid landning (rise>=24)")
    parser.add_argument("--qw_gap_base", type=float, default=3.0,
                        help="V2: basbonus för gap-hopp (skalas med span, x2 vid djup>141)")
    parser.add_argument("--qw_height_coef", type=float, default=0.0,
                        help="höjdviktad fartinkomst: coef*z_norm*fart*rarity (0=av)")
    cfg = parse_full_cfg(parser, argv=argv)
    return run_rl(cfg)


if __name__ == "__main__":
    sys.exit(main())
