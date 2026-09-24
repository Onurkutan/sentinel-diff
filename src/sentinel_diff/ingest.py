"""
Cloud-Optimized GeoTIFF (COG) windowed streaming reader.
Fetches only the requested bounding box coordinates using HTTP range requests.
"""


import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

# Sentinel-2 L2A products generated with processing baseline >= 04.00 (from
# 2022-01-25 onwards, and all Collection-1 reprocessed products) encode
# surface reflectance with an additive offset of +1000 digital numbers
# (BOA_ADD_OFFSET = -1000).  Older products have no offset.  Neither
# Planetary Computer nor AWS Earth Search harmonises this, so bi-temporal
# comparisons across the baseline change must subtract it explicitly.
BOA_OFFSET_BASELINE = 4.0
BOA_ADD_OFFSET = 1000

# Categorical layers must never be offset-corrected.
CATEGORICAL_BANDS = {"SCL"}


def parse_processing_baseline(item) -> float | None:
    """Return the ``s2:processing_baseline`` of a STAC item as a float.

    Returns ``None`` when the property is missing or unparsable.
    """
    props = getattr(item, "properties", None) or {}
    raw = props.get("s2:processing_baseline")
    if raw is None:
        return None
    try:
        return float(str(raw).strip())
    except ValueError:
        return None


def boa_offset_for_item(item) -> int:
    """Digital-number offset that must be subtracted from reflectance bands.

    ``1000`` for processing baseline >= 04.00, ``0`` otherwise (including
    when the baseline is unknown, in which case no correction is applied).
    """
    baseline = parse_processing_baseline(item)
    if baseline is not None and baseline >= BOA_OFFSET_BASELINE:
        return BOA_ADD_OFFSET
    return 0


def apply_boa_offset(band: np.ndarray, offset: int) -> np.ndarray:
    """Subtract *offset* from a reflectance band, clamping at zero.

    Returns an ``int32`` array so that unsigned inputs cannot wrap around.
    """
    corrected = band.astype(np.int32) - int(offset)
    return np.clip(corrected, 0, None)


def read_windowed_band(
    asset_href: str,
    bbox_wgs84: list[float],
    target_shape: tuple[int, int] | None = None,
    resampling: rasterio.enums.Resampling = rasterio.enums.Resampling.bilinear,
) -> tuple[np.ndarray, rasterio.Affine, rasterio.crs.CRS]:
    """
    Reads only the bounding box region from a remote Cloud-Optimized GeoTIFF.
    
    Args:
        asset_href: Direct or signed URL to the GeoTIFF asset
        bbox_wgs84: [min_lon, min_lat, max_lon, max_lat] in EPSG:4326
        target_shape: Optional (height, width) to resample to (useful for aligning 20m SWIR to 10m Green/NIR)
        resampling: Resampling algorithm (use nearest for categorical bands like SCL)
        
    Returns:
        (band_array, transform, crs)
    """
    with rasterio.open(asset_href) as src:
        # Transform WGS84 (lat/lon) bounds to raster native CRS (e.g. UTM)
        min_lon, min_lat, max_lon, max_lat = bbox_wgs84
        left, bottom, right, top = transform_bounds(
            "EPSG:4326", src.crs, min_lon, min_lat, max_lon, max_lat
        )
        
        # Calculate pixel window
        window = from_bounds(left, bottom, right, top, transform=src.transform)
        
        # Read windowed data
        if target_shape is not None:
            data = src.read(
                1,
                window=window,
                out_shape=target_shape,
                resampling=resampling,
            )
        else:
            data = src.read(1, window=window)
            
        win_transform = rasterio.windows.transform(window, src.transform)
        return data, win_transform, src.crs


def load_multispectral_cube(
    item,
    bbox_wgs84: list[float],
    bands: list[str] = ("B03", "B08", "B11", "SCL"),
) -> dict[str, np.ndarray]:
    """
    Loads required Sentinel-2 bands for a given STAC item within a bounding box.
    Automatically aligns 20m bands (like B11 SWIR and SCL) to the 10m grid (B03 Green, B08 NIR).
    Uses nearest-neighbor resampling for categorical layers (SCL) to avoid spurious intermediate classes.

    Reflectance bands are harmonised to the pre-04.00 radiometric convention by
    subtracting the BOA offset (see :func:`boa_offset_for_item`).  The applied
    offset is recorded under ``cube["boa_offset"]``.
    """
    offset = boa_offset_for_item(item)

    # First read B03 (10m) as reference geometry
    green_href = item.assets["B03"].href
    green_data, transform, crs = read_windowed_band(green_href, bbox_wgs84)
    ref_shape = green_data.shape

    cube = {
        "B03": apply_boa_offset(green_data, offset),
        "transform": transform,
        "crs": crs,
        "boa_offset": offset,
    }
    
    # Read remaining bands resampled to reference 10m shape
    for band in bands:
        if band == "B03":
            continue
        if band not in item.assets:
            continue
        band_href = item.assets[band].href
        resampling_mode = (
            rasterio.enums.Resampling.nearest
            if band == "SCL"
            else rasterio.enums.Resampling.bilinear
        )
        band_data, _, _ = read_windowed_band(
            band_href, bbox_wgs84, target_shape=ref_shape, resampling=resampling_mode
        )
        if band in CATEGORICAL_BANDS:
            cube[band] = band_data
        else:
            cube[band] = apply_boa_offset(band_data, offset)

    return cube
