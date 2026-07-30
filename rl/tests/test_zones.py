import numpy as np
import pytest

from rl.zones import (RASTER, CLS_OPEN, CLS_WATER, GateScore, OPEN_TARGET,
                      ZoneRaster)

pytestmark = pytest.mark.skipif(not RASTER.exists(), reason="rastret ej byggt")


@pytest.fixture(scope="module")
def raster():
    return ZoneRaster()


def test_raster_loads_with_expected_size(raster):
    assert len(raster._map) == 42379          # agentens rapporterade voxelantal
    assert raster.n_open == 31971


def test_lift_shaft_excluded_water_excluded(raster):
    # vattenbassängen i dm3 ligger djupt; leta upp en känd vattenvoxel ur rastret
    d = np.load(RASTER)
    wi = np.flatnonzero(d["cls"] == CLS_WATER)[0]
    pos = (d["ix"][wi] * 32.0 + 16, d["iy"][wi] * 32.0 + 16, d["iz"][wi] * 32.0 + 16)
    assert raster.is_excluded(pos)
    cls, target = raster.lookup(pos)
    assert cls == CLS_WATER and target == 0.0


def test_open_voxel_has_500_target(raster):
    d = np.load(RASTER)
    oi = np.flatnonzero(d["cls"] == CLS_OPEN)[0]
    pos = (d["ix"][oi] * 32.0 + 16, d["iy"][oi] * 32.0 + 16, d["iz"][oi] * 32.0 + 16)
    cls, target = raster.lookup(pos)
    assert cls == CLS_OPEN and target == OPEN_TARGET
    assert not raster.is_excluded(pos)


def test_unknown_voxel_not_counted(raster):
    cls, target = raster.lookup((99999.0, 99999.0, 99999.0))
    assert target == 0.0


def test_gate_score_terms(raster):
    d = np.load(RASTER)
    oi = np.flatnonzero(d["cls"] == CLS_OPEN)[:100]
    gs = GateScore(raster)
    for i in oi:
        pos = (d["ix"][i] * 32.0 + 16, d["iy"][i] * 32.0 + 16, d["iz"][i] * 32.0 + 16)
        gs.tick(pos, 600.0)
    s = gs.summary()
    assert s["score"] == pytest.approx(1.2)       # 600/500
    assert s["open_mean_speed"] == pytest.approx(600.0)
    assert 0 < s["open_coverage"] < 0.01          # 100 av 31971
    assert not gs.passed()                        # täckningskravet fäller
