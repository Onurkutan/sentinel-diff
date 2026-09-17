"""
STAC discovery client for public Sentinel-2 L2A collections.
Queries open STAC catalogs (e.g. Microsoft Planetary Computer or AWS Earth Search).
"""

from typing import List, Dict, Any, Optional
from pystac_client import Client
import planetary_computer as pc

# Microsoft Planetary Computer public STAC endpoint (free, no account needed for basic search)
DEFAULT_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION_SENTINEL_2 = "sentinel-2-l2a"

# Reference Bounding Boxes for Istanbul Water Reservoirs [min_lon, min_lat, max_lon, max_lat]
RESERVOIR_PRESETS: Dict[str, List[float]] = {
    "alibeykoy": [28.87, 41.10, 28.96, 41.17],
    "terkos": [28.53, 41.25, 28.73, 41.38],
    "omerli": [29.28, 41.00, 29.45, 41.10],
    "buyukcekmece": [28.48, 41.02, 28.60, 41.13],
    "sazlidere": [28.67, 41.08, 28.78, 41.16],
}


def get_preset_bbox(name: str) -> List[float]:
    """Returns the bounding box coordinates for a named preset."""
    name_clean = name.lower().replace("-", "_").strip()
    if name_clean not in RESERVOIR_PRESETS:
        available = ", ".join(RESERVOIR_PRESETS.keys())
        raise ValueError(f"Unknown preset '{name}'. Available presets: {available}")
    return RESERVOIR_PRESETS[name_clean]


def search_sentinel_scenes(
    bbox: List[float],
    datetime_range: str,
    max_cloud_cover: float = 15.0,
    max_items: int = 10,
    sort_by_cloud: bool = False,
    stac_url: str = DEFAULT_STAC_URL,
) -> List[Dict[str, Any]]:
    """
    Discovers available Sentinel-2 scenes matching bounding box and date criteria.
    Uses max_items to bound total returned items across pages.
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
    
    if sort_by_cloud:
        # Sort by cloud cover ascending, then by date
        items.sort(key=lambda x: (x.properties.get("eo:cloud_cover", 100.0) or 100.0, x.datetime))
    else:
        # Sort chronologically
        items.sort(key=lambda x: x.datetime)
    
    results = []
    for item in items:
        results.append({
            "id": item.id,
            "datetime": item.datetime.isoformat() if item.datetime else None,
            "cloud_cover": item.properties.get("eo:cloud_cover"),
            "assets": list(item.assets.keys()),
            "item_obj": item,
        })
    return results
