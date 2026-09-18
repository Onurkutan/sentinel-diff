import numpy as np

from sentinel_diff.indices import (
    compute_mndwi,
    compute_ndvi,
    safe_normalized_difference,
)


def test_safe_normalized_difference_basic():
    a = np.array([[10.0, 20.0], [0.0, 5.0]])
    b = np.array([[5.0, 20.0], [0.0, 15.0]])
    res = safe_normalized_difference(a, b)
    
    # (10-5)/(10+5) = 5/15 = 1/3
    assert np.isclose(res[0, 0], 1.0 / 3.0)
    # (20-20)/(40) = 0.0
    assert np.isclose(res[0, 1], 0.0)
    # 0/0 should be NaN
    assert np.isnan(res[1, 0])
    # (5-15)/(20) = -0.5
    assert np.isclose(res[1, 1], -0.5)


def test_indices_clipping():
    a = np.array([[1000.0, -100.0]])
    b = np.array([[1.0, 200.0]])
    res = safe_normalized_difference(a, b)
    assert np.all(res[np.isfinite(res)] <= 1.0)
    assert np.all(res[np.isfinite(res)] >= -1.0)


def test_mndwi_and_ndvi():
    green = np.array([[0.2, 0.1]])
    swir = np.array([[0.05, 0.4]])
    nir = np.array([[0.5, 0.05]])
    red = np.array([[0.1, 0.3]])

    mndwi = compute_mndwi(green, swir)
    ndvi = compute_ndvi(nir, red)

    # High green, low swir -> water -> positive MNDWI
    assert mndwi[0, 0] > 0
    # Low green, high swir -> dry land -> negative MNDWI
    assert mndwi[0, 1] < 0

    # High NIR, low red -> healthy canopy -> positive NDVI
    assert ndvi[0, 0] > 0
    # Low NIR, high red -> non-vegetated -> negative NDVI
    assert ndvi[0, 1] < 0
