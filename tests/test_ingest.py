"""Tests for sentinel_diff.ingest – resampling behaviour on real GeoTIFF rasters.

Every test creates a tiny on-disk GeoTIFF via rasterio so that the code
under test (read_windowed_band, load_multispectral_cube) is exercised with
the same I/O and resampling paths used in production.

Shared GeoTIFF helpers and fixtures are defined in tests/conftest.py.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from rasterio.enums import Resampling

from sentinel_diff.ingest import load_multispectral_cube, read_windowed_band

# ── read_windowed_band ───────────────────────────────────────────────────


class TestReadWindowedBand:
    """Exercise read_windowed_band against on-disk GeoTIFFs.

    Uses ``scl_geotiff_20m`` and ``scl_bbox_wgs84`` fixtures from conftest.
    """

    def test_nearest_preserves_classes(self, scl_geotiff_20m: Path, scl_bbox_wgs84):
        """Nearest-neighbour upsampling must keep only original class values."""
        result, _transform, _crs = read_windowed_band(
            str(scl_geotiff_20m), scl_bbox_wgs84,
            target_shape=(8, 8), resampling=Resampling.nearest,
        )

        assert result.shape == (8, 8)
        assert set(np.unique(result)) <= {4, 9}, (
            f"Nearest resampling introduced unexpected classes: "
            f"{set(np.unique(result))}"
        )

    def test_bilinear_creates_interpolated_classes(
        self, scl_geotiff_20m: Path, scl_bbox_wgs84
    ):
        """Bilinear upsampling on a categorical raster must introduce
        at least one value outside {4, 9}, proving why nearest is required
        for classification layers."""
        result, _transform, _crs = read_windowed_band(
            str(scl_geotiff_20m), scl_bbox_wgs84,
            target_shape=(8, 8), resampling=Resampling.bilinear,
        )

        unique_vals = set(np.unique(result))
        extra = unique_vals - {4, 9}
        assert len(extra) > 0, (
            "Bilinear resampling did not introduce any interpolated values; "
            "the test cannot demonstrate the difference from nearest."
        )


# ── load_multispectral_cube ──────────────────────────────────────────────


class TestLoadMultispectralCube:
    """Exercise load_multispectral_cube with stub STAC items backed by
    real GeoTIFFs.

    Simulates Sentinel-2 resolution: B03/B08 at 10 m (8×8 grid), B11/SCL
    at 20 m (4×4 grid) covering the same ground footprint.  The function
    under test should upsample B11 and SCL to the B03 reference grid.

    Uses ``mixed_resolution_stac_item`` and ``mixed_resolution_bbox``
    fixtures from conftest.
    """

    def test_scl_preserves_classes(
        self, mixed_resolution_stac_item, mixed_resolution_bbox
    ):
        """SCL band upsampled from 20 m → 10 m must contain only the
        original discrete class values {4, 9}."""
        cube = load_multispectral_cube(mixed_resolution_stac_item, mixed_resolution_bbox)

        assert "SCL" in cube
        scl_classes = set(np.unique(cube["SCL"]))
        assert scl_classes <= {4, 9}, (
            f"SCL band contains interpolated classes after upsampling: "
            f"{scl_classes}"
        )

    def test_band_shapes_match(
        self, mixed_resolution_stac_item, mixed_resolution_bbox
    ):
        """All bands in the cube must be aligned to the B03 reference grid."""
        cube = load_multispectral_cube(mixed_resolution_stac_item, mixed_resolution_bbox)

        ref_shape = cube["B03"].shape
        assert cube["B11"].shape == ref_shape, (
            f"B11 shape {cube['B11'].shape} != B03 shape {ref_shape}"
        )
        assert cube["SCL"].shape == ref_shape, (
            f"SCL shape {cube['SCL'].shape} != B03 shape {ref_shape}"
        )
