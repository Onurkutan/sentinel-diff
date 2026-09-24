"""
Full Command-Line Interface for sentinel-diff.
Provides search, analysis, presets, and diagnostic commands.
"""

import json
from pathlib import Path

import click

from sentinel_diff import __version__
from sentinel_diff.catalog import (
    RESERVOIR_PRESETS,
    get_preset_bbox,
    search_sentinel_scenes,
    select_scene_pair,
)
from sentinel_diff.cva import (
    compute_cva_magnitude,
    compute_difference,
    filter_noise_morphology,
    otsu_threshold,
)
from sentinel_diff.indices import compute_mndwi
from sentinel_diff.ingest import load_multispectral_cube, parse_processing_baseline
from sentinel_diff.mask import build_valid_mask
from sentinel_diff.metrics import summarize_water_change
from sentinel_diff.viz import generate_interactive_slider_html, plot_change_summary


@click.group()
@click.version_option(version=__version__)
def main():
    """sentinel-diff: Multi-temporal satellite change detection from open Sentinel-2 data."""


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
        raise click.ClickException(str(e)) from e

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
@click.option("--max-cloud", type=float, default=10.0, help="Max cloud cover %% for STAC query (default: 10.0).")
@click.option(
    "--min-component-px",
    type=int,
    default=6,
    show_default=True,
    help="Minimum connected-component size (pixels) kept after morphological cleaning of the "
    "water masks. Applies to metrics AND figure. 0 disables cleaning.",
)
@click.option("--out-dir", default="reports", help="Output directory for reports and figures.")
def analyze(
    preset: str,
    before_date: str,
    after_date: str,
    max_cloud: float,
    min_component_px: int,
    out_dir: str,
):
    """Run full change detection pipeline between two temporal observations."""
    bbox = get_preset_bbox(preset)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    click.echo(f"=== sentinel-diff Analysis: {preset.upper()} ===")
    click.echo(f"    max-cloud={max_cloud}%  min-component-px={min_component_px}")
    click.echo(f"1. Searching baseline scenes ({before_date})...")
    before_scenes = search_sentinel_scenes(
        bbox, before_date, max_cloud_cover=max_cloud, max_items=20
    )
    if not before_scenes:
        raise click.ClickException(f"No clear baseline scene found in range {before_date}")
    click.echo(f"   Found {len(before_scenes)} candidate scene(s).")

    click.echo(f"2. Searching observation scenes ({after_date})...")
    after_scenes = search_sentinel_scenes(
        bbox, after_date, max_cloud_cover=max_cloud, max_items=20
    )
    if not after_scenes:
        raise click.ClickException(f"No clear observation scene found in range {after_date}")
    click.echo(f"   Found {len(after_scenes)} candidate scene(s).")

    click.echo("3. Selecting scene pair (DOY proximity + dedup + cloud tiebreaker)...")
    before_pick, after_pick = select_scene_pair(before_scenes, after_scenes)
    item_before = before_pick["item_obj"]
    item_after = after_pick["item_obj"]
    cloud_b = f"{before_pick['cloud_cover']:.2f}%" if before_pick['cloud_cover'] is not None else "N/A"
    cloud_a = f"{after_pick['cloud_cover']:.2f}%" if after_pick['cloud_cover'] is not None else "N/A"
    click.echo(f"   Before: {item_before.id} ({before_pick['datetime'][:10]}, cloud: {cloud_b})")
    click.echo(f"   After:  {item_after.id} ({after_pick['datetime'][:10]}, cloud: {cloud_a})")

    click.echo("4. Streaming windowed multispectral bands (B03, B08, B11, SCL)...")
    cube_before = load_multispectral_cube(item_before, bbox)
    cube_after = load_multispectral_cube(item_after, bbox)
    baseline_b = parse_processing_baseline(item_before)
    baseline_a = parse_processing_baseline(item_after)
    click.echo(
        f"   BOA offset: before={cube_before['boa_offset']} DN (baseline {baseline_b}), "
        f"after={cube_after['boa_offset']} DN (baseline {baseline_a})"
    )
    if cube_before["B03"].shape != cube_after["B03"].shape:
        raise click.ClickException(
            f"Scene grids differ: {cube_before['B03'].shape} vs {cube_after['B03'].shape}. "
            "The two acquisitions must share the same tile/orbit footprint."
        )
    pixel_res_m = float(abs(cube_before["transform"].a))

    click.echo("5. Calculating Scene Classification Masks and MNDWI...")
    mask_before = build_valid_mask(cube_before["SCL"]) if "SCL" in cube_before else None
    mask_after = build_valid_mask(cube_after["SCL"]) if "SCL" in cube_after else None
    valid_joint = (mask_before & mask_after) if (mask_before is not None and mask_after is not None) else None

    mndwi_before = compute_mndwi(cube_before["B03"], cube_before["B11"], valid_mask=valid_joint)
    mndwi_after = compute_mndwi(cube_after["B03"], cube_after["B11"], valid_mask=valid_joint)

    # Water classification (MNDWI > 0.0 indicates surface water body).
    # NaN (masked) pixels compare False and are therefore never water.
    water_before_raw = mndwi_before > 0.0
    water_after_raw = mndwi_after > 0.0

    # Morphological noise cleanup on the per-scene water masks.  The SAME
    # cleaned masks feed both the hectare metrics and the figure, so the
    # numbers and the picture always agree.
    if min_component_px > 0:
        water_before = filter_noise_morphology(water_before_raw, min_pixel_size=min_component_px)
        water_after = filter_noise_morphology(water_after_raw, min_pixel_size=min_component_px)
    else:
        water_before, water_after = water_before_raw, water_after_raw

    click.echo("6. Performing Change Vector Analysis (CVA) & Otsu Thresholding...")
    diff_mndwi = compute_difference(mndwi_before, mndwi_after, valid_mask=valid_joint)
    cva_mag = compute_cva_magnitude(diff_mndwi, valid_mask=valid_joint)

    # Statistical change threshold (diagnostic layer only)
    otsu_th = otsu_threshold(cva_mag)
    click.echo(f"   Otsu Threshold on |Delta MNDWI|: {otsu_th:.3f}")

    # Isolate water transitions
    persistent_water = water_before & water_after
    water_loss = water_before & ~water_after
    water_gain = ~water_before & water_after

    click.echo("7. Computing quantitative surface area metrics...")
    metrics = summarize_water_change(
        water_before, water_after, valid_mask=valid_joint, pixel_res_m=pixel_res_m
    )
    metrics["otsu_threshold_abs_delta_mndwi"] = round(float(otsu_th), 4)

    # Attach complete provenance metadata for standalone reproducibility
    metrics["metadata"] = {
        "preset": preset,
        "bbox": bbox,
        "baseline_scene_id": item_before.id,
        "baseline_datetime": before_pick["datetime"],
        "baseline_cloud_cover_pct": before_pick["cloud_cover"],
        "baseline_processing_baseline": baseline_b,
        "baseline_boa_offset_dn": cube_before["boa_offset"],
        "observation_scene_id": item_after.id,
        "observation_datetime": after_pick["datetime"],
        "observation_cloud_cover_pct": after_pick["cloud_cover"],
        "observation_processing_baseline": baseline_a,
        "observation_boa_offset_dn": cube_after["boa_offset"],
        "stac_collection": "sentinel-2-l2a",
        "max_cloud_pct": max_cloud,
        "min_component_px": min_component_px,
        "water_threshold_mndwi": 0.0,
        "sentinel_diff_version": __version__,
    }

    click.echo("\n" + "=" * 45)
    click.echo(f"  SURFACE WATER CHANGE SUMMARY: {preset.upper()}")
    click.echo("=" * 45)
    click.echo(f"Baseline Scene       : {item_before.id}")
    click.echo(f"Baseline Date        : {before_pick['datetime'][:10]} (cloud: {cloud_b})")
    click.echo(f"Observation Scene    : {item_after.id}")
    click.echo(f"Observation Date     : {after_pick['datetime'][:10]} (cloud: {cloud_a})")
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
        f"{before_pick['datetime'][:10]} vs {after_pick['datetime'][:10]} | "
        f"Net Change: {metrics['net_change_hectares']} ha ({metrics['percentage_change']}%)"
    )
    plot_change_summary(
        before_index=mndwi_before,
        after_index=mndwi_after,
        diff_magnitude=cva_mag,
        change_mask=(cva_mag > otsu_th),
        persistent_water_mask=persistent_water,
        water_loss_mask=water_loss,
        water_gain_mask=water_gain,
        output_path=fig_file,
        title=f"Istanbul {preset.upper()} Reservoir - Multi-Temporal Water Surface Change",
        subtitle=subtitle,
    )
    click.echo(f"Saved diagnostic figure to: {fig_file}")

    # Generate interactive HTML dashboard report
    html_file = out_path / "interactive" / f"{preset}_report.html"
    generate_interactive_slider_html(
        before_index=mndwi_before,
        after_index=mndwi_after,
        persistent_water_mask=persistent_water,
        water_loss_mask=water_loss,
        water_gain_mask=water_gain,
        output_html_path=html_file,
        title=f"Istanbul {preset.upper()} Reservoir Water Change Analysis",
        metrics=metrics,
        before_label=before_pick["datetime"][:10],
        after_label=after_pick["datetime"][:10],
    )
    click.echo(f"Saved interactive report to: {html_file}")


if __name__ == "__main__":
    main()
