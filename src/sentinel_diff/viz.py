"""
Visualization module for sentinel-diff.
Generates publication-quality matplotlib figures and a standalone single-file
HTML report with an embedded before/after swipe slider.
"""

import base64
import math
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap, to_rgb
from PIL import Image  # Pillow is a hard dependency of matplotlib (pillow>=9)

# Standard publication palette
PALETTE = {
    "persistent_water": "#1f77b4",  # Deep Blue
    "water_loss": "#d62728",        # Crimson Red (Drying / Drought)
    "water_gain": "#2ca02c",        # Vibrant Green (Refilling / Expansion)
    "background": "#f0f0f0",        # Light neutral
    "masked": "#7f7f7f",            # Slate grey
}


def plot_change_summary(
    before_index: np.ndarray,
    after_index: np.ndarray,
    diff_magnitude: np.ndarray,
    change_mask: np.ndarray,
    persistent_water_mask: np.ndarray,
    water_loss_mask: np.ndarray,
    water_gain_mask: np.ndarray,
    output_path: Path,
    title: str = "Sentinel-2 Multi-Temporal Change Analysis",
    subtitle: str = "",
) -> None:
    """
    Builds a comprehensive 4-panel diagnostic figure:
    1. Before Index (e.g. MNDWI Before)
    2. After Index (e.g. MNDWI After)
    3. Change Magnitude Heatmap with the Otsu change-mask outline
    4. Classified Transition Map built from the *same* masks used for metrics
    """
    fig, axes = plt.subplots(2, 2, figsize=(12, 10), dpi=130)
    fig.patch.set_facecolor("#fafafa")

    # 1. Before
    im0 = axes[0, 0].imshow(before_index, cmap="Blues_r", vmin=-0.5, vmax=0.8)
    axes[0, 0].set_title("Baseline (Before)", fontsize=12, fontweight="bold", pad=8)
    axes[0, 0].axis("off")
    fig.colorbar(im0, ax=axes[0, 0], fraction=0.046, pad=0.04, label="MNDWI")

    # 2. After
    im1 = axes[0, 1].imshow(after_index, cmap="Blues_r", vmin=-0.5, vmax=0.8)
    axes[0, 1].set_title("Observation (After)", fontsize=12, fontweight="bold", pad=8)
    axes[0, 1].axis("off")
    fig.colorbar(im1, ax=axes[0, 1], fraction=0.046, pad=0.04, label="MNDWI")

    # 3. Change Magnitude
    im2 = axes[1, 0].imshow(diff_magnitude, cmap="magma", vmin=0.0, vmax=0.8)
    axes[1, 0].set_title("Change Magnitude (|Δ MNDWI|)", fontsize=12, fontweight="bold", pad=8)
    axes[1, 0].axis("off")
    fig.colorbar(im2, ax=axes[1, 0], fraction=0.046, pad=0.04, label="|Δ|")
    if np.any(change_mask):
        axes[1, 0].contour(
            change_mask.astype(float), levels=[0.5], colors="#00e5ff", linewidths=0.4
        )

    # 4. Classified Transition
    # 0: Background, 1: Persistent Water, 2: Water Loss (Dry), 3: Water Gain
    transition = np.zeros(before_index.shape, dtype=int)
    transition[persistent_water_mask] = 1
    transition[water_loss_mask] = 2
    transition[water_gain_mask] = 3

    cmap_trans = ListedColormap([
        PALETTE["background"],
        PALETTE["persistent_water"],
        PALETTE["water_loss"],
        PALETTE["water_gain"]
    ])
    
    axes[1, 1].imshow(transition, cmap=cmap_trans, vmin=0, vmax=3)
    axes[1, 1].set_title("Classified Water Transition", fontsize=12, fontweight="bold", pad=8)
    axes[1, 1].axis("off")

    # Custom legend
    import matplotlib.patches as mpatches
    legend_elements = [
        mpatches.Patch(color=PALETTE["persistent_water"], label="Persistent Water"),
        mpatches.Patch(color=PALETTE["water_loss"], label="Water Loss (Shrinkage)"),
        mpatches.Patch(color=PALETTE["water_gain"], label="Water Gain (Recovery)"),
    ]
    axes[1, 1].legend(handles=legend_elements, loc="lower right", framealpha=0.9, fontsize=9)

    plt.suptitle(f"{title}\n{subtitle}", fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout()
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, bbox_inches="tight")
    plt.close()


