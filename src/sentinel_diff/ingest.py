"""
Cloud-Optimized GeoTIFF (COG) windowed streaming reader.
Fetches only the requested bounding box coordinates using HTTP range requests.
"""

from typing import List, Dict, Optional, Tuple
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
import numpy as np


def read_windowed_band(
    asset_href: str,
    bbox_wgs84: List[float],
    target_shape: Optional[Tuple[int, int]] = None,
) -> Tuple[np.ndarray, rasterio.Affine, rasterio.crs.CRS]:
    """
    Reads only the bounding box region from a remote Cloud-Optimized GeoTIFF.
    
    Args:
        asset_href: Direct or signed URL to the GeoTIFF asset
        bbox_wgs84: [min_lon, min_lat, max_lon, max_lat] in EPSG:4326
        target_shape: Optional (height, width) to resample to (useful for aligning 20m SWIR to 10m Green/NIR)
        
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
                resampling=rasterio.enums.Resampling.bilinear,
            )
        else:
            data = src.read(1, window=window)
            
        win_transform = rasterio.windows.transform(window, src.transform)
        return data, win_transform, src.crs


def load_multispectral_cube(
    item,
    bbox_wgs84: List[float],
    bands: List[str] = ("B03", "B08", "B11", "SCL"),
) -> Dict[str, np.ndarray]:
    """
    Loads required Sentinel-2 bands for a given STAC item within a bounding box.
    Automatically aligns 20m bands (like B11 SWIR and SCL) to the 10m grid (B03 Green, B08 NIR).
    """
    # First read B03 (10m) as reference geometry
    green_href = item.assets["B03"].href
    green_data, transform, crs = read_windowed_band(green_href, bbox_wgs84)
    ref_shape = green_data.shape
    
    cube = {"B03": green_data, "transform": transform, "crs": crs}
    
    # Read remaining bands resampled to reference 10m shape
    for band in bands:
        if band == "B03":
            continue
        if band not in item.assets:
            continue
        band_href = item.assets[band].href
        band_data, _, _ = read_windowed_band(band_href, bbox_wgs84, target_shape=ref_shape)
        cube[band] = band_data
        
    return cube
