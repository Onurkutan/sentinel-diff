import numpy as np

from sentinel_diff.mask import (
    SCL_CLOUD_HIGH_PROBABILITY,
    SCL_CLOUD_SHADOWS,
    SCL_VEGETATION,
    SCL_WATER,
    build_valid_mask,
    isolate_water_scl,
)


def test_build_valid_mask():
    scl = np.array([
        [SCL_WATER, SCL_VEGETATION],
        [SCL_CLOUD_HIGH_PROBABILITY, SCL_CLOUD_SHADOWS],
    ])
    mask = build_valid_mask(scl)
    assert mask.dtype == bool
    assert mask[0, 0]
    assert mask[0, 1]
    assert not mask[1, 0]
    assert not mask[1, 1]


def test_isolate_water_scl():
    scl = np.array([
        [SCL_WATER, SCL_VEGETATION],
        [SCL_WATER, SCL_CLOUD_HIGH_PROBABILITY],
    ])
    water = isolate_water_scl(scl)
    assert water[0, 0]
    assert not water[0, 1]
    assert water[1, 0]
    assert not water[1, 1]