def _stride_for(shape: tuple[int, ...], max_size: int) -> int:
    """Integer stride so that the longest side of ``shape`` is <= ``max_size``."""
    longest = max(int(shape[0]), int(shape[1]))
    if max_size <= 0 or longest <= max_size:
        return 1
    return math.ceil(longest / max_size)


def _indexed_png_bytes(indices: np.ndarray, palette_rgb: np.ndarray, transparent_index: int | None = None) -> bytes:
    """Encode a 2-D uint8 index image as an 8-bit palette PNG.

    A palette PNG stores one byte per pixel instead of four (RGBA), which keeps
    the embedded report roughly 4x smaller for the same raster.  Pillow ships
    with matplotlib, so this adds no new dependency.
    """
    img = Image.fromarray(np.ascontiguousarray(indices, dtype=np.uint8), mode="P")
    flat = np.zeros(256 * 3, dtype=np.uint8)
    flat[: palette_rgb.size] = palette_rgb.astype(np.uint8).ravel()
    img.putpalette(flat.tolist())
    buf = BytesIO()
    save_kwargs: dict[str, Any] = {"format": "png", "optimize": True}
    if transparent_index is not None:
        save_kwargs["transparency"] = transparent_index
    img.save(buf, **save_kwargs)
    return buf.getvalue()


INDEX_PNG_LEVELS = 128  # colormap quantisation levels for the embedded index rasters


def render_index_png_bytes(
    index: np.ndarray,
    cmap: str = "Blues_r",
    vmin: float = -0.5,
    vmax: float = 0.8,
    max_size: int = 900,
) -> bytes:
    """Render a 2-D float index array (NaN allowed) to PNG bytes.

    The value range ``[vmin, vmax]`` is quantised to ``INDEX_PNG_LEVELS`` steps
    of the matplotlib colormap ``cmap`` and written as an 8-bit palette PNG.
    NaN pixels are painted with the ``PALETTE["masked"]`` grey.  The array is
    downsampled by integer striding so its longest side is <= ``max_size`` px,
    which keeps the embedded report small.
    """
    arr = np.asarray(index, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"index must be 2-D, got shape {arr.shape}")
    stride = _stride_for(arr.shape, max_size)
    arr = arr[::stride, ::stride]

    nan_mask = np.isnan(arr)
    normed = (np.nan_to_num(arr, nan=vmin) - vmin) / (vmax - vmin)
    normed = np.clip(normed, 0.0, 1.0)
    levels = np.rint(normed * (INDEX_PNG_LEVELS - 1)).astype(np.uint8)
    masked_index = INDEX_PNG_LEVELS  # one extra palette slot for masked pixels
    levels[nan_mask] = masked_index

    ramp = matplotlib.colormaps[cmap](np.linspace(0.0, 1.0, INDEX_PNG_LEVELS))[:, :3]
    palette = np.rint(np.vstack([ramp, to_rgb(PALETTE["masked"])]) * 255).astype(np.uint8)
    return _indexed_png_bytes(levels, palette)


