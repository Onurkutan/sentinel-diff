"""
STAC discovery client for public Sentinel-2 L2A collections.
Queries open STAC catalogs (e.g. Microsoft Planetary Computer or AWS Earth Search).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import planetary_computer as pc
from pystac_client import Client

# Microsoft Planetary Computer public STAC endpoint (free, no account needed for basic search)
DEFAULT_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION_SENTINEL_2 = "sentinel-2-l2a"

# Reference Bounding Boxes for Istanbul Water Reservoirs [min_lon, min_lat, max_lon, max_lat]
RESERVOIR_PRESETS: dict[str, list[float]] = {
    "alibeykoy": [28.87, 41.10, 28.96, 41.17],
    "terkos": [28.53, 41.25, 28.73, 41.38],
    "omerli": [29.28, 41.00, 29.45, 41.10],
    "buyukcekmece": [28.48, 41.02, 28.60, 41.13],
    "sazlidere": [28.67, 41.08, 28.78, 41.16],
}


def get_preset_bbox(name: str) -> list[float]:
    """Returns the bounding box coordinates for a named preset."""
    name_clean = name.lower().replace("-", "_").strip()
    if name_clean not in RESERVOIR_PRESETS:
        available = ", ".join(RESERVOIR_PRESETS.keys())
        raise ValueError(f"Unknown preset '{name}'. Available presets: {available}")
    return RESERVOIR_PRESETS[name_clean]


def _extract_cloud_cover(properties: dict[str, Any]) -> float:
    """Extract cloud cover from STAC item properties.

    Returns 100.0 only when the value is genuinely missing (``None``).
    A cloud cover of ``0.0`` is preserved as ``0.0``.
    """
    cc = properties.get("eo:cloud_cover")
    return cc if cc is not None else 100.0


def search_sentinel_scenes(
    bbox: list[float],
    datetime_range: str,
    max_cloud_cover: float = 15.0,
    max_items: int = 10,
    stac_url: str = DEFAULT_STAC_URL,
) -> list[dict[str, Any]]:
    """Discovers available Sentinel-2 scenes matching bounding box and date criteria.

    Results are sorted chronologically by acquisition datetime.
    """
    client = Client.open(stac_url, modifier=pc.sign_inplace)

    search = client.search(
        collections=[COLLECTION_SENTINEL_2],
        bbox=bbox,
        datetime=datetime_range,
        query={"eo:cloud_cover": {"lt": max_cloud_cover}},
        max_items=max_items,
    )

    items = list(search.items())
    # Sort chronologically
    items.sort(key=lambda x: x.datetime)

    results = []
    for item in items:
        results.append({
            "id": item.id,
            "datetime": item.datetime.isoformat() if item.datetime else None,
            "cloud_cover": _extract_cloud_cover(item.properties),
            "assets": list(item.assets.keys()),
            "item_obj": item,
        })
    return results


# ── Scene pair selection ─────────────────────────────────────────────────


def _product_key(item_id: str) -> str:
    """Extract the product key from a Sentinel-2 item ID.

    The first five underscore-separated segments form a unique product
    identity (platform, processing level, acquisition datetime, relative
    orbit, tile).  Example::

        S2B_MSIL2A_20230802T084609_R107_T35TPF_20230802T163932
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ product key
                                                 ^^^^^^^^^^^^^^ processing timestamp

    Reprocessed products share the same product key but have a different
    sixth segment (processing timestamp).
    """
    parts = item_id.split("_")
    return "_".join(parts[:5])


def _processing_timestamp(item_id: str) -> str:
    """Return the processing-timestamp segment (6th part) of a Sentinel-2 ID."""
    parts = item_id.split("_")
    return parts[5] if len(parts) > 5 else ""


def _day_of_year(dt_iso: str) -> int:
    """Return the day-of-year for an ISO-8601 datetime string."""
    # Python 3.10 fromisoformat does not handle trailing 'Z'
    dt = datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
    return dt.timetuple().tm_yday


def _doy_distance(doy_a: int, doy_b: int) -> int:
    """Circular day-of-year distance so that late December and early January
    are treated as neighbours (e.g. DOY 365 vs DOY 2 -> 2, not 363)."""
    d = abs(doy_a - doy_b)
    return min(d, 365 - d)


def dedup_scenes(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove reprocessing duplicates from a list of STAC scene dicts.

    When multiple items share the same product key (first 5 ID segments),
    only the one with the latest processing timestamp (6th segment) is kept.
    """
    best: dict[str, dict[str, Any]] = {}
    for scene in scenes:
        key = _product_key(scene["id"])
        ts = _processing_timestamp(scene["id"])
        if key not in best or ts > _processing_timestamp(best[key]["id"]):
            best[key] = scene
    return list(best.values())


def select_scene_pair(
    before_scenes: list[dict[str, Any]],
    after_scenes: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select the best (before, after) scene pair for change detection.

    Selection criteria (in priority order):

    1. **Day-of-year proximity**: minimises phenological / seasonal bias
       between the two acquisitions.
    2. **Cloud cover sum**: among pairs with identical DOY distance, the
       pair with the lowest combined cloud cover is preferred.

    Both lists are deduplicated before pairing (see :func:`dedup_scenes`).

    Raises
    ------
    ValueError
        If either list is empty after deduplication.
    """
    before_deduped = dedup_scenes(before_scenes)
    after_deduped = dedup_scenes(after_scenes)

    if not before_deduped or not after_deduped:
        raise ValueError("No scenes available for pairing after deduplication.")

    best_pair: tuple[dict[str, Any], dict[str, Any]] | None = None
    best_score: tuple[int, float] | None = None

    for b in before_deduped:
        b_doy = _day_of_year(b["datetime"])
        b_cc = b["cloud_cover"]
        for a in after_deduped:
            a_doy = _day_of_year(a["datetime"])
            a_cc = a["cloud_cover"]
            score = (_doy_distance(b_doy, a_doy), b_cc + a_cc)
            if best_score is None or score < best_score:
                best_score = score
                best_pair = (b, a)

    assert best_pair is not None  # guaranteed by non-empty inputs
    return best_pair
