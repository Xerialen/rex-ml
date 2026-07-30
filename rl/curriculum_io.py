"""Global curriculum-samordning över SF:s processer.

Problemet: SF kör envarna i spawnade worker-processer — en Curriculum-instans
per env hade växlat steg osynkroniserat (olika envs i olika steg = inkonsistent
belöningsfunktion i samma batch). Steget måste vara GLOBALT.

Lösning (fildriven, lockfri):
  * varje env appendar episodresultat till  <dir>/episodes/<env_id>.jsonl
    (append av korta rader är atomärt nog på lokal disk),
  * rl/curriculum_daemon.py aggregerar alla jsonl, äger stegbeslutet och
    skriver  <dir>/stage.json  (atomärt via rename),
  * envarna läser stage.json vid episodslut (mtime-cachead).

FileCurriculumClient och den lokala Curriculum-klassen (rewards_gate1) delar
gränssnitt: .stage, .reward_fn, .end_episode(peak, coll) — QWEnvCore ser ingen
skillnad.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .rewards_gate1 import REWARD_FNS


def read_stage(train_dir: Path) -> dict:
    p = Path(train_dir) / "stage.json"
    try:
        return json.load(open(p))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"stage": 0, "done": False}


def write_stage(train_dir: Path, stage: int, done: bool, meta: dict | None = None):
    p = Path(train_dir) / "stage.json"
    tmp = p.with_suffix(".json.tmp")
    payload = {"stage": stage, "done": done, "t": time.time()}
    if meta:
        payload.update(meta)
    json.dump(payload, open(tmp, "w"))
    os.replace(tmp, p)          # atomärt på samma filsystem


class FileCurriculumClient:
    """Env-sidan: rapportera episoder, följ daemonens globala steg."""

    STAGE_CHECK_EVERY_S = 5.0

    def __init__(self, train_dir: str | Path, env_id: str):
        self.dir = Path(train_dir)
        (self.dir / "episodes").mkdir(parents=True, exist_ok=True)
        self._f = open(self.dir / "episodes" / f"{env_id}.jsonl", "a", buffering=1)
        self._stage = read_stage(self.dir)["stage"]
        self._last_check = 0.0
        self.done = False

    @property
    def stage(self) -> int:
        return self._stage

    @property
    def reward_fn(self):
        return REWARD_FNS[self._stage]

    def end_episode(self, peak_speed: float, collision_loss_total: float) -> bool:
        self._f.write(json.dumps({"peak": round(float(peak_speed), 1),
                                  "coll": round(float(collision_loss_total), 1),
                                  "stage": self._stage, "t": time.time()}) + "\n")
        now = time.time()
        if now - self._last_check >= self.STAGE_CHECK_EVERY_S:
            self._last_check = now
            st = read_stage(self.dir)
            changed = st["stage"] != self._stage
            self._stage = st["stage"]
            self.done = bool(st.get("done"))
            return changed
        return False