def render_transition_png_bytes(
    persistent_water_mask: np.ndarray,
    water_loss_mask: np.ndarray,
    water_gain_mask: np.ndarray,
    max_size: int = 900,
) -> bytes:
    """Render the classified transition overlay as a palette PNG with transparent background.

    Colours come from ``PALETTE``; loss and gain are painted on top of
    persistent water, mirroring the priority used in ``plot_change_summary``.
    """
    masks = [np.asarray(m, dtype=bool) for m in (persistent_water_mask, water_loss_mask, water_gain_mask)]
    shape = masks[0].shape
    if any(m.shape != shape for m in masks) or len(shape) != 2:
        raise ValueError("all masks must be 2-D and share the same shape")
    stride = _stride_for(shape, max_size)
    masks = [m[::stride, ::stride] for m in masks]

    # 0: transparent background, 1: persistent water, 2: loss, 3: gain
    classes = np.zeros(masks[0].shape, dtype=np.uint8)
    for value, mask in enumerate(masks, start=1):
        classes[mask] = value
    palette = np.rint(
        np.array([
            to_rgb(PALETTE["background"]),
            to_rgb(PALETTE["persistent_water"]),
            to_rgb(PALETTE["water_loss"]),
            to_rgb(PALETTE["water_gain"]),
        ]) * 255
    ).astype(np.uint8)
    return _indexed_png_bytes(classes, palette, transparent_index=0)


def _data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


# (metadata key, human label) pairs shown in the provenance table when present.
_PROVENANCE_ROWS: list[tuple[str, str]] = [
    ("preset", "Preset"),
    ("bbox", "Bounding box [lon_min, lat_min, lon_max, lat_max]"),
    ("stac_collection", "STAC collection"),
    ("baseline_scene_id", "Baseline scene ID"),
    ("baseline_datetime", "Baseline datetime (UTC)"),
    ("baseline_cloud_cover_pct", "Baseline cloud cover (%)"),
    ("baseline_processing_baseline", "Baseline processing baseline"),
    ("baseline_boa_offset_dn", "Baseline BOA offset (DN)"),
    ("observation_scene_id", "Observation scene ID"),
    ("observation_datetime", "Observation datetime (UTC)"),
    ("observation_cloud_cover_pct", "Observation cloud cover (%)"),
    ("observation_processing_baseline", "Observation processing baseline"),
    ("observation_boa_offset_dn", "Observation BOA offset (DN)"),
    ("max_cloud_pct", "Max cloud cover for STAC query (%)"),
    ("min_component_px", "Min connected-component size (px)"),
    ("water_threshold_mndwi", "Water threshold (MNDWI >)"),
    ("sentinel_diff_version", "sentinel-diff version"),
]


def _provenance_table_html(metadata: dict[str, Any]) -> str:
    rows = []
    for key, label in _PROVENANCE_ROWS:
        if key in metadata and metadata[key] is not None:
            rows.append(
                f"<tr><th>{escape(label)}</th><td>{escape(str(metadata[key]))}</td></tr>"
            )
    if not rows:
        return "<p class=\"muted\">No provenance metadata available.</p>"
    return "<table class=\"provenance\">" + "".join(rows) + "</table>"


