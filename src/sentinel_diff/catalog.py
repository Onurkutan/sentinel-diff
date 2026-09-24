"""
STAC discovery client for public Sentinel-2 L2A collections.
Queries open STAC catalogs (e.g. Microsoft Planetary Computer or AWS Earth Search).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import planetary_computer as pc
from pystac_client import Client

# Microsoft Planetary Computer public STAC endpoint (free, no account needed for basic search)
DEFAULT_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
# AWS Earth Search (Element 84) public STAC endpoint (free, no signing required)
EARTHSEARCH_STAC_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION_SENTINEL_2 = "sentinel-2-l2a"

# Canonical band keys used throughout the pipeline (Planetary Computer naming).
CANONICAL_BANDS = ("B03", "B08", "B11", "SCL")


@dataclass(frozen=True)
class StacProvider:
    """Description of a public Sentinel-2 L2A STAC provider.

    ``asset_map`` translates canonical band keys (``B03``/``B08``/``B11``/``SCL``)
    to the provider's asset keys.  ``modifier`` is passed to
    :meth:`pystac_client.Client.open` (e.g. URL signing) or ``None``.
    """

    name: str
    stac_url: str
    collection: str = COLLECTION_SENTINEL_2
    asset_map: dict[str, str] = field(
        default_factory=lambda: {b: b for b in CANONICAL_BANDS}
    )
    modifier: Callable[..., Any] | None = None


PROVIDERS: dict[str, StacProvider] = {
    "pc": StacProvider(
        name="pc",
        stac_url=DEFAULT_STAC_URL,
        asset_map={"B03": "B03", "B08": "B08", "B11": "B11", "SCL": "SCL"},
        modifier=pc.sign_inplace,
    ),
    "earthsearch": StacProvider(
        name="earthsearch",
        stac_url=EARTHSEARCH_STAC_URL,
        asset_map={"B03": "green", "B08": "nir", "B11": "swir16", "SCL": "scl"},
        modifier=None,
    ),
}
DEFAULT_PROVIDER = "pc"


def get_provider(name: str) -> StacProvider:
    """Return the :class:`StacProvider` registered under *name*."""
    key = name.lower().strip()
    if key not in PROVIDERS:
        available = ", ".join(PROVIDERS.keys())
        raise ValueError(f"Unknown STAC provider '{name}'. Available providers: {available}")
    return PROVIDERS[key]

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
    stac_url: str | None = None,
    provider: str = DEFAULT_PROVIDER,
) -> list[dict[str, Any]]:
    """Discovers available Sentinel-2 scenes matching bounding box and date criteria.

    *provider* selects an entry of :data:`PROVIDERS` (``"pc"`` or
    ``"earthsearch"``); *stac_url* overrides that provider's endpoint.
    Results are sorted chronologically by acquisition datetime and every
    scene dict carries the provider name under ``"provider"``.
    """
    prov = get_provider(provider)
    url = stac_url if stac_url is not None else prov.stac_url
    client = Client.open(url, modifier=prov.modifier)

    search = client.search(
        collections=[prov.collection],
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
            "provider": prov.name,
        })
    return results


# ── Scene pair selection ─────────────────────────────────────────────────


def _is_esa_id(item_id: str) -> bool:
    """True for ESA-style product names (Planetary Computer), e.g.
    ``S2B_MSIL2A_20230802T084609_R107_T35TPF_20241025T040038``.

    Earth Search IDs (``S2B_35TPF_20230802_0_L2A``) have five segments and
    no ``MSIL2A`` level segment.
    """
    parts = item_id.split("_")
    return len(parts) >= 6 or (len(parts) > 1 and parts[1].startswith("MSIL"))


def _product_key(item_id: str) -> str:
    """Extract the product key from a Sentinel-2 item ID.

    For ESA names (Planetary Computer) the first five underscore-separated
    segments form a unique product identity (platform, processing level,
    acquisition datetime, relative orbit, tile).  Example::

        S2B_MSIL2A_20230802T084609_R107_T35TPF_20230802T163932
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ product key
                                                 ^^^^^^^^^^^^^^ processing timestamp

    For Earth Search names the first three segments (platform, tile,
    acquisition date) form the product key and the fourth segment is the
    reprocessing sequence number::

        S2B_35TPF_20230802_0_L2A
        ^^^^^^^^^^^^^^^^^^ product key
                           ^ processing sequence

    Reprocessed products share the same product key but have a different
    processing segment.
    """
    parts = item_id.split("_")
    if _is_esa_id(item_id):
        return "_".join(parts[:5])
    return "_".join(parts[:3])


def _processing_timestamp(item_id: str) -> str:
    """Return the processing segment of a Sentinel-2 ID (6th part for ESA
    names, 4th part for Earth Search names; ``""`` when absent)."""
    parts = item_id.split("_")
    if _is_esa_id(item_id):
        return parts[5] if len(parts) > 5 else ""
    return parts[3] if len(parts) > 3 else ""


def _processing_sort_key(item_id: str) -> tuple[int, int | str]:
    """Sortable key for the processing segment.

    Earth Search sequence numbers are integers (``"10"`` must beat ``"9"``);
    ESA processing timestamps compare correctly as strings.
    """
    ts = _processing_timestamp(item_id)
    return (1, int(ts)) if ts.isdigit() else (0, ts)


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

    When multiple items share the same product key (see :func:`_product_key`),
    only the one with the latest processing segment is kept.  Both ESA
    (Planetary Computer) and Earth Search ID formats are supported.
    """
    best: dict[str, dict[str, Any]] = {}
    for scene in scenes:
        key = _product_key(scene["id"])
        ts = _processing_sort_key(scene["id"])
        if key not in best or ts > _processing_sort_key(best[key]["id"]):
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
        b_cc = b["cloud_cover"] if b["cloud_cover"] is not None else 100.0
        for a in after_deduped:
            a_doy = _day_of_year(a["datetime"])
            a_cc = a["cloud_cover"] if a["cloud_cover"] is not None else 100.0
            score = (_doy_distance(b_doy, a_doy), b_cc + a_cc)
            if best_score is None or score < best_score:
                best_score = score
                best_pair = (b, a)

    assert best_pair is not None  # guaranteed by non-empty inputs
    return best_pair
