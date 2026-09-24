# Changelog

All notable changes to `sentinel-diff` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow SemVer.

## [0.1.0] - 2026-09-24

First tagged release. Bi-temporal Sentinel-2 surface-water change detection
from open STAC catalogs, with a reproducible Alibeyköy (Istanbul) benchmark.

### Added
- STAC discovery on Microsoft Planetary Computer and AWS Earth Search
  (`--provider pc|earthsearch`), with per-provider asset-name mapping and
  reprocessing deduplication for both ESA and Earth Search item IDs.
- Windowed Cloud-Optimized GeoTIFF streaming of B03/B08/B11/SCL; SCL
  upsampled with nearest-neighbour resampling.
- BOA reflectance offset harmonisation from `s2:processing_baseline`
  (respects `earthsearch:boa_offset_applied`).
- Scene pairing by circular day-of-year distance with cloud-cover tiebreaker.
- SCL valid-pixel masking, MNDWI water delineation, CVA magnitude and
  Otsu change threshold (diagnostic).
- Morphological cleaning of the per-scene water masks with
  `--min-component-px` (default 6, 0 disables); metrics and figure share the
  same cleaned masks.
- Hectare accounting (persistent / loss / gain / net) with full provenance
  metadata in `reports/<preset>_metrics.json`.
- 4-panel matplotlib diagnostic figure.
- Standalone single-file HTML report with before/after swipe slider,
  transition overlay, metric cards and provenance table (imagery embedded).
- GeoTIFF (uint8 class raster, nodata 255) and WGS-84 GeoJSON export of the
  transition map (`--no-export` to skip).
- Offline test suite (55 tests) including an end-to-end run of `analyze`
  against stub STAC items backed by local GeoTIFFs; CI on Python 3.10-3.12.
- Repository hygiene scanner (`scripts/check_repo_hygiene.py`).

### Fixed
- Morphological filter eroded a 1-pixel rim from regions touching the image
  border (scipy `border_value=0`).
- Day-of-year distance ignored the year boundary.
- Cloud cover of exactly 0.0 was treated as missing (100 %).
- Lint results depended on the installed ruff version; rule set is now pinned.

### Benchmark
Alibeyköy Reservoir, 2021-08-02 vs 2023-08-02 (Planetary Computer):
baseline 249.60 ha, observation 187.77 ha, net −61.83 ha (−24.77 %).
