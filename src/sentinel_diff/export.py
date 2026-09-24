"""
GIS export of the classified water-transition map.

Writes the transition classes as a georeferenced GeoTIFF (native CRS) and as
GeoJSON polygons (EPSG:4326) so results open directly in QGIS or any other
open GIS tool.  Only ``rasterio`` and the standard library are used; no
geopandas/fiona dependency is introduced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.warp import transform_geom
from scipy import ndimage

_CONNECTIVITY_8 = np.ones((3, 3), dtype=np.uint8)

TRANSITION_CODES: dict[str, int] = {
    "background": 0,
    "persistent_water": 1,
    "water_loss": 2,
    "water_gain": 3,
}
TRANSITION_NODATA = 255

_CODE_TO_NAME = {code: name for name, code in TRANSITION_CODES.items()}
_VECTOR_CLASSES = ("persistent_water", "water_loss", "water_gain")


def build_transition_raster(
    persistent_water: np.ndarray,
    water_loss: np.ndarray,
    water_gain: np.ndarray,
    valid_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Combine boolean transition masks into a single uint8 class raster.

    Pixel values follow ``TRANSITION_CODES``; pixels outside *valid_mask*
    are set to ``TRANSITION_NODATA`` (255).
    """
    transition = np.full(np.shape(persistent_water), TRANSITION_CODES["background"], dtype=np.uint8)
    transition[np.asarray(persistent_water, dtype=bool)] = TRANSITION_CODES["persistent_water"]
    transition[np.asarray(water_loss, dtype=bool)] = TRANSITION_CODES["water_loss"]
    transition[np.asarray(water_gain, dtype=bool)] = TRANSITION_CODES["water_gain"]
    if valid_mask is not None:
        transition[~np.asarray(valid_mask, dtype=bool)] = TRANSITION_NODATA
    return transition


def write_transition_geotiff(
    transition: np.ndarray,
    transform: rasterio.Affine,
    crs: Any,
    output_path: Path,
) -> Path:
    """Write the transition raster as a single-band uint8 GeoTIFF (nodata=255, deflate)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(transition, dtype=np.uint8)
    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="uint8",
        crs=crs,
        transform=transform,
        nodata=TRANSITION_NODATA,
        compress="deflate",
    ) as dst:
        dst.write(data, 1)
        dst.set_band_description(1, "water_transition")
    return output_path


def write_transition_geojson(
    transition: np.ndarray,
    transform: rasterio.Affine,
    crs: Any,
    output_path: Path,
    pixel_res_m: float | None = None,
) -> dict[str, Any]:
    """Vectorise transition classes 1-3 into a WGS-84 GeoJSON FeatureCollection.

    Each feature carries ``class_code``, ``class_name`` and ``area_ha``.  The
    area is derived from the polygon's pixel count multiplied by the native
    pixel area (``abs(transform.a * transform.e)``), so it is exact on the
    analysis grid and independent of the reprojection to EPSG:4326.

    Returns ``{"feature_count": int, "area_ha_by_class": {name: float}}``.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(transition, dtype=np.uint8)

    if pixel_res_m is not None:
        pixel_area_ha = float(pixel_res_m) ** 2 / 10_000.0
    else:
        pixel_area_ha = abs(float(transform.a) * float(transform.e)) / 10_000.0

    features: list[dict[str, Any]] = []
    area_by_class = dict.fromkeys(_VECTOR_CLASSES, 0.0)

    for name in _VECTOR_CLASSES:
        code = TRANSITION_CODES[name]
        class_mask = data == code
        if not class_mask.any():
            continue
        # 8-connected labelling: one label per polygon emitted by ``shapes``
        # (same connectivity), so the label's pixel count is the polygon's area.
        labels, _n = ndimage.label(class_mask, structure=_CONNECTIVITY_8)
        labels = labels.astype(np.int32)
        pixel_counts = np.bincount(labels.ravel())
        for geom, label_value in shapes(labels, mask=class_mask, connectivity=8, transform=transform):
            pixel_count = int(pixel_counts[int(label_value)])
            area_ha = round(pixel_count * pixel_area_ha, 4)
            area_by_class[name] += area_ha
            geom_wgs84 = transform_geom(crs, "EPSG:4326", geom)
            features.append({
                "type": "Feature",
                "geometry": geom_wgs84,
                "properties": {
                    "class_code": int(code),
                    "class_name": name,
                    "area_ha": area_ha,
                },
            })

    collection = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(collection, f)

    return {
        "feature_count": len(features),
        "area_ha_by_class": {k: round(v, 2) for k, v in area_by_class.items()},
    }

