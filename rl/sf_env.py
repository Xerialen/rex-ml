"""Sample Factory-adapter: gymnasium.Env ovanpå QWEnvCore.

Körs i sim/.venv-sf (gymnasium 0.29.1, sample-factory 2.1.1). Kärnan (rl/env.py)
är gym-fri; det här skalet gör bara spaces + API-formen SF kräver:
konstruktor (full_env_name, cfg, render_mode) + register_env-fabrik.

Handlingsrum (STACK.md-skissen, nativt stöd via TupleActionDistribution):
    Tuple(Box(2) platt 1-D, Discrete(2) fwd, Discrete(3) side, Discrete(2) jump)
"""
from __future__ import annotations

import gymnasium as gym
import numpy as np

from rl import spec as S
from rl.env import EpisodeConfig, QWEnvCore, StubBackend
from rl.rewards_gate1 import Curriculum


def _make_backend(cfg, map_name: str):
    """qwsim (riktig fysik) som default; stub endast för smoke/tester."""
    backend_name = getattr(cfg, "qw_backend", "qwsim") if cfg is not None else "qwsim"
    if backend_name == "stub":
        return StubBackend()
    from rl.qwsim_backend import QwsimBackend
    return QwsimBackend(cfg, map_name=map_name)


def _make_curriculum(cfg, env_config):
    """Globalt fildrivet curriculum under SF-träning (cfg har train_dir);
    lokal Curriculum annars (tester/smoke). Se rl/curriculum_io.py för varför:
    per-env-instanser i spawnade workers hade växlat steg osynkroniserat."""
    train_dir = getattr(cfg, "train_dir", None) if cfg is not None else None
    if train_dir:
        import os
        from pathlib import Path
        from rl.curriculum_io import FileCurriculumClient
        exp_dir = Path(train_dir) / getattr(cfg, "experiment", "default")
        if env_config is not None and "worker_index" in env_config:
            env_id = f"w{env_config['worker_index']}v{env_config.get('vector_index', 0)}"
        else:
            env_id = f"pid{os.getpid()}"
        return FileCurriculumClient(exp_dir, env_id)
    return Curriculum()


class QWGate1Env(gym.Env):
    def __init__(self, full_env_name: str, cfg=None, env_config=None, render_mode=None):
        self.name = full_env_name
        self.render_mode = render_mode
        self.core = QWEnvCore(_make_backend(cfg, "100m"), _make_curriculum(cfg, env_config),
                              cfg=EpisodeConfig())
        n_obs = self.core.obs_spec.n_obs
        self.observation_space = gym.spaces.Box(-4.0, 4.0, shape=(n_obs,), dtype=np.float32)
        self.action_space = gym.spaces.Tuple((
            gym.spaces.Box(-1.0, 1.0, shape=(2,), dtype=np.float32),
            gym.spaces.Discrete(2),   # framåt
            gym.spaces.Discrete(3),   # sidled: ingen/vänster/höger
            gym.spaces.Discrete(2),   # hopp
        ))

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        return self.core.reset().astype(np.float32), {}

    def step(self, action):
        # SF levererar Tuple-actions som PLATT array [box0,box1,fwd,side,jump]
        # (STACK.md rad 62); gymnasium-sampling ger en äkta 4-tuple. Stöd båda.
        if isinstance(action, (tuple, list)) and len(action) == 4:
            box, fwd, side, jump = action
        else:
            a = np.asarray(action).ravel()
            box, fwd, side, jump = a[0:2], a[2], a[3], a[4]
        obs, r, done, info = self.core.step(np.asarray(box, dtype=np.float32),
                                            int(fwd), int(side), int(jump))
        # SF/gymnasium: terminated (mål/krash) vs truncated (tidsgräns)
        truncated = done and self.core.tick >= self.core.cfg.max_ticks
        terminated = done and not truncated
        return obs.astype(np.float32), r, terminated, truncated, info

    def render(self):
        return None


