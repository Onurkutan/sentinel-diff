"""Shared test fixtures and helpers for sentinel-diff test suite.

Provides reusable GeoTIFF writer, bbox extractor, and SCL data factories
so that tests can exercise the real I/O and resampling paths without
duplication.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

# ── constants ────────────────────────────────────────────────────────────

EPSG_32635 = CRS.from_epsg(32635)
ORIGIN_X = 666_600.0  # easting  (UTM zone 35N)
ORIGIN_Y = 4_561_200.0  # northing (top-left, north-up)


# ── helpers ──────────────────────────────────────────────────────────────


def write_test_geotiff(
    path: Path,
    data: np.ndarray,
    crs: CRS = EPSG_32635,
    pixel_size: float = 20.0,
    origin: tuple[float, float] = (ORIGIN_X, ORIGIN_Y),
) -> Path:
    """Write a single-band GeoTIFF with the given *data* array."""
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


def bbox_wgs84_from_geotiff(path: Path) -> list[float]:
    """Return [west, south, east, north] in EPSG:4326 for the raster at *path*."""
    with rasterio.open(path) as src:
        bounds = src.bounds
        west, south, east, north = transform_bounds(
            src.crs, "EPSG:4326", bounds.left, bounds.bottom, bounds.right, bounds.top
        )
    return [west, south, east, north]


def make_scl_4x4() -> np.ndarray:
    """4×4 uint8 grid: top-left 2×2 = 9 (cloud high prob), rest = 4 (vegetation)."""
    data = np.full((4, 4), 4, dtype=np.uint8)
    data[:2, :2] = 9
    return data


# ── fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def scl_geotiff_20m(tmp_path: Path) -> Path:
    """Write a 4×4 SCL GeoTIFF at 20 m resolution and return its path."""
    return write_test_geotiff(
        tmp_path / "SCL.tif", make_scl_4x4(), pixel_size=20.0
    )


@pytest.fixture
def scl_bbox_wgs84(scl_geotiff_20m: Path) -> list[float]:
    """WGS-84 bounding box for the SCL test raster."""
    return bbox_wgs84_from_geotiff(scl_geotiff_20m)


@pytest.fixture
def mixed_resolution_stac_item(tmp_path: Path):
    """Create GeoTIFFs at mixed resolutions and return a stub STAC item.

    B03 and B08 are 10 m → 8×8 pixels.
    B11 and SCL are 20 m → 4×4 pixels, same ground extent (80 m × 80 m).
    """
    from types import SimpleNamespace

    b03_data = np.full((8, 8), 200, dtype=np.uint8)
    b08_data = np.full((8, 8), 180, dtype=np.uint8)
    b11_data = np.full((4, 4), 150, dtype=np.uint8)
    scl_data = make_scl_4x4()

    b03_path = write_test_geotiff(tmp_path / "B03.tif", b03_data, pixel_size=10.0)
    b08_path = write_test_geotiff(tmp_path / "B08.tif", b08_data, pixel_size=10.0)
    b11_path = write_test_geotiff(tmp_path / "B11.tif", b11_data, pixel_size=20.0)
    scl_path = write_test_geotiff(tmp_path / "SCL.tif", scl_data, pixel_size=20.0)

    return SimpleNamespace(
        assets={
            "B03": SimpleNamespace(href=str(b03_path)),
            "B08": SimpleNamespace(href=str(b08_path)),
            "B11": SimpleNamespace(href=str(b11_path)),
            "SCL": SimpleNamespace(href=str(scl_path)),
        }
    )


@pytest.fixture
def mixed_resolution_bbox(tmp_path: Path, mixed_resolution_stac_item) -> list[float]:
    """WGS-84 bounding box from the B03 raster in the mixed-resolution set."""
    return bbox_wgs84_from_geotiff(tmp_path / "B03.tif")
