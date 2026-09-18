import numpy as np

from sentinel_diff.metrics import (
    pixel_count_to_hectares,
    pixel_count_to_sq_km,
    summarize_water_change,
)


def test_pixel_to_area():
    # 100 pixels of 10m x 10m = 10,000 m² = 1.0 ha
    assert pixel_count_to_hectares(100, 10.0) == 1.0
    # 10,000 pixels of 10m x 10m = 1,000,000 m² = 1.0 km²
    assert pixel_count_to_sq_km(10_000, 10.0) == 1.0


def test_summarize_water_change():
    # 4 pixels:
    # (0, 0): persistent water (1 -> 1)
    # (0, 1): water loss (1 -> 0)
    # (1, 0): water gain (0 -> 1)
    # (1, 1): persistent land (0 -> 0)
    before = np.array([[True, True], [False, False]])
    after = np.array([[True, False], [True, False]])

    summary = summarize_water_change(before, after, pixel_res_m=10.0)

    # Each pixel = 0.01 ha
    assert summary["baseline_water_hectares"] == 0.02
    assert summary["subsequent_water_hectares"] == 0.02
    assert summary["persistent_water_hectares"] == 0.01
    assert summary["water_loss_hectares"] == 0.01
    assert summary["water_gain_hectares"] == 0.01
    assert summary["net_change_hectares"] == 0.0
    assert summary["percentage_change"] == 0.0
