"""
Spatial metrics and surface area calculations for environmental monitoring.
"""

from typing import Any

import numpy as np


def pixel_count_to_hectares(pixel_count: int, pixel_res_m: float = 10.0) -> float:
    """Converts pixel count to hectares. 1 ha = 10,000 m²."""
    area_m2 = pixel_count * (pixel_res_m ** 2)
    return float(area_m2 / 10_000.0)


def pixel_count_to_sq_km(pixel_count: int, pixel_res_m: float = 10.0) -> float:
    """Converts pixel count to square kilometers."""
    area_m2 = pixel_count * (pixel_res_m ** 2)
    return float(area_m2 / 1_000_000.0)


def summarize_water_change(
    water_before: np.ndarray,
    water_after: np.ndarray,
    valid_mask: np.ndarray = None,
    pixel_res_m: float = 10.0,
) -> dict[str, Any]:
    """
    Computes rigorous surface area transition metrics between two observations.
    
    Classes:
    - Persistent water: True in before AND after
    - Contraction / Loss (Drought/Shrinkage): True in before, False in after
    - Expansion / Gain (Recovery/Inflow): False in before, True in after
    - Persistent non-water: False in before AND after
    """
    b = water_before.astype(bool)
    a = water_after.astype(bool)
    
    if valid_mask is not None:
        valid = valid_mask.astype(bool)
        b = b & valid
        a = a & valid
    else:
        valid = np.ones(b.shape, dtype=bool)

    total_analyzed_pixels = int(np.count_nonzero(valid))
    persistent_water_px = int(np.count_nonzero(b & a))
    water_loss_px = int(np.count_nonzero(b & ~a))
    water_gain_px = int(np.count_nonzero(~b & a))
    
    before_total_px = persistent_water_px + water_loss_px
    after_total_px = persistent_water_px + water_gain_px
    net_change_px = after_total_px - before_total_px

    before_ha = pixel_count_to_hectares(before_total_px, pixel_res_m)
    after_ha = pixel_count_to_hectares(after_total_px, pixel_res_m)
    loss_ha = pixel_count_to_hectares(water_loss_px, pixel_res_m)
    gain_ha = pixel_count_to_hectares(water_gain_px, pixel_res_m)
    net_change_ha = pixel_count_to_hectares(net_change_px, pixel_res_m)

    pct_change = (net_change_ha / before_ha * 100.0) if before_ha > 0 else 0.0

    return {
        "pixel_resolution_m": pixel_res_m,
        "total_analyzed_hectares": round(pixel_count_to_hectares(total_analyzed_pixels, pixel_res_m), 2),
        "baseline_water_hectares": round(before_ha, 2),
        "subsequent_water_hectares": round(after_ha, 2),
        "persistent_water_hectares": round(pixel_count_to_hectares(persistent_water_px, pixel_res_m), 2),
        "water_loss_hectares": round(loss_ha, 2),
        "water_gain_hectares": round(gain_ha, 2),
        "net_change_hectares": round(net_change_ha, 2),
        "percentage_change": round(pct_change, 2),
    }