class QWGate2Env(gym.Env):
    """Fritt strövande dm3 (Gate 2). Samma obs/action-rum som Gate 1;
    zonrastret används för fastnad-undantag (vatten/hiss/tele)."""

    def __init__(self, full_env_name: str, cfg=None, env_config=None, render_mode=None,
                 spawn_region=None, spawn_centers=None, spawn_takeoff_states=None,
                 max_ticks=None):
        from rl.env_gate2 import Gate2Config, QWGate2Core
        from rl.zones import RASTER, ZoneRaster
        self.name = full_env_name
        self.render_mode = render_mode
        is_excluded = ZoneRaster().is_excluded if RASTER.exists() else None
        g2cfg = Gate2Config(
            spawn_region=spawn_region,
            spawn_centers=spawn_centers,
            spawn_takeoff_states=spawn_takeoff_states,
            takeoff_speed_range=(float(getattr(cfg, "qw_takeoff_speed_lo", 350.0)),
                                 float(getattr(cfg, "qw_takeoff_speed_hi", 450.0))),
            takeoff_air_frac=float(getattr(cfg, "qw_takeoff_air_frac", 0.0)),
            takeoff_multihop=bool(getattr(cfg, "qw_takeoff_multihop", False)),
            completion_bonus=float(getattr(cfg, "qw_completion_bonus", 12.0)),
            route_states=_route_states()
                if float(getattr(cfg, "qw_takeoff_air_frac", 0.0)) > 0.0 else None,
            prog_shaping=float(getattr(cfg, "qw_prog_shaping", 0.0)),
            vertical_rewards=bool(getattr(cfg, "qw_vertical_rewards", False)),
            cell_rarity=bool(getattr(cfg, "qw_cell_rarity", False)),
            novelty_bonus=float(getattr(cfg, "qw_novelty_bonus", 1.5)),
            rarity_lo=float(getattr(cfg, "qw_rarity_lo", 0.5)),
            rarity_hi=float(getattr(cfg, "qw_rarity_hi", 4.0)),
            climb_coef=float(getattr(cfg, "qw_climb_coef", 0.08)),
            gap_base=float(getattr(cfg, "qw_gap_base", 3.0)),
            height_coef=float(getattr(cfg, "qw_height_coef", 0.0)),
            gap_anneal=bool(getattr(cfg, "qw_gap_anneal", False)),
            gap_anneal_ref=float(getattr(cfg, "qw_gap_anneal_ref", 1.0)))
        if max_ticks is not None:
            g2cfg.max_ticks = int(max_ticks)
        self.core = QWGate2Core(_make_backend(cfg, "dm3"), cfg=g2cfg,
                                is_excluded=is_excluded)
        n_obs = self.core.obs_spec.n_obs
        self.observation_space = gym.spaces.Box(-4.0, 4.0, shape=(n_obs,), dtype=np.float32)
        self.action_space = gym.spaces.Tuple((
            gym.spaces.Box(-1.0, 1.0, shape=(2,), dtype=np.float32),
            gym.spaces.Discrete(2), gym.spaces.Discrete(3), gym.spaces.Discrete(2),
        ))

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self.core.rng = np.random.default_rng(seed)
        return self.core.reset().astype(np.float32), {}

    def step(self, action):
        if isinstance(action, (tuple, list)) and len(action) == 4:
            box, fwd, side, jump = action
        else:
            a = np.asarray(action).ravel()
            box, fwd, side, jump = a[0:2], a[2], a[3], a[4]
        obs, r, done, info = self.core.step(np.asarray(box, dtype=np.float32),
                                            int(fwd), int(side), int(jump))
        # Skeptikerfynd 4 (2026-08-03): FIX C-/grop-/fullbordans-/camp-slut är
        # ÄKTA terminaler — som truncated hade de värde-bootstrappats med
        # γ·V(slutobs) och dränkt completionkontrasten (takeoff-envs har
        # 15-70× fler sådana slut per frame än strövepisoder).
        terminal = info.get("terminal", info["stuck"])
        truncated = done and not terminal
        return obs.astype(np.float32), r, done and terminal, truncated, info

    def render(self):
        return None


