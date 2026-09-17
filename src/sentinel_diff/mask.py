"""
Scene Classification Layer (SCL) interpretation and cloud masking for Sentinel-2.
"""

from typing import Set
import numpy as np

# Standard Sentinel-2 SCL class definitions
SCL_NO_DATA = 0
SCL_SATURATED_OR_DEFECTIVE = 1
SCL_DARK_AREA_PIXELS = 2
SCL_CLOUD_SHADOWS = 3
SCL_VEGETATION = 4
SCL_NOT_VEGETATED = 5
SCL_WATER = 6
SCL_UNCLASSIFIED = 7
SCL_CLOUD_MEDIUM_PROBABILITY = 8
SCL_CLOUD_HIGH_PROBABILITY = 9
SCL_THIN_CIRRUS = 10
SCL_SNOW = 11

DEFAULT_INVALID_CLASSES: Set[int] = {
    SCL_NO_DATA,
    SCL_SATURATED_OR_DEFECTIVE,
    SCL_CLOUD_SHADOWS,
    SCL_CLOUD_MEDIUM_PROBABILITY,
    SCL_CLOUD_HIGH_PROBABILITY,
    SCL_THIN_CIRRUS,
}


def build_valid_mask(
    scl_band: np.ndarray,
    invalid_classes: Set[int] = DEFAULT_INVALID_CLASSES,
) -> np.ndarray:
    """
    Constructs a boolean mask where True indicates clean, usable surface pixels
    (free from clouds, cloud shadows, and missing data).
    """
    mask = np.ones(scl_band.shape, dtype=bool)
    for invalid_val in invalid_classes:
        mask &= (scl_band != invalid_val)
    return mask


def isolate_water_scl(scl_band: np.ndarray) -> np.ndarray:
    """
    Returns True for pixels categorized as Water by SCL.
    Useful for cross-checking against MNDWI/NDWI.
    """
    return scl_band == SCL_WATER
