"""
Change Vector Analysis (CVA) and statistical thresholding algorithms.
Provides automated Otsu and Median Absolute Deviation (MAD) thresholding without OpenCV.
"""

import numpy as np
from scipy import ndimage


def compute_difference(
    before: np.ndarray,
    after: np.ndarray,
    valid_mask: np.ndarray | None = None,
) -> np.ndarray:
    """
    Computes simple temporal difference: after - before.
    Positive values indicate an increase in the index, negative indicate a decrease.
    """
    diff = after.astype(np.float32) - before.astype(np.float32)
    if valid_mask is not None:
        diff = np.where(valid_mask, diff, np.nan)
    return diff


def compute_cva_magnitude(
    diff_dim1: np.ndarray,
    diff_dim2: np.ndarray | None = None,
    valid_mask: np.ndarray | None = None,
) -> np.ndarray:
    """
    Computes Change Vector magnitude.
    If 1D (single index): |diff_dim1|
    If 2D (e.g. diff_NDVI and diff_NDBI): sqrt(diff1^2 + diff2^2)
    """
    if diff_dim2 is None:
        magnitude = np.abs(diff_dim1)
    else:
        magnitude = np.sqrt(np.square(diff_dim1) + np.square(diff_dim2))
        
    if valid_mask is not None:
        magnitude = np.where(valid_mask, magnitude, np.nan)
        
    return magnitude


def otsu_threshold(values: np.ndarray, n_bins: int = 256) -> float:
    """
    Vectorized Otsu thresholding from scratch using NumPy.
    Finds the threshold that maximizes between-class variance.
    Filters out NaN and infinite values automatically.
    """
    valid_vals = values[np.isfinite(values)]
    if len(valid_vals) == 0:
        return 0.0

    min_val, max_val = float(np.min(valid_vals)), float(np.max(valid_vals))
    if np.isclose(min_val, max_val):
        return min_val

    # Histogram & probabilities
    counts, bin_edges = np.histogram(valid_vals, bins=n_bins, range=(min_val, max_val))
    probabilities = counts / counts.sum()
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0

    # Cumulative sums
    weight1 = np.cumsum(probabilities)
    weight2 = 1.0 - weight1

    # Cumulative means
    mean1 = np.cumsum(probabilities * bin_centers) / np.maximum(weight1, 1e-12)
    total_mean = mean1[-1]
    mean2 = (total_mean - np.cumsum(probabilities * bin_centers)) / np.maximum(weight2, 1e-12)

    # Between-class variance: sigma_b^2 = w1 * w2 * (mu1 - mu2)^2
    variance = weight1 * weight2 * np.square(mean1 - mean2)
    variance[weight1 <= 1e-6] = 0.0
    variance[weight2 <= 1e-6] = 0.0

    # If multiple bins achieve maximum variance (a plateau), take the midpoint
    max_var = np.max(variance)
    if max_var <= 1e-12:
        return float(min_val)
        
    candidates = np.where(np.isclose(variance, max_var, rtol=1e-4))[0]
    best_idx = int(np.round(np.mean(candidates)))
    return float(bin_centers[best_idx])


def mad_threshold(values: np.ndarray, k: float = 3.0) -> float:
    """
    Robust threshold based on Median Absolute Deviation (MAD).
    Threshold = median + k * 1.4826 * MAD
    Ideal for anomaly detection and isolated change detection.
    """
    valid_vals = values[np.isfinite(values)]
    if len(valid_vals) == 0:
        return 0.0

    med = np.median(valid_vals)
    mad = np.median(np.abs(valid_vals - med))
    sigma_est = 1.4826 * mad
    return float(med + k * sigma_est)


def filter_noise_morphology(
    binary_mask: np.ndarray,
    min_pixel_size: int = 9,
) -> np.ndarray:
    """
    Removes isolated single-pixel false alarms and fills small pinhole gaps
    using binary opening and closing operations.
    """
    # 3x3 structuring element
    struct = ndimage.generate_binary_structure(2, 2)

    # scipy treats everything outside the array as background (border_value=0),
    # so a plain opening would erode a 1-pixel rim along the image edges and
    # systematically shrink any region touching the bounding box.  Replicate
    # the edge pixels outwards by one, run the operators, then crop back.
    padded = np.pad(np.asarray(binary_mask, dtype=bool), 1, mode="edge")
    # Opening removes small bright spots (noise)
    opened = ndimage.binary_opening(padded, structure=struct)
    # Closing bridges tiny gaps in contiguous areas
    closed = ndimage.binary_closing(opened, structure=struct)[1:-1, 1:-1]
    
    # Label connected components and filter by min_pixel_size
    labeled, num_features = ndimage.label(closed, structure=struct)
    if num_features == 0:
        return closed
        
    counts = np.bincount(labeled.ravel())
    large_components = counts >= min_pixel_size
    large_components[0] = False  # Background label 0 is always False
    
    return large_components[labeled]