def register(name: str = "qw_gate1"):
    from sample_factory.envs.env_utils import register_env
    register_env(name, make_env)


def make_env(full_env_name, cfg=None, env_config=None, render_mode=None):
    # modulnivå — SF picklar fabriken till spawnade worker-processer
    return QWGate1Env(full_env_name, cfg, env_config, render_mode)


def make_env_gate2(full_env_name, cfg=None, env_config=None, render_mode=None):
    # INTERLEAVED 100m-REPETITION (2026-07-31 09:50, mätgrundat): gate2-policyn
    # fastnade i enhetlig kryssvana ~410 (fördelningsdiagnos: p99 431, >500 bara
    # 0,1 % — teknikregistret från gate1 [984 bevisat] TAPPAT under navigations-
    # inlärningen). En delmängd workers kör 100m-korridoren med steg 4-belöningen
    # så extremfarten förblir i policyns register; resten tränar dm3-navigation.
    # En karta per process ⇒ split per WORKER (rummen är identiska).
    mix = getattr(cfg, "qw_gate1_mix_workers", 6) if cfg is not None else 0
    widx = env_config.get("worker_index", 99) if env_config is not None else 99
    if widx < mix:
        env = QWGate1Env(full_env_name, cfg, env_config, render_mode)
        cur = Curriculum()              # lokal (fildrivna klientens stage är read-only)
        cur.stage = 3                   # steg 4: exp-fart + väggstraff (repetition)
        env.core.cur = cur
        return env
    # HEXAGON-CURRICULUM (ägaren 2026-08-01 ~22:15: "de ska börja göra hoppen
    # från och till ring/quad"): workers [mix, mix+N) spawnar på hexagonens
    # PLATÅNIVÅ (box kring ring/quad-plattformarna + sidoledgerna, z 20-220 —
    # utesluter gropen -192 och gårgolven -264). Ratificerat curriculum-verktyg;
    # policyns input är oförändrad.
    hexn = getattr(cfg, "qw_hex_spawn_workers", 0) if cfg is not None else 0
    if widx < mix + hexn:
        # 2026-08-02 13:15 (närhetsmätning @5.3G, jump_proximity): plattformstid
        # 3.8→1.4 %, bästa annalkande 389 mot kravet <350 — boxen snävad från
        # platån (z 20-220) till PLATTFORMSBANDET z 40-130 (2513 OPEN-centers)
        # så episoderna börjar på ring/quad-nivån där gropkorsningen presenteras.
        return QWGate2Env(full_env_name, cfg, env_config, render_mode,
                          spawn_region=((0.0, -350.0, 40.0), (1200.0, 600.0, 130.0)))
    # RA-CURRICULUM (samma mätning): 55 låga besök men z-vinst max 51.7 av
    # kravets +80 — trappklättringen påbörjas men fullföljs inte. Spawns i
    # RA-gården+trappan (1184 OPEN-centers, z -48..240) multiplicerar
    # klättertillfällena; klätterbonus 0.5 + höjdtermen betalar varje steg.
    ran = getattr(cfg, "qw_ra_spawn_workers", 0) if cfg is not None else 0
    if widx < mix + hexn + ran:
        return QWGate2Env(full_env_name, cfg, env_config, render_mode,
                          spawn_region=((0.0, -1000.0, -60.0), (520.0, -460.0, 240.0)))
    # RISKREGIMEN (ägaren 2026-08-02 ~15:00: sista H100-natten, "beredd att ta
    # risker"): reverse curriculum — starta MITT I gate-uppgifterna.
    # LEDGE-workers: exakta OPEN-voxelcentrum ute på hexagonens sidoledger
    # (|perp|>100 från ring→quad-axeln, -20<z<130, d2(grop)<800) — boxar är
    # för grova för smala ledger. Första lyckade gropkorsningen ligger då
    # ~200 u bort och V2-djupbonusen (x2 vid djup>141) förstärker den direkt.
    ledn = getattr(cfg, "qw_ledge_spawn_workers", 0) if cfg is not None else 0
    if widx < mix + hexn + ran + ledn:
        return QWGate2Env(full_env_name, cfg, env_config, render_mode,
                          spawn_centers=_ledge_centers())
    # KANTAVSTAMPS-workers (reverse curriculum steg 0, 2026-08-03): riktade
    # takeoff-states på hexagonens sidoledger — grundad kantstart, yaw mot
    # målplattformens landningscentroid, initialfart 350-450 u/s (kanoniskt
    # human-lyckat p50 372.8/p90 418.6/max 451.4, analyst_fas1_validation.md
    # — FIX D 2026-08-03). Episodtak ~12 s (graft ur förslag 4: varje takeoff-
    # episod avgörs inom ~2-3 s; resten är post-försöks-strövande som redan
    # täcks av hex/ra/mix ⇒ ~5x fler kantförsök per frame ur samma workers).
    tofn = getattr(cfg, "qw_takeoff_spawn_workers", 0) if cfg is not None else 0
    if widx < mix + hexn + ran + ledn + tofn:
        return QWGate2Env(full_env_name, cfg, env_config, render_mode,
                          spawn_takeoff_states=_takeoff_states(),
                          max_ticks=getattr(cfg, "qw_takeoff_max_ticks", 77 * 12))
    # MEGA-workers: SNG-rummets ansats mot megahyllan (-720,80,160).
    megn = getattr(cfg, "qw_mega_spawn_workers", 0) if cfg is not None else 0
    if widx < mix + hexn + ran + ledn + tofn + megn:
        return QWGate2Env(full_env_name, cfg, env_config, render_mode,
                          spawn_region=((-1000.0, -150.0, -40.0), (-450.0, 350.0, 140.0)))
    return QWGate2Env(full_env_name, cfg, env_config, render_mode)


