"""Offline end-to-end test of ``sentinel-diff analyze``.

The STAC search is monkeypatched to return stub items whose assets point at
tiny GeoTIFFs written to ``tmp_path``.  Everything downstream (windowed COG
reading, BOA offset, SCL masking, MNDWI, morphology, metrics, figure, HTML)
runs through the real code path in ``sentinel_diff.cli.analyze``.

Synthetic scene (20 x 20 px at 10 m, 100 m2 per pixel = 0.01 ha):

* Baseline:    rows 0-9 water, rows 10-19 land.
* Observation: rows 0-5 water, rows 6-19 land, plus ONE isolated water
  pixel at (15, 10) that morphological cleaning must remove.
* SCL (20 m):  cell (0, 0) is cloud in the observation scene -> the 2 x 2
  10 m block at rows 0-1 / cols 0-1 is excluded from every metric.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from click.testing import CliRunner

import sentinel_diff.cli as cli_module
from sentinel_diff.cli import main
from tests.conftest import bbox_wgs84_from_geotiff, write_test_geotiff

WATER_GREEN, WATER_SWIR = 3000, 500
LAND_GREEN, LAND_SWIR = 500, 3000


def _write_scene(dirpath: Path, water_rows: int, speck: bool, cloud_corner: bool):
    dirpath.mkdir()
    green = np.full((20, 20), LAND_GREEN, dtype=np.uint16)
    swir = np.full((20, 20), LAND_SWIR, dtype=np.uint16)
    green[:water_rows, :] = WATER_GREEN
    swir[:water_rows, :] = WATER_SWIR
    if speck:
        green[15, 10] = WATER_GREEN
        swir[15, 10] = WATER_SWIR
    nir = np.full((20, 20), 1000, dtype=np.uint16)
    scl = np.full((10, 10), 4, dtype=np.uint8)  # vegetation everywhere
    if cloud_corner:
        scl[0, 0] = 9  # high-probability cloud
    write_test_geotiff(dirpath / "B03.tif", green, pixel_size=10.0)
    write_test_geotiff(dirpath / "B08.tif", nir, pixel_size=10.0)
    write_test_geotiff(dirpath / "B11.tif", swir, pixel_size=10.0)
    write_test_geotiff(dirpath / "SCL.tif", scl, pixel_size=20.0)
    return dirpath


def _stub_scene(item_id: str, dt: str, scene_dir: Path, baseline: str):
    item = SimpleNamespace(
        id=item_id,
        properties={"s2:processing_baseline": baseline},
        assets={b: SimpleNamespace(href=str(scene_dir / f"{b}.tif")) for b in ("B03", "B08", "B11", "SCL")},
    )
    return {"id": item_id, "datetime": dt, "cloud_cover": 1.0, "assets": list(item.assets), "item_obj": item}


def _run(tmp_path: Path, monkeypatch, extra_args: list[str]):
    before_dir = _write_scene(tmp_path / "before", water_rows=10, speck=False, cloud_corner=False)
    after_dir = _write_scene(tmp_path / "after", water_rows=6, speck=True, cloud_corner=True)
    bbox = bbox_wgs84_from_geotiff(before_dir / "B03.tif")

    before = _stub_scene("S2B_MSIL2A_20210802T084559_R107_T35TPF_20210802T203106",
                         "2021-08-02T08:45:59Z", before_dir, "03.00")
    after = _stub_scene("S2B_MSIL2A_20230802T084609_R107_T35TPF_20241025T040038",
                        "2023-08-02T08:46:09Z", after_dir, "05.10")

    def fake_search(bbox_arg, datetime_range, **kwargs):
        return [before] if datetime_range.startswith("2021") else [after]

    monkeypatch.setattr(cli_module, "search_sentinel_scenes", fake_search)
    monkeypatch.setattr(cli_module, "get_preset_bbox", lambda _name: bbox)

    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["analyze", "--preset", "synthetic", "--before-date", "2021-08-01/2021-08-31",
         "--after-date", "2023-08-01/2023-08-31", "--out-dir", str(out_dir), *extra_args],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    metrics = json.loads((out_dir / "synthetic_metrics.json").read_text())
    return result, metrics, out_dir


def test_analyze_end_to_end_default_cleaning(tmp_path: Path, monkeypatch):
    result, metrics, out_dir = _run(tmp_path, monkeypatch, [])

    # Artifacts
    assert (out_dir / "figures" / "synthetic_change_analysis.png").stat().st_size > 0
    html_file = out_dir / "interactive" / "synthetic_report.html"
    html = html_file.read_text()
    assert "Net Surface Change" in html
    # Single-file report: imagery embedded, no relative links, under the 2 MB hygiene limit
    assert "data:image/png;base64," in html
    assert 'src="../' not in html
    assert html_file.stat().st_size < 2 * 1024 * 1024

    # Water accounting on the joint-valid grid (2x2 cloud notch removed)
    assert metrics["pixel_resolution_m"] == 10.0
    assert metrics["total_analyzed_hectares"] == 3.96      # 400 - 4 px
    assert metrics["baseline_water_hectares"] == 1.96      # 200 - 4 px
    assert metrics["subsequent_water_hectares"] == 1.16    # 120 - 4 px, speck removed
    assert metrics["persistent_water_hectares"] == 1.16
    assert metrics["water_loss_hectares"] == 0.80
    assert metrics["water_gain_hectares"] == 0.0
    assert metrics["net_change_hectares"] == -0.80
    # Self-consistency: baseline = persistent + loss, subsequent = persistent + gain
    assert metrics["baseline_water_hectares"] == round(
        metrics["persistent_water_hectares"] + metrics["water_loss_hectares"], 2)
    assert metrics["subsequent_water_hectares"] == round(
        metrics["persistent_water_hectares"] + metrics["water_gain_hectares"], 2)

    # Provenance
    md = metrics["metadata"]
    assert md["baseline_boa_offset_dn"] == 0
    assert md["observation_boa_offset_dn"] == 1000
    assert md["observation_processing_baseline"] == 5.10
    assert md["min_component_px"] == 6
    assert "BOA offset: before=0 DN" in result.output


def test_analyze_without_cleaning_keeps_isolated_pixel(tmp_path: Path, monkeypatch):
    """--min-component-px 0 disables morphology: the 1-px speck counts as gain."""
    _result, metrics, _ = _run(tmp_path, monkeypatch, ["--min-component-px", "0"])
    assert metrics["subsequent_water_hectares"] == 1.17
    assert metrics["water_gain_hectares"] == 0.01
    assert metrics["metadata"]["min_component_px"] == 0
