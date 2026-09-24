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

from sentinel_diff.ingest import (
    apply_boa_offset,
    boa_offset_for_item,
    load_multispectral_cube,
    parse_processing_baseline,
    read_windowed_band,
)
from tests.conftest import bbox_wgs84_from_geotiff, make_scl_4x4, write_test_geotiff

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


# ── BOA offset harmonisation ─────────────────────────────────────────────


def _item(baseline):
    from types import SimpleNamespace

    props = {} if baseline is None else {"s2:processing_baseline": baseline}
    return SimpleNamespace(id="stub", assets={}, properties=props)


class TestBoaOffset:
    """Processing baseline >= 04.00 products carry a +1000 DN offset."""

    def test_parse_processing_baseline(self):
        assert parse_processing_baseline(_item("05.10")) == 5.10
        assert parse_processing_baseline(_item("03.00")) == 3.0
        assert parse_processing_baseline(_item(None)) is None
        assert parse_processing_baseline(_item("n/a")) is None

    def test_offset_by_baseline(self):
        assert boa_offset_for_item(_item("03.01")) == 0
        assert boa_offset_for_item(_item("04.00")) == 1000
        assert boa_offset_for_item(_item("05.10")) == 1000
        assert boa_offset_for_item(_item(None)) == 0

    def test_earthsearch_boa_offset_applied_flag_disables_offset(self):
        """Earth Search removes the +1000 DN offset at ingestion and flags it;
        the flag must win over a >= 04.00 processing baseline."""
        from types import SimpleNamespace

        applied = SimpleNamespace(
            id="S2B_35TPF_20230802_0_L2A", assets={},
            properties={"s2:processing_baseline": "05.10",
                        "earthsearch:boa_offset_applied": True},
        )
        assert boa_offset_for_item(applied) == 0

        not_applied = SimpleNamespace(
            id="S2B_35TPF_20230802_0_L2A", assets={},
            properties={"s2:processing_baseline": "05.10",
                        "earthsearch:boa_offset_applied": False},
        )
        assert boa_offset_for_item(not_applied) == 1000

    def test_apply_offset_clamps_and_does_not_wrap(self):
        band = np.array([[1500, 800, 0]], dtype=np.uint16)
        out = apply_boa_offset(band, 1000)
        assert out.dtype == np.int32
        assert out.tolist() == [[500, 0, 0]]

    def test_cube_subtracts_offset_from_reflectance_but_not_scl(self, tmp_path: Path):
        """A baseline-05.10 item must yield B03 = DN - 1000 while SCL is untouched."""
        from types import SimpleNamespace

        b03 = np.full((4, 4), 1500, dtype=np.uint16)
        b11 = np.full((4, 4), 1200, dtype=np.uint16)
        write_test_geotiff(tmp_path / "B03.tif", b03, pixel_size=10.0)
        write_test_geotiff(tmp_path / "B11.tif", b11, pixel_size=10.0)
        write_test_geotiff(tmp_path / "SCL.tif", make_scl_4x4(), pixel_size=10.0)
        item = SimpleNamespace(
            id="S2B_stub",
            properties={"s2:processing_baseline": "05.10"},
            assets={
                "B03": SimpleNamespace(href=str(tmp_path / "B03.tif")),
                "B11": SimpleNamespace(href=str(tmp_path / "B11.tif")),
                "SCL": SimpleNamespace(href=str(tmp_path / "SCL.tif")),
            },
        )
        bbox = bbox_wgs84_from_geotiff(tmp_path / "B03.tif")

        cube = load_multispectral_cube(item, bbox, bands=("B03", "B11", "SCL"))

        assert cube["boa_offset"] == 1000
        assert int(cube["B03"].max()) == 500 and int(cube["B03"].min()) == 500
        assert int(cube["B11"].max()) == 200
        assert set(np.unique(cube["SCL"])) == {4, 9}

    def test_cube_leaves_legacy_baseline_untouched(self, tmp_path: Path):
        from types import SimpleNamespace

        b03 = np.full((4, 4), 1500, dtype=np.uint16)
        write_test_geotiff(tmp_path / "B03.tif", b03, pixel_size=10.0)
        item = SimpleNamespace(
            id="S2B_stub",
            properties={"s2:processing_baseline": "03.01"},
            assets={"B03": SimpleNamespace(href=str(tmp_path / "B03.tif"))},
        )
        bbox = bbox_wgs84_from_geotiff(tmp_path / "B03.tif")
        cube = load_multispectral_cube(item, bbox, bands=("B03",))
        assert cube["boa_offset"] == 0
        assert int(cube["B03"].max()) == 1500


# ── Provider asset maps ──────────────────────────────────────────────────


class TestAssetMap:
    def test_cube_loads_earthsearch_keys_and_exposes_canonical_keys(self, tmp_path: Path):
        """Assets keyed green/nir/swir16/scl are read via asset_map; the cube is
        keyed B03/B08/B11/SCL so the rest of the pipeline is untouched."""
        from types import SimpleNamespace

        write_test_geotiff(tmp_path / "green.tif", np.full((8, 8), 300, dtype=np.uint16), pixel_size=10.0)
        write_test_geotiff(tmp_path / "nir.tif", np.full((8, 8), 250, dtype=np.uint16), pixel_size=10.0)
        write_test_geotiff(tmp_path / "swir16.tif", np.full((4, 4), 150, dtype=np.uint16), pixel_size=20.0)
        write_test_geotiff(tmp_path / "scl.tif", make_scl_4x4(), pixel_size=20.0)
        item = SimpleNamespace(
            id="S2B_35TPF_20230802_0_L2A",
            properties={"s2:processing_baseline": "05.09",
                        "earthsearch:boa_offset_applied": True},
            assets={k: SimpleNamespace(href=str(tmp_path / f"{k}.tif"))
                    for k in ("green", "nir", "swir16", "scl")},
        )
        bbox = bbox_wgs84_from_geotiff(tmp_path / "green.tif")
        asset_map = {"B03": "green", "B08": "nir", "B11": "swir16", "SCL": "scl"}

        cube = load_multispectral_cube(item, bbox, asset_map=asset_map)

        assert {"B03", "B08", "B11", "SCL"} <= set(cube)
        assert not {"green", "nir", "swir16", "scl"} & set(cube)
        assert cube["boa_offset"] == 0
        assert int(cube["B03"].max()) == 300
        assert int(cube["B08"].max()) == 250
        assert cube["B11"].shape == cube["B03"].shape == (8, 8)
        assert int(cube["B11"].max()) == 150
        assert set(np.unique(cube["SCL"])) == {4, 9}

    def test_cube_without_asset_map_still_uses_canonical_keys(
        self, mixed_resolution_stac_item, mixed_resolution_bbox
    ):
        cube = load_multispectral_cube(mixed_resolution_stac_item, mixed_resolution_bbox, asset_map=None)
        assert {"B03", "B08", "B11", "SCL"} <= set(cube)