_LEDGE_CACHE = None
_TAKEOFF_CACHE = None


def _takeoff_states():
    """Kantavstamps-states (rl/data/gate_takeoff_states.json, genererad ur
    ledge_centers()-masken + Fas 1-ankarna). Modul-cachad json-laddning —
    samma mönster som _LEDGE_CACHE; fabriken körs i workerprocessen."""
    global _TAKEOFF_CACHE
    if _TAKEOFF_CACHE is None:
        import json
        from pathlib import Path
        p = Path(__file__).parent / "data" / "gate_takeoff_states.json"
        _TAKEOFF_CACHE = json.load(open(p))["states"]
    return _TAKEOFF_CACHE


_ROUTE_CACHE = None


def _route_states():
    """Rutt-states (steg -1): verkliga (pos, vel, yaw)-tillstånd samplade ur
    bottens verifierade lyckade rq-SO-bana (rl/data/route_states_rq_so.json,
    genererad ur traj_63G ep1-klippet). Modul-cachad som _TAKEOFF_CACHE."""
    global _ROUTE_CACHE
    if _ROUTE_CACHE is None:
        import json
        from pathlib import Path
        p = Path(__file__).parent / "data" / "route_states_rq_so.json"
        _ROUTE_CACHE = json.load(open(p))["states"]
    return _ROUTE_CACHE


def _ledge_centers():
    """OPEN-voxelcentrum på hexagonens sidoledger — kanonisk källa är
    rl.jump_gates.ledge_centers() (v6 delar mask mellan spawn-curriculum och
    detektor; beräknas en gång per workerprocess, fabriken körs i workern)."""
    global _LEDGE_CACHE
    if _LEDGE_CACHE is None:
        from rl.jump_gates import ledge_centers
        _LEDGE_CACHE = ledge_centers()
    return _LEDGE_CACHE
