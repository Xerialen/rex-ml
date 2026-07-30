"""Curriculum-daemonen: äger det GLOBALA stegbeslutet under träning.

Körs bredvid träningen (samma tmux-fönster, eget kommando):
    .venv/bin/python -m rl.curriculum_daemon <train_dir> [--interval 5]

Aggregerar alla envs episod-jsonl (rl/curriculum_io.py), applicerar
StageCriteria (rewards_gate1) på det rullande fönstret ÖVER ALLA envs och
skriver stage.json. Varje växling loggas till <train_dir>/curriculum_log.jsonl
— det är de raderna PROGRESS.md-milstolparna citerar.

Avslutar sig själv när sista steget konvergerat (done=True i stage.json):
det är signalen "Gate 1-KANDIDAT — kör bevisprotokollet på riktiga servern".
"""
from __future__ import annotations

import argparse
import json
import time
from collections import deque
from pathlib import Path

from .curriculum_io import read_stage, write_stage
from .rewards_gate1 import REWARD_FNS, StageCriteria


def scan_new(files: dict, ep_dir: Path) -> list[dict]:
    out = []
    for p in sorted(ep_dir.glob("*.jsonl")):
        pos = files.get(p, 0)
        with open(p) as f:
            f.seek(pos)
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass        # halvskriven rad — tas nästa varv
            files[p] = f.tell()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("train_dir", type=Path)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--window", type=int, default=200)
    args = ap.parse_args(argv)

    crit = StageCriteria()
    st = read_stage(args.train_dir)
    stage, done = st["stage"], bool(st.get("done"))
    window: deque = deque(maxlen=args.window)
    episodes_in_stage = 0
    files: dict = {}
    ep_dir = args.train_dir / "episodes"
    log = open(args.train_dir / "curriculum_log.jsonl", "a", buffering=1)
    print(f"[daemon] startar i steg {stage + 1}, fönster {args.window}")

    while not done:
        time.sleep(args.interval)
        if not ep_dir.exists():
            continue
        fresh = [e for e in scan_new(files, ep_dir) if e.get("stage") == stage]
        for e in fresh:
            window.append((e["peak"], e["coll"]))
            episodes_in_stage += 1
        if episodes_in_stage < crit.min_episodes or len(window) < window.maxlen:
            continue
        peaks = [p for p, _ in window]
        colls = [c for _, c in window]
        mean_peak = sum(peaks) / len(peaks)
        mean_coll = sum(colls) / len(colls)
        need_speed, max_coll = crit.thresholds[stage]
        if mean_peak >= need_speed and mean_coll <= max_coll:
            entry = {"from_stage": stage + 1, "mean_peak": round(mean_peak, 1),
                     "mean_coll": round(mean_coll, 1), "episodes": episodes_in_stage,
                     "t": time.time()}
            if stage == len(REWARD_FNS) - 1:
                done = True
                entry["event"] = "GATE1_KANDIDAT"
            else:
                stage += 1
                entry["event"] = f"steg -> {stage + 1}"
                window.clear()
                episodes_in_stage = 0
            log.write(json.dumps(entry) + "\n")
            print(f"[daemon] {entry['event']}: peak {mean_peak:.0f}, koll {mean_coll:.0f}")
            write_stage(args.train_dir, stage, done,
                        {"mean_peak": round(mean_peak, 1)})
    print("[daemon] klart — Gate 1-KANDIDAT, kör bevisprotokollet på riktiga servern")


if __name__ == "__main__":
    main()
