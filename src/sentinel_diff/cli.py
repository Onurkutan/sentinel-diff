"""
Full Command-Line Interface for sentinel-diff.
Provides search, analysis, presets, and diagnostic commands.
"""

from pathlib import Path
import json
import click
import numpy as np

from sentinel_diff import __version__
from sentinel_diff.catalog import RESERVOIR_PRESETS, get_preset_bbox, search_sentinel_scenes
from sentinel_diff.indices import compute_mndwi, compute_ndvi
from sentinel_diff.mask import build_valid_mask
from sentinel_diff.cva import compute_difference, compute_cva_magnitude, otsu_threshold, filter_noise_morphology
from sentinel_diff.metrics import summarize_water_change
from sentinel_diff.ingest import load_multispectral_cube
from sentinel_diff.viz import plot_change_summary, generate_interactive_slider_html


@click.group()
@click.version_option(version=__version__)
def main():
    """sentinel-diff: Multi-temporal satellite change detection from open Sentinel-2 data."""
    pass


@main.command()
def status():
    """Show pipeline status and environment configuration."""
    click.echo(f"sentinel-diff v{__version__} - Environment and modules ready.")


@main.command()
def presets():
    """List available geographical preset areas (e.g. Istanbul water reservoirs)."""
    click.echo("Available Presets:")
    for name, bbox in RESERVOIR_PRESETS.items():
        click.echo(f"  - {name:<16} BBox [lon_min, lat_min, lon_max, lat_max]: {bbox}")


@main.command()
@click.option("--preset", default="alibeykoy", help="Preset name (e.g. alibeykoy, terkos, omerli).")
@click.option("--date-range", required=True, help="ISO-8601 date range (e.g. 2023-07-01/2023-09-30).")
@click.option("--max-cloud", default=10.0, help="Maximum cloud cover percentage (default: 10.0).")
@click.option("--limit", default=5, help="Max scenes to list.")
def search(preset: str, date_range: str, max_cloud: float, limit: int):
    """Search for available cloudless Sentinel-2 scenes in STAC."""
    try:
        bbox = get_preset_bbox(preset)
    except ValueError as e:
        raise click.ClickException(str(e))

    click.echo(f"Searching STAC for preset '{preset}' (BBox: {bbox}) between {date_range}...")
    scenes = search_sentinel_scenes(bbox, date_range, max_cloud_cover=max_cloud, max_items=limit)
    
    if not scenes:
        click.echo("No scenes found matching criteria.")
        return

    click.echo(f"\nFound {len(scenes)} cloudless scenes:")
    click.echo(f"{'Scene ID':<45} {'Date (UTC)':<22} {'Cloud %':<8}")
    click.echo("-" * 78)
    for s in scenes:
        dt_str = s['datetime'][:19] if s['datetime'] else 'Unknown'
        cloud = f"{s['cloud_cover']:.2f}%" if s['cloud_cover'] is not None else 'N/A'
        click.echo(f"{s['id']:<45} {dt_str:<22} {cloud:<8}")


