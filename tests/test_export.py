"""Tests for the GeoTIFF / GeoJSON export of the water-transition map.

A 6 x 6 transition raster at 10 m (0.01 ha per pixel) in EPSG:32635 is
written with the real ``sentinel_diff.export`` functions and read back with
rasterio / json.  Layout (rows x cols):

* rows 0-1, cols 0-5 : persistent_water (12 px)         -> 1 polygon, 0.12 ha
* rows 2-3, cols 0-2 : water_loss (6 px)                -> 1 polygon, 0.06 ha
* row  5,   col  0   : water_loss (1 px, disconnected)  -> 1 polygon, 0.01 ha
* rows 4-5, cols 4-5 : water_gain (4 px)                -> 1 polygon, 0.04 ha
* row  0,   col  0   : invalid (overrides persistent)   -> nodata 255
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from sentinel_diff.export import (
    TRANSITION_CODES,
    TRANSITION_NODATA,
    build_transition_raster,
    write_transition_geojson,
    write_transition_geotiff,
)
from tests.conftest import EPSG_32635, ORIGIN_X, ORIGIN_Y

PIXEL_SIZE = 10.0
TRANSFORM = from_origin(ORIGIN_X, ORIGIN_Y, PIXEL_SIZE, PIXEL_SIZE)


def _masks():
    persistent = np.zeros((6, 6), dtype=bool)
    loss = np.zeros((6, 6), dtype=bool)
    gain = np.zeros((6, 6), dtype=bool)
    valid = np.ones((6, 6), dtype=bool)
    persistent[0:2, :] = True
    loss[2:4, 0:3] = True
    loss[5, 0] = True
    gain[4:6, 4:6] = True
    valid[0, 0] = False
    return persistent, loss, gain, valid


def _expected_transition() -> np.ndarray:
    exp = np.zeros((6, 6), dtype=np.uint8)
    exp[0:2, :] = TRANSITION_CODES["persistent_water"]
    exp[2:4, 0:3] = TRANSITION_CODES["water_loss"]
    exp[5, 0] = TRANSITION_CODES["water_loss"]
    exp[4:6, 4:6] = TRANSITION_CODES["water_gain"]
    exp[0, 0] = TRANSITION_NODATA
    return exp


def test_build_transition_raster_codes_and_nodata():
    transition = build_transition_raster(*_masks())
    assert transition.dtype == np.uint8
    np.testing.assert_array_equal(transition, _expected_transition())
    # Without a valid mask nothing is nodata
    persistent, loss, gain, _ = _masks()
    assert not (build_transition_raster(persistent, loss, gain) == TRANSITION_NODATA).any()


def test_write_transition_geotiff_roundtrip(tmp_path: Path):
    transition = build_transition_raster(*_masks())
    out = write_transition_geotiff(transition, TRANSFORM, EPSG_32635, tmp_path / "rasters" / "t.tif")
    assert out.is_file()
    with rasterio.open(out) as src:
        assert src.count == 1
        assert src.dtypes[0] == "uint8"
        assert src.nodata == TRANSITION_NODATA
        assert src.crs == EPSG_32635
        assert src.transform == TRANSFORM
        assert src.profile["compress"] == "deflate"
        np.testing.assert_array_equal(src.read(1), _expected_transition())


def test_write_transition_geojson_features_areas_and_wgs84(tmp_path: Path):
    transition = build_transition_raster(*_masks())
    out = tmp_path / "vectors" / "t.geojson"
    summary = write_transition_geojson(transition, TRANSFORM, EPSG_32635, out)

    fc = json.loads(out.read_text(encoding="utf-8"))
    assert fc["type"] == "FeatureCollection"
    features = fc["features"]

    # One polygon per connected component: 1 persistent, 2 loss, 1 gain
    by_class: dict[str, list[dict]] = defaultdict(list)
    for feat in features:
        by_class[feat["properties"]["class_name"]].append(feat)
    assert {k: len(v) for k, v in by_class.items()} == {
        "persistent_water": 1, "water_loss": 2, "water_gain": 1,
    }
    assert summary["feature_count"] == 4
    assert summary["area_ha_by_class"] == {
        "persistent_water": 0.11, "water_loss": 0.07, "water_gain": 0.04,
    }

    # area_ha per class equals pixel count x 0.01 ha (nodata pixel excluded)
    px_area_ha = PIXEL_SIZE * PIXEL_SIZE / 10_000.0
    for name, feats in by_class.items():
        n_px = int(np.count_nonzero(transition == TRANSITION_CODES[name]))
        assert round(sum(f["properties"]["area_ha"] for f in feats), 4) == round(n_px * px_area_ha, 4)
        assert all(f["properties"]["class_code"] == TRANSITION_CODES[name] for f in feats)
    assert sorted(f["properties"]["area_ha"] for f in by_class["water_loss"]) == [0.01, 0.06]

    # Reprojected to WGS-84: all coordinates fall in the Istanbul UTM-35N area
    def _coords(obj):
        if isinstance(obj[0], (int, float)):
            yield obj
        else:
            for sub in obj:
                yield from _coords(sub)

    for feat in features:
        assert feat["geometry"]["type"] in ("Polygon", "MultiPolygon")
        for lon, lat in _coords(feat["geometry"]["coordinates"]):
            assert 25.0 <= lon <= 32.0, lon
            assert 40.0 <= lat <= 42.0, lat


def test_write_transition_geojson_empty_classes(tmp_path: Path):
    """No water at all -> valid empty FeatureCollection and zeroed summary."""
    zeros = np.zeros((4, 4), dtype=bool)
    transition = build_transition_raster(zeros, zeros, zeros)
    out = tmp_path / "empty.geojson"
    summary = write_transition_geojson(transition, TRANSFORM, EPSG_32635, out)
    assert json.loads(out.read_text())["features"] == []
    assert summary == {
        "feature_count": 0,
        "area_ha_by_class": {"persistent_water": 0.0, "water_loss": 0.0, "water_gain": 0.0},
    }