def generate_interactive_slider_html(
    before_index: np.ndarray,
    after_index: np.ndarray,
    persistent_water_mask: np.ndarray,
    water_loss_mask: np.ndarray,
    water_gain_mask: np.ndarray,
    output_html_path: Path,
    title: str,
    metrics: dict[str, Any],
    before_label: str = "Baseline",
    after_label: str = "Observation",
) -> Path:
    """Write a standalone, single-file HTML report with a before/after swipe slider.

    The two index rasters and the transition overlay are embedded as base64
    PNG data URIs; the slider and overlay toggle are pure CSS + JS.  The file
    has no external scripts, fonts, images or relative links, so it can be
    opened from anywhere (including as an e-mail attachment) without the
    ``figures/`` directory next to it.
    """
    before_uri = _data_uri(render_index_png_bytes(before_index))
    after_uri = _data_uri(render_index_png_bytes(after_index))
    overlay_uri = _data_uri(
        render_transition_png_bytes(persistent_water_mask, water_loss_mask, water_gain_mask)
    )

    def fmt(key: str) -> str:
        return escape(str(metrics.get(key, "N/A")))

    net = metrics.get("net_change_hectares", 0) or 0
    net_class = "danger" if net < 0 else "success"
    metadata = metrics.get("metadata", {}) or {}
    safe_title = escape(title)
    safe_before = escape(before_label)
    safe_after = escape(after_label)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_title} - sentinel-diff</title>
  <style>
    :root {{
      --water: {PALETTE["persistent_water"]};
      --loss: {PALETTE["water_loss"]};
      --gain: {PALETTE["water_gain"]};
      --masked: {PALETTE["masked"]};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      margin: 0;
      padding: 16px;
      background: #f8fafc;
      color: #1e293b;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
      background: #ffffff;
      border-radius: 12px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
      padding: 24px;
    }}
    h1 {{ margin-top: 0; font-size: 24px; color: #0f172a; }}
    h2 {{ font-size: 17px; color: #0f172a; margin: 28px 0 12px; }}
    .subtitle {{ color: #64748b; margin-top: -6px; margin-bottom: 20px; font-size: 14px; }}
    .muted {{ color: #64748b; font-size: 13px; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin-bottom: 24px;
    }}
    .card {{ background: #f1f5f9; border-radius: 8px; padding: 14px; border-left: 4px solid #0284c7; }}
    .card.danger {{ border-left-color: var(--loss); }}
    .card.success {{ border-left-color: var(--gain); }}
    .card-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }}
    .card-value {{ font-size: 20px; font-weight: 700; margin-top: 6px; color: #0f172a; }}
    .card.danger .card-value {{ color: var(--loss); }}
    .card.success .card-value {{ color: var(--gain); }}

    .compare {{
      position: relative;
      width: 100%;
      overflow: hidden;
      border-radius: 8px;
      border: 1px solid #e2e8f0;
      background: #e2e8f0;
      user-select: none;
      -webkit-user-select: none;
      touch-action: none;
    }}
    .compare img {{ display: block; width: 100%; height: auto; image-rendering: auto; }}
    .compare .layer {{ position: absolute; inset: 0; }}
    .compare .after {{ clip-path: inset(0 0 0 50%); }}
    .compare .overlay {{ pointer-events: none; }}
    .compare .overlay.hidden {{ display: none; }}
    .divider {{
      position: absolute;
      top: 0;
      bottom: 0;
      left: 50%;
      width: 3px;
      margin-left: -1.5px;
      background: #ffffff;
      box-shadow: 0 0 6px rgba(0, 0, 0, 0.6);
      pointer-events: none;
    }}
    .divider::after {{
      content: "\\2194";
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: 36px;
      height: 36px;
      line-height: 36px;
      border-radius: 50%;
      background: #ffffff;
      color: #0f172a;
      font-size: 18px;
      text-align: center;
      box-shadow: 0 1px 6px rgba(0, 0, 0, 0.4);
    }}
    .compare input[type="range"] {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      margin: 0;
      opacity: 0;
      cursor: ew-resize;
      -webkit-appearance: none;
      appearance: none;
      background: transparent;
    }}
    .date-label {{
      position: absolute;
      top: 10px;
      padding: 4px 10px;
      border-radius: 6px;
      background: rgba(15, 23, 42, 0.75);
      color: #ffffff;
      font-size: 13px;
      font-weight: 600;
      pointer-events: none;
    }}
    .date-label.left {{ left: 10px; }}
    .date-label.right {{ right: 10px; }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      align-items: center;
      margin: 12px 0 4px;
      font-size: 14px;
    }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px; margin-top: 8px; }}
    .legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
    .swatch {{ width: 14px; height: 14px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.15); display: inline-block; }}
    table.provenance {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    table.provenance th, table.provenance td {{
      text-align: left;
      padding: 6px 8px;
      border-bottom: 1px solid #e2e8f0;
      vertical-align: top;
      word-break: break-all;
    }}
    table.provenance th {{ width: 40%; color: #475569; font-weight: 600; }}
    footer {{ margin-top: 28px; text-align: center; font-size: 12px; color: #94a3b8; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>{safe_title}</h1>
    <div class="subtitle">Reproducible multi-temporal Sentinel-2 surface-water change detection</div>

    <div class="grid">
      <div class="card">
        <div class="card-label">Baseline Water Area</div>
        <div class="card-value">{fmt("baseline_water_hectares")} ha</div>
      </div>
      <div class="card">
        <div class="card-label">Observation Water Area</div>
        <div class="card-value">{fmt("subsequent_water_hectares")} ha</div>
      </div>
      <div class="card danger">
        <div class="card-label">Water Loss (Shrinkage)</div>
        <div class="card-value">{fmt("water_loss_hectares")} ha</div>
      </div>
      <div class="card success">
        <div class="card-label">Water Gain (Expansion)</div>
        <div class="card-value">{fmt("water_gain_hectares")} ha</div>
      </div>
      <div class="card {net_class}">
        <div class="card-label">Net Surface Change</div>
        <div class="card-value">{fmt("net_change_hectares")} ha ({fmt("percentage_change")}%)</div>
      </div>
    </div>

    <h2>Before / after swipe comparison (MNDWI)</h2>
    <p class="muted">Drag the handle to compare. Left of the divider: {safe_before}. Right: {safe_after}.
      Bright = water (high MNDWI), dark blue = dry land, grey = masked (cloud, shadow, no data).</p>
    <div class="compare" id="compare">
      <img class="before" src="{before_uri}" alt="{safe_before} MNDWI">
      <img class="layer after" id="after" src="{after_uri}" alt="{safe_after} MNDWI">
      <img class="layer overlay" id="overlay" src="{overlay_uri}" alt="Classified water transition overlay">
      <div class="divider" id="divider"></div>
      <div class="date-label left">{safe_before}</div>
      <div class="date-label right">{safe_after}</div>
      <input type="range" id="swipe" min="0" max="100" value="50" step="0.1"
             aria-label="Swipe between {safe_before} and {safe_after}">
    </div>
    <div class="controls">
      <label><input type="checkbox" id="toggle-overlay" checked> Show water transition overlay</label>
    </div>
    <div class="legend">
      <span><i class="swatch" style="background: var(--water)"></i> Persistent water</span>
      <span><i class="swatch" style="background: var(--loss)"></i> Water loss (shrinkage)</span>
      <span><i class="swatch" style="background: var(--gain)"></i> Water gain (expansion)</span>
      <span><i class="swatch" style="background: var(--masked)"></i> Masked / no data</span>
    </div>

    <h2>Provenance</h2>
    {_provenance_table_html(metadata)}

    <footer>
      Generated with <strong>sentinel-diff</strong> &middot; Copernicus Sentinel-2 L2A open data (ESA).
      Single-file report: all imagery is embedded, no network access required.
    </footer>
  </div>
  <script>
    (function () {{
      var slider = document.getElementById("swipe");
      var after = document.getElementById("after");
      var divider = document.getElementById("divider");
      var overlay = document.getElementById("overlay");
      var toggle = document.getElementById("toggle-overlay");
      function update() {{
        var pct = parseFloat(slider.value);
        after.style.clipPath = "inset(0 0 0 " + pct + "%)";
        divider.style.left = pct + "%";
      }}
      slider.addEventListener("input", update);
      toggle.addEventListener("change", function () {{
        overlay.classList.toggle("hidden", !toggle.checked);
      }});
      update();
    }})();
  </script>
</body>
</html>
"""
    output_html_path.parent.mkdir(parents=True, exist_ok=True)
    output_html_path.write_text(html_content, encoding="utf-8")
    return output_html_path