@main.command()
@click.option("--preset", default="alibeykoy", help="Preset area name.")
@click.option("--before-date", required=True, help="Baseline date range (e.g. 2021-08-01/2021-08-31).")
@click.option("--after-date", required=True, help="Observation date range (e.g. 2023-08-01/2023-08-31).")
@click.option("--out-dir", default="reports", help="Output directory for reports and figures.")
def analyze(preset: str, before_date: str, after_date: str, out_dir: str):
    """Run full change detection pipeline between two temporal observations."""
    bbox = get_preset_bbox(preset)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    click.echo(f"=== sentinel-diff Analysis: {preset.upper()} ===")
    click.echo(f"1. Searching baseline scene ({before_date}, selecting least cloudy)...")
    before_scenes = search_sentinel_scenes(
        bbox, before_date, max_cloud_cover=15.0, max_items=20, sort_by_cloud=True
    )
    if not before_scenes:
        raise click.ClickException(f"No clear baseline scene found in range {before_date}")
    item_before = before_scenes[0]["item_obj"]
    cloud_b = f"{before_scenes[0]['cloud_cover']:.2f}%" if before_scenes[0]['cloud_cover'] is not None else "N/A"
    click.echo(f"   Using: {item_before.id} ({before_scenes[0]['datetime'][:10]}, cloud: {cloud_b})")

    click.echo(f"2. Searching observation scene ({after_date}, selecting least cloudy)...")
    after_scenes = search_sentinel_scenes(
        bbox, after_date, max_cloud_cover=15.0, max_items=20, sort_by_cloud=True
    )
    if not after_scenes:
        raise click.ClickException(f"No clear observation scene found in range {after_date}")
    item_after = after_scenes[0]["item_obj"]
    cloud_a = f"{after_scenes[0]['cloud_cover']:.2f}%" if after_scenes[0]['cloud_cover'] is not None else "N/A"
    click.echo(f"   Using: {item_after.id} ({after_scenes[0]['datetime'][:10]}, cloud: {cloud_a})")

    click.echo("3. Streaming windowed multispectral bands (B03, B08, B11, SCL)...")
    cube_before = load_multispectral_cube(item_before, bbox)
    cube_after = load_multispectral_cube(item_after, bbox)

    click.echo("4. Calculating Scene Classification Masks and MNDWI...")
    mask_before = build_valid_mask(cube_before["SCL"]) if "SCL" in cube_before else None
    mask_after = build_valid_mask(cube_after["SCL"]) if "SCL" in cube_after else None
    valid_joint = (mask_before & mask_after) if (mask_before is not None and mask_after is not None) else None

    mndwi_before = compute_mndwi(cube_before["B03"], cube_before["B11"], valid_mask=valid_joint)
    mndwi_after = compute_mndwi(cube_after["B03"], cube_after["B11"], valid_mask=valid_joint)

    # Water classification (MNDWI > 0.0 indicates surface water body)
    water_before = (mndwi_before > 0.0)
    water_after = (mndwi_after > 0.0)

    click.echo("5. Performing Change Vector Analysis (CVA) & Otsu Thresholding...")
    diff_mndwi = compute_difference(mndwi_before, mndwi_after, valid_mask=valid_joint)
    cva_mag = compute_cva_magnitude(diff_mndwi, valid_mask=valid_joint)
    
    # Statistical change threshold
    otsu_th = otsu_threshold(cva_mag)
    click.echo(f"   Otsu Threshold on |Delta MNDWI|: {otsu_th:.3f}")

    # Isolate water transitions
    water_loss = water_before & ~water_after
    water_gain = ~water_before & water_after

    # Morphological noise cleanup
    water_loss_clean = filter_noise_morphology(water_loss, min_pixel_size=6)
    water_gain_clean = filter_noise_morphology(water_gain, min_pixel_size=6)

    click.echo("6. Computing quantitative surface area metrics...")
    metrics = summarize_water_change(
        water_before, water_after, valid_mask=valid_joint, pixel_res_m=10.0
    )

    # Attach complete provenance metadata for standalone reproducibility
    metrics["metadata"] = {
        "preset": preset,
        "bbox": bbox,
        "baseline_scene_id": item_before.id,
        "baseline_datetime": before_scenes[0]["datetime"],
        "baseline_cloud_cover_pct": before_scenes[0]["cloud_cover"],
        "observation_scene_id": item_after.id,
        "observation_datetime": after_scenes[0]["datetime"],
        "observation_cloud_cover_pct": after_scenes[0]["cloud_cover"],
        "stac_collection": "sentinel-2-l2a",
    }

    click.echo("\n" + "=" * 45)
    click.echo(f"  SURFACE WATER CHANGE SUMMARY: {preset.upper()}")
    click.echo("=" * 45)
    click.echo(f"Baseline Scene       : {item_before.id}")
    click.echo(f"Baseline Date        : {before_scenes[0]['datetime'][:10]} (cloud: {cloud_b})")
    click.echo(f"Observation Scene    : {item_after.id}")
    click.echo(f"Observation Date     : {after_scenes[0]['datetime'][:10]} (cloud: {cloud_a})")
    click.echo(f"Baseline Water Area  : {metrics['baseline_water_hectares']} ha")
    click.echo(f"Subsequent Water Area: {metrics['subsequent_water_hectares']} ha")
    click.echo(f"Persistent Water     : {metrics['persistent_water_hectares']} ha")
    click.echo(f"Water Loss (Drying)  : {metrics['water_loss_hectares']} ha")
    click.echo(f"Water Gain (Inflow)  : {metrics['water_gain_hectares']} ha")
    click.echo(f"Net Change           : {metrics['net_change_hectares']} ha ({metrics['percentage_change']}%)")
    click.echo("=" * 45 + "\n")

    # Save metrics JSON
    metrics_file = out_path / f"{preset}_metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    click.echo(f"Saved metrics to: {metrics_file}")

    # Build and save figure
    fig_file = out_path / "figures" / f"{preset}_change_analysis.png"
    subtitle = (
        f"{before_scenes[0]['datetime'][:10]} vs {after_scenes[0]['datetime'][:10]} | "
        f"Net Change: {metrics['net_change_hectares']} ha ({metrics['percentage_change']}%)"
    )
    plot_change_summary(
        before_index=mndwi_before,
        after_index=mndwi_after,
        diff_magnitude=cva_mag,
        change_mask=(cva_mag > otsu_th),
        water_loss_mask=water_loss_clean,
        water_gain_mask=water_gain_clean,
        output_path=fig_file,
        title=f"Istanbul {preset.upper()} Reservoir - Multi-Temporal Water Surface Change",
        subtitle=subtitle,
    )
    click.echo(f"Saved diagnostic figure to: {fig_file}")

    # Generate interactive HTML dashboard report
    html_file = out_path / "interactive" / f"{preset}_report.html"
    generate_interactive_slider_html(
        figure_rel_path=f"../figures/{preset}_change_analysis.png",
        output_html_path=html_file,
        title=f"Istanbul {preset.upper()} Reservoir Water Change Analysis",
        metrics=metrics,
    )
    click.echo(f"Saved interactive report to: {html_file}")


if __name__ == "__main__":
    main()
