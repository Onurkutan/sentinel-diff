"""
Vectorized spectral index calculations from Sentinel-2 bands.
All calculations use NumPy arrays and handle zero-division and invalid domain values gracefully.
"""

from typing import Optional
import numpy as np


def safe_normalized_difference(
    band_a: np.ndarray,
    band_b: np.ndarray,
    valid_mask: Optional[np.ndarray] = None,
    eps: float = 1e-7,
) -> np.ndarray:
    """
    Computes (band_a - band_b) / (band_a + band_b).
    Values outside [-1.0, 1.0] or where denominator is near zero are masked/clipped.
    """
    a = band_a.astype(np.float32)
    b = band_b.astype(np.float32)
    
    denominator = a + b
    # Avoid zero division
    with np.errstate(divide="ignore", invalid="ignore"):
        diff = (a - b) / np.where(np.abs(denominator) < eps, np.nan, denominator)
    
    # Clip to theoretical bounds
    diff = np.clip(diff, -1.0, 1.0)
    
    if valid_mask is not None:
        diff = np.where(valid_mask, diff, np.nan)
        
    return diff


def compute_mndwi(
    green: np.ndarray,
    swir: np.ndarray,
    valid_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Modified Normalized Difference Water Index (Xu, 2006).
    MNDWI = (Green - SWIR) / (Green + SWIR)
    Superior to NDWI for separating open water from urban noise and built-up land.
    Positive values (> 0.0) typically represent open water bodies.
    """
    return safe_normalized_difference(green, swir, valid_mask=valid_mask)


def compute_ndwi(
    green: np.ndarray,
    nir: np.ndarray,
    valid_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Normalized Difference Water Index (McFeeters, 1996).
    NDWI = (Green - NIR) / (Green + NIR)
    """
    return safe_normalized_difference(green, nir, valid_mask=valid_mask)


def compute_ndvi(
    nir: np.ndarray,
    red: np.ndarray,
    valid_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Normalized Difference Vegetation Index (Rouse et al., 1974).
    NDVI = (NIR - Red) / (NIR + Red)
    Values > 0.3 typically represent healthy green vegetation canopy.
    """
    return safe_normalized_difference(nir, red, valid_mask=valid_mask)


def compute_ndbi(
    swir: np.ndarray,
    nir: np.ndarray,
    valid_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Normalized Difference Built-up Index (Zha et al., 2003).
    NDBI = (SWIR - NIR) / (SWIR + NIR)
    Positive values indicate built-up impervious surfaces and bare soil.
    """
    return safe_normalized_difference(swir, nir, valid_mask=valid_mask)
