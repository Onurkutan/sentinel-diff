"""
Visualization module for sentinel-diff.
Generates publication-quality matplotlib figures and standalone HTML slider maps.
"""

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

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


def generate_interactive_slider_html(
    figure_rel_path: str,
    output_html_path: Path,
    title: str,
    metrics: dict[str, Any],
) -> None:
    """
    Generates a lightweight, zero-dependency standalone HTML dashboard with metrics
    and full diagnostic visualization.
    """
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} - sentinel-diff</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      margin: 0;
      padding: 24px;
      background: #f8fafc;
      color: #1e293b;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
      background: #ffffff;
      border-radius: 12px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
      padding: 32px;
    }}
    h1 {{
      margin-top: 0;
      font-size: 26px;
      color: #0f172a;
    }}
    .subtitle {{
      color: #64748b;
      margin-top: -8px;
      margin-bottom: 24px;
      font-size: 15px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 32px;
    }}
    .card {{
      background: #f1f5f9;
      border-radius: 8px;
      padding: 16px;
      border-left: 4px solid #0284c7;
    }}
    .card.danger {{
      border-left-color: #ef4444;
    }}
    .card.success {{
      border-left-color: #10b981;
    }}
    .card-label {{
      font-size: 13px;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .card-value {{
      font-size: 22px;
      font-weight: 700;
      margin-top: 6px;
      color: #0f172a;
    }}
    .figure-container {{
      text-align: center;
      margin-top: 24px;
    }}
    .figure-container img {{
      max-width: 100%;
      height: auto;
      border-radius: 8px;
      border: 1px solid #e2e8f0;
      box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }}
    footer {{
      margin-top: 32px;
      text-align: center;
      font-size: 13px;
      color: #94a3b8;
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>{title}</h1>
    <div class="subtitle">Reproducible Multi-Temporal Satellite Change Detection & Environmental Monitoring</div>
    
    <div class="grid">
      <div class="card">
        <div class="card-label">Baseline Water Area</div>
        <div class="card-value">{metrics.get('baseline_water_hectares', 'N/A')} ha</div>
      </div>
      <div class="card">
        <div class="card-label">Observation Water Area</div>
        <div class="card-value">{metrics.get('subsequent_water_hectares', 'N/A')} ha</div>
      </div>
      <div class="card danger">
        <div class="card-label">Water Loss (Shrinkage)</div>
        <div class="card-value">{metrics.get('water_loss_hectares', 'N/A')} ha</div>
      </div>
      <div class="card {'danger' if metrics.get('net_change_hectares', 0) < 0 else 'success'}">
        <div class="card-label">Net Surface Change</div>
        <div class="card-value">{metrics.get('net_change_hectares', 'N/A')} ha ({metrics.get('percentage_change', 'N/A')}%)</div>
      </div>
    </div>

    <div class="figure-container">
      <img src="{figure_rel_path}" alt="{title} Change Analysis Figure">
    </div>

    <footer>
      Generated with <strong>sentinel-diff</strong> · Powered by European Space Agency Sentinel-2 L2A open data.
    </footer>
  </div>
</body>
</html>
"""
    output_html_path.parent.mkdir(parents=True, exist_ok=True)
    output_html_path.write_text(html_content, encoding="utf-8")

