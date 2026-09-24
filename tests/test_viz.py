"""Tests for the standalone HTML slider report and its PNG renderers in ``sentinel_diff.viz``."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from sentinel_diff.viz import (
    PALETTE,
    generate_interactive_slider_html,
    render_index_png_bytes,
    render_transition_png_bytes,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_dimensions(png: bytes) -> tuple[int, int]:
    """Decode (width, height) from the IHDR chunk (bytes 16-24) without PIL."""
    assert png[:8] == PNG_SIGNATURE
    assert png[12:16] == b"IHDR"
    width, height = struct.unpack(">II", png[16:24])
    return width, height


def _synthetic_pair(shape: tuple[int, int] = (40, 30)):
    rng = np.random.default_rng(0)
    before = rng.uniform(-0.5, 0.8, size=shape)
    after = before - 0.3
    before[0, 0] = np.nan  # masked pixel must not break rendering
    after[0, 0] = np.nan
    water_before = before > 0.0
    water_after = after > 0.0
    persistent = water_before & water_after
    loss = water_before & ~water_after
    gain = ~water_before & water_after
    return before, after, persistent, loss, gain


def test_render_index_png_bytes_is_png_with_nan():
    before, *_ = _synthetic_pair()
    png = render_index_png_bytes(before)
    assert png[:4] == b"\x89PNG"
    assert _png_dimensions(png) == (30, 40)  # (width, height) of a 40 x 30 array


def test_render_index_png_bytes_downsamples_large_input():
    big = np.zeros((2000, 2000), dtype=np.float32)
    png = render_index_png_bytes(big, max_size=900)
    width, height = _png_dimensions(png)
    assert width <= 900 and height <= 900
    assert width == height == 667  # stride 3 -> ceil(2000 / 3)


def test_render_transition_png_bytes_transparent_background_and_palette():
    _, _, persistent, loss, gain = _synthetic_pair()
    png = render_transition_png_bytes(persistent, loss, gain)
    assert png[:4] == b"\x89PNG"
    assert _png_dimensions(png) == (30, 40)
    # IHDR colour type 3 = indexed; a tRNS chunk makes the background transparent
    assert png[25] == 3
    assert b"tRNS" in png
    assert PALETTE["water_loss"].startswith("#")


def test_generate_interactive_slider_html_is_single_file(tmp_path: Path):
    before, after, persistent, loss, gain = _synthetic_pair()
    metrics = {
        "baseline_water_hectares": 12.34,
        "subsequent_water_hectares": 9.87,
        "water_loss_hectares": 3.21,
        "water_gain_hectares": 0.74,
        "net_change_hectares": -2.47,
        "percentage_change": -20.02,
        "metadata": {
            "baseline_scene_id": "S2A_MSIL2A_20210801T000000_R000_T00XXX_20210801T000000",
            "observation_scene_id": "S2B_MSIL2A_20230801T000000_R000_T00XXX_20230801T000000",
            "baseline_datetime": "2021-08-01T08:45:59Z",
            "observation_cloud_cover_pct": 1.5,
            "min_component_px": 6,
            "max_cloud_pct": 10.0,
        },
    }
    out = tmp_path / "nested" / "report.html"
    returned = generate_interactive_slider_html(
        before, after, persistent, loss, gain, out, "Synthetic Test", metrics,
        before_label="2021-08-01", after_label="2023-08-01",
    )
    assert returned == out
    html = out.read_text(encoding="utf-8")

    assert html.count("data:image/png;base64,") >= 3
    assert 'src="../' not in html
    assert "<script src=" not in html and "<link " not in html
    assert '<input type="range"' in html
    assert "clip-path" in html
    for value in ("12.34", "9.87", "3.21", "0.74", "-2.47", "-20.02"):
        assert value in html
    assert metrics["metadata"]["baseline_scene_id"] in html
    assert metrics["metadata"]["observation_scene_id"] in html
    assert "2021-08-01" in html and "2023-08-01" in html
    assert PALETTE["water_loss"] in html and PALETTE["water_gain"] in html
    assert out.stat().st_size < 2 * 1024 * 1024
