"""Tests for sentinel_diff.ingest – resampling behaviour on real GeoTIFF rasters.

Every test creates a tiny on-disk GeoTIFF via rasterio so that the code
under test (read_windowed_band, load_multispectral_cube) is exercised with
the same I/O and resampling paths used in production.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

from sentinel_diff.ingest import load_multispectral_cube, read_windowed_band

# ── helpers ──────────────────────────────────────────────────────────────

EPSG_32635 = CRS.from_epsg(32635)
ORIGIN_X = 666_600.0  # easting
ORIGIN_Y = 4_561_200.0  # northing (top-left, north-up)


def _write_test_geotiff(
    path: Path,
    data: np.ndarray,
    crs: CRS = EPSG_32635,
    pixel_size: float = 20.0,
    origin: tuple[float, float] = (ORIGIN_X, ORIGIN_Y),
) -> Path:
    """Write a single-band uint8 GeoTIFF with the given *data*."""
    transform = from_origin(origin[0], origin[1], pixel_size, pixel_size)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype=data.dtype,
        crs=crs,
        transform=transform,
    ) as dst:
        dst.write(data, 1)
    return path


def _bbox_wgs84_from_geotiff(path: Path) -> list[float]:
    """Return [west, south, east, north] in EPSG:4326 for the raster at *path*."""
    with rasterio.open(path) as src:
        bounds = src.bounds  # left, bottom, right, top in native CRS
        west, south, east, north = transform_bounds(
            src.crs, "EPSG:4326", bounds.left, bounds.bottom, bounds.right, bounds.top
        )
    return [west, south, east, north]


def _make_scl_4x4() -> np.ndarray:
    """4×4 uint8 grid: top-left 2×2 = 9 (cloud), remainder = 4 (vegetation)."""
    data = np.full((4, 4), 4, dtype=np.uint8)
    data[:2, :2] = 9
    return data


# ── read_windowed_band ───────────────────────────────────────────────────


class TestReadWindowedBand:
    """Exercise read_windowed_band against on-disk GeoTIFFs."""

    def test_nearest_preserves_classes(self, tmp_path: Path):
        """Nearest-neighbour upsampling must keep only original class values."""
        tif = _write_test_geotiff(
            tmp_path / "scl.tif", _make_scl_4x4(), pixel_size=20.0
        )
        bbox = _bbox_wgs84_from_geotiff(tif)

        result, _transform, _crs = read_windowed_band(
            str(tif), bbox, target_shape=(8, 8), resampling=Resampling.nearest
        )

        assert result.shape == (8, 8)
        assert set(np.unique(result)) <= {4, 9}, (
            f"Nearest resampling introduced unexpected classes: "
            f"{set(np.unique(result))}"
        )

    def test_bilinear_creates_interpolated_classes(self, tmp_path: Path):
        """Bilinear upsampling on a categorical raster must introduce
        at least one value outside {4, 9}, proving why nearest is required
        for classification layers."""
        tif = _write_test_geotiff(
            tmp_path / "scl.tif", _make_scl_4x4(), pixel_size=20.0
        )
        bbox = _bbox_wgs84_from_geotiff(tif)

        result, _transform, _crs = read_windowed_band(
            str(tif), bbox, target_shape=(8, 8), resampling=Resampling.bilinear
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
    """

    @staticmethod
    def _make_stub_item(tmp_path: Path) -> SimpleNamespace:
        """Create GeoTIFFs at mixed resolutions and a stub STAC item.

        B03 and B08 are 10 m → 8×8 pixels.
        B11 and SCL are 20 m → 4×4 pixels, same ground extent.
        """
        # Same ground extent: 80 m × 80 m
        b03_data = np.full((8, 8), 200, dtype=np.uint8)
        b08_data = np.full((8, 8), 180, dtype=np.uint8)
        b11_data = np.full((4, 4), 150, dtype=np.uint8)
        scl_data = _make_scl_4x4()

        b03_path = _write_test_geotiff(
            tmp_path / "B03.tif", b03_data, pixel_size=10.0
        )
        b08_path = _write_test_geotiff(
            tmp_path / "B08.tif", b08_data, pixel_size=10.0
        )
        b11_path = _write_test_geotiff(
            tmp_path / "B11.tif", b11_data, pixel_size=20.0
        )
        scl_path = _write_test_geotiff(
            tmp_path / "SCL.tif", scl_data, pixel_size=20.0
        )

        item = SimpleNamespace(
            assets={
                "B03": SimpleNamespace(href=str(b03_path)),
                "B08": SimpleNamespace(href=str(b08_path)),
                "B11": SimpleNamespace(href=str(b11_path)),
                "SCL": SimpleNamespace(href=str(scl_path)),
            }
        )
        return item

    def test_scl_preserves_classes(self, tmp_path: Path):
        """SCL band upsampled from 20 m → 10 m must contain only the
        original discrete class values {4, 9}."""
        item = self._make_stub_item(tmp_path)
        bbox = _bbox_wgs84_from_geotiff(tmp_path / "B03.tif")

        cube = load_multispectral_cube(item, bbox)

        assert "SCL" in cube
        scl_classes = set(np.unique(cube["SCL"]))
        assert scl_classes <= {4, 9}, (
            f"SCL band contains interpolated classes after upsampling: "
            f"{scl_classes}"
        )

    def test_band_shapes_match(self, tmp_path: Path):
        """All bands in the cube must be aligned to the B03 reference grid."""
        item = self._make_stub_item(tmp_path)
        bbox = _bbox_wgs84_from_geotiff(tmp_path / "B03.tif")

        cube = load_multispectral_cube(item, bbox)

        ref_shape = cube["B03"].shape
        assert cube["B11"].shape == ref_shape, (
            f"B11 shape {cube['B11'].shape} != B03 shape {ref_shape}"
        )
        assert cube["SCL"].shape == ref_shape, (
            f"SCL shape {cube['SCL'].shape} != B03 shape {ref_shape}"
        )
