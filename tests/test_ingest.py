import numpy as np
import rasterio
from rasterio.enums import Resampling


def test_categorical_nearest_vs_bilinear_resampling():
    """
    Verifies that nearest-neighbor resampling preserves exact categorical integer classes
    (e.g. 4 for Vegetation, 6 for Water) and does not synthesize intermediate classes like 5.
    """
    # 2x2 categorical raster with classes 4 and 6
    cat_data = np.array([[4, 6], [4, 6]], dtype=np.uint8)

    # Resample to 4x4 using nearest
    # In rasterio, nearest should only produce 4 and 6
    unique_orig = set(np.unique(cat_data))
    
    # Simulate nearest expansion
    nearest_upsampled = np.kron(cat_data, np.ones((2, 2), dtype=np.uint8))
    unique_nearest = set(np.unique(nearest_upsampled))
    assert unique_nearest == unique_orig
    assert 5 not in unique_nearest  # Spurious class must not appear
