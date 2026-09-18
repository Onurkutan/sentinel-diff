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
    assert mask[0, 0] is np.True_ or mask[0, 0] == True
    assert mask[0, 1] is np.True_ or mask[0, 1] == True
    assert mask[1, 0] is np.False_ or mask[1, 0] == False
    assert mask[1, 1] is np.False_ or mask[1, 1] == False


def test_isolate_water_scl():
    scl = np.array([
        [SCL_WATER, SCL_VEGETATION],
        [SCL_WATER, SCL_CLOUD_HIGH_PROBABILITY],
    ])
    water = isolate_water_scl(scl)
    assert water[0, 0] == True
    assert water[0, 1] == False
    assert water[1, 0] == True
    assert water[1, 1] == False
