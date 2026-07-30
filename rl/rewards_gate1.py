"""Gate 1-belöningar och curriculum-växling (BRIEF §4, steg 1–4) för 100m.bsp.

Korridoren (uppmätt i evidence/corridor_100m.json): start (224,-1408,32),
mål (224,2900,32) — framdriftsaxeln är +Y, mittlinjen x=224.
Fysiktaket är 821.4 UPS (evidence/strafe_ceiling_100m.json); gaten är 800.

Alla vikter är startvärden — autonom justering vid stagnation är förväntad
(grundlagens operatörsisolering) och loggas i PROGRESS.md, inte här.
"""
from __future__ import annotations

import dataclasses
from collections import deque

import numpy as np

from .spec import TICK_DT

CORRIDOR_X = 224.0
CORRIDOR_START_Y = -1408.0
CORRIDOR_END_Y = 2900.0
CROSS_TRACK_MARGIN = 96.0   # fritt spelrum runt mittlinjen innan straff (steg 3+)
WALL_IMPULSE_MIN = 100.0    # u/s plötslig fartförlust som räknas som kollision


@dataclasses.dataclass
class StepState:
    """Det belöningsfunktionerna får se för ett (slot, tick)."""
    pos: np.ndarray          # (3,)
    vel: np.ndarray          # (3,)
    prev_vel: np.ndarray
    onground: bool
    prev_onground: bool
    jumped_this_tick: bool


def _speed_h(v: np.ndarray) -> float:
    return float(np.hypot(v[0], v[1]))


def _collision_loss(s: StepState) -> float:
    """Ofrivillig horisontell fartförlust (u/s) denna tick, 0 om ingen."""
    loss = _speed_h(s.prev_vel) - _speed_h(s.vel)
    # markfriktion är inte "kollision"; kollisionsstraffet i steg 4 ska träffa
    # väggträffar, dvs stora förluster även i luften eller vid landningsögonblick
    if loss < WALL_IMPULSE_MIN:
        return 0.0
    return loss


def reward_stage1(s: StepState) -> float:
    """Ren framdrift mot målet: minimera delta-avstånd. Konvergerar mot W-häng."""
    return (s.vel[1] * TICK_DT) / 100.0


def reward_stage2(s: StepState) -> float:
    """Momentumbevarande: lufttid med framåtvektor belönas, marktick straffas."""
    r = reward_stage1(s)
    if not s.onground and s.vel[1] > 0:
        r += 0.02
    if s.onground:
        r -= 0.02   # friktionen dränerar — varje marktick kostar
    return r


def reward_stage3(s: StepState) -> float:
    """Vektoracceleration: exponentiell utdelning först ÖVER motorgränsen 320."""
    sp = _speed_h(s.vel)
    r = 0.0
    if sp > 320.0:
        r += (np.expm1((sp - 320.0) / 160.0)) * 0.01   # exp-kurva, BRIEF §4
    cross = abs(s.pos[0] - CORRIDOR_X)
    if cross > CROSS_TRACK_MARGIN:
        r -= 0.002 * (cross - CROSS_TRACK_MARGIN) / 100.0
    return r + reward_stage2(s) * 0.25


def reward_stage4(s: StepState) -> float:
    """Half-beat: som steg 3 men kollisioner (väggträffar) straffas massivt."""
    r = reward_stage3(s)
    loss = _collision_loss(s)
    if loss > 0.0:
        r -= loss / 200.0
    return r


REWARD_FNS = [reward_stage1, reward_stage2, reward_stage3, reward_stage4]


@dataclasses.dataclass
class StageCriteria:
    """Automatisk fasväxling (BRIEF: 'utan att vänta på extern signal')."""
    min_episodes: int = 200
    # per steg: (rullande medel-peakfart som krävs, max kollisionsförlust/ep)
    thresholds = (
        (300.0, np.inf),   # steg 1 -> 2: springer korridoren stabilt
        (330.0, np.inf),   # steg 2 -> 3: hopprytmen slår motorgränsen ibland
        (500.0, np.inf),   # steg 3 -> 4: circle jump + accel fungerar
        # steg 4 -> KANDIDAT-PRÖVNING: träningsepisoder är SAMPLADE. 750 samplat
        # medel signalerar prövning; kandidaturen avgörs av 30-körnings GREEDY-
        # eval i qwsim med BÄSTA-KÖRNING-PEAK >= 820 (ägarens skärpta Gate 1-krav
        # 2026-07-30: "peaken ska vara 820"), och gaten bevisas därefter alltid
        # på riktiga servern. Sanna qwsim-taket ommäts (evidence/
        # strafe_ceiling_qwsim.json) — ligger det under 820 eskaleras per grundlagen.
        (750.0, 150.0),
    )


class Curriculum:
    """Spårar rullande episod-peakfarter och växlar steg automatiskt."""

    def __init__(self, criteria: StageCriteria | None = None, window: int = 200):
        self.criteria = criteria or StageCriteria()
        self.stage = 0                       # 0-indexerat internt (steg 1–4)
        self.peaks: deque = deque(maxlen=window)
        self.coll: deque = deque(maxlen=window)
        self.episodes_in_stage = 0
        self.done = False

    @property
    def reward_fn(self):
        return REWARD_FNS[self.stage]

    def end_episode(self, peak_speed: float, collision_loss_total: float) -> bool:
        """Returnerar True om steget just växlade (för loggning)."""
        self.peaks.append(peak_speed)
        self.coll.append(collision_loss_total)
        self.episodes_in_stage += 1
        if self.episodes_in_stage < self.criteria.min_episodes:
            return False
        need_speed, max_coll = self.criteria.thresholds[self.stage]
        if len(self.peaks) < self.peaks.maxlen:
            return False
        if float(np.mean(self.peaks)) >= need_speed and float(np.mean(self.coll)) <= max_coll:
            if self.stage == len(REWARD_FNS) - 1:
                self.done = True             # Gate 1-kandidat — bevisa på servern
                return True
            self.stage += 1
            self.episodes_in_stage = 0
            self.peaks.clear()
            self.coll.clear()
            return True
        return False
