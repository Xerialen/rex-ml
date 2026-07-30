"""Checkpoint-skördaren: ratchet för greedy-peak under pågående träning.

Problem (uppmätt): greedy-peaken oscillerar mellan checkpoints (703→780→703)
medan SF roterar bort saves varannan minut — bra ögonblick RADERAS. Skördaren
greedy-evaluerar varje ny save och behåller bäst-hittills (kopia, inget raderas).

    SF_STDDEV_MAX=1.0 PYTHONPATH=. sim/.venv-sf/bin/python -m rl.harvest_best \
        pipeline/out/rl/train_dir/gate1_v1 --target 820

Skriver harvest/best.pth + harvest/best.json (peak, källfil, tid) och loggar
varje prövning till harvest/log.jsonl. Avslutar när target nåtts (kandidaten
är då säkrad på disk) — eller kör tills den stoppas.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

os.environ.setdefault("SF_STDDEV_MAX", "1.0")   # träningsparitet

import numpy as np
import torch


def greedy_peak(exp_dir: Path, device: str = "cpu") -> float:
    from rl.eval_gate1 import load_policy, run_episodes
    cfg, env, ac = load_policy(exp_dir, device)
    res = run_episodes(env, ac, cfg, n=1, device=device, sample=False)
    return float(res[0]["peak_speed"])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("exp_dir", type=Path)
    ap.add_argument("--target", type=float, default=820.0)
    ap.add_argument("--interval", type=float, default=30.0)
    args = ap.parse_args(argv)

    src = args.exp_dir / "checkpoint_p0"
    harvest = args.exp_dir / "harvest"
    eval_dir = harvest / "eval_dir"
    (eval_dir / "checkpoint_p0").mkdir(parents=True, exist_ok=True)
    shutil.copy(args.exp_dir / "config.json", eval_dir / "config.json")
    log = open(harvest / "log.jsonl", "a", buffering=1)

    best = -1.0
    best_meta = harvest / "best.json"
    if best_meta.exists():
        best = json.load(open(best_meta)).get("peak", -1.0)
        print(f"[skörd] återupptar, bäst hittills {best:.1f}")
    seen: set[str] = set()

    while True:
        cks = sorted(src.glob("checkpoint_*.pth"))
        fresh = [c for c in cks if c.name not in seen]
        if fresh:
            c = fresh[-1]
            seen.add(c.name)
            # stabil kopia innan rotationen hinner radera
            for old in (eval_dir / "checkpoint_p0").glob("checkpoint_*.pth"):
                old.unlink()          # egen arbetskopia, inget källmaterial
            try:
                shutil.copy(c, eval_dir / "checkpoint_p0" / c.name)
            except FileNotFoundError:
                time.sleep(args.interval)
                continue
            try:
                peak = greedy_peak(eval_dir)
            except Exception as e:     # halvskriven fil etc — hoppa
                log.write(json.dumps({"ckpt": c.name, "error": str(e)[:200],
                                      "t": time.time()}) + "\n")
                time.sleep(args.interval)
                continue
            entry = {"ckpt": c.name, "greedy_peak": round(peak, 1),
                     "best": round(max(best, peak), 1), "t": time.time()}
            log.write(json.dumps(entry) + "\n")
            print(f"[skörd] {c.name}: greedy {peak:.1f} (bäst {max(best, peak):.1f})")
            if peak > best:
                best = peak
                shutil.copy(eval_dir / "checkpoint_p0" / c.name, harvest / "best.pth")
                json.dump({"peak": best, "source": c.name, "t": time.time()},
                          open(best_meta, "w"))
                if best >= args.target:
                    print(f"[skörd] MÅL {args.target} NÅTT: {best:.1f} — kandidaten "
                          f"säkrad i {harvest}/best.pth. Kör serverprotokollet.")
                    return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
