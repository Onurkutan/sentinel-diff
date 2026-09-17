# Roadmap & Implementation Status (PLAN.md)

This document tracks the verified implementation status of `sentinel-diff`. All status markers reflect empirical verification against the codebase:

- `[x]` **done**: Wired into the `sentinel-diff analyze` pipeline and verified with reproducible output (metrics JSON, figure, or HTML report).
- `[~]` **implemented, not wired**: Function/algorithm is implemented and covered by unit tests, but not currently called or utilized in the main `analyze` pipeline output.
- `[ ]` **not started**: Planned but not yet implemented.

---

## Roadmap

### Phase 1 – Scaffold & safety
- [x] `pyproject.toml`, `.gitignore`, `scripts/check_repo_hygiene.py`
- [ ] Test fixtures (`tests/fixtures` and `conftest.py` missing)
- [ ] CI (`.github/workflows` missing)

### Phase 2 – Data ingestion
- [x] Microsoft Planetary Computer STAC + windowed COG reading
- [ ] AWS Earth Search (asset keys are PC-specific: `B03`/`B08`/`B11`/`SCL`; Earth Search uses `green`/`nir`/`swir16`/`scl`)

### Phase 3 – Spectral core
- [x] SCL valid mask, MNDWI
- [~] NDVI, NDBI (implemented in `indices.py`, not called by `analyze`)

### Phase 4 – Change detection
- [~] CVA magnitude + Otsu (computed; `change_mask` passed to `viz.py` but unused in transition rendering, no impact on metrics)
- [~] MAD threshold (implemented in `cva.py`, never called)
- [~] Morphological filter (applied only to figure masks; metrics computed from raw binary masks)

### Phase 5 – Metrics & reporting
- [x] Hectare metrics, matplotlib 4-panel figure
- [ ] Single-file HTML slider map (current HTML is a static dashboard: no slider, links to PNG via relative path)

### Phase 6 – Docs, tests, release
- [x] Real offline unit tests: `test_ingest.py` (GeoTIFF rasters via `tmp_path`), `test_catalog.py` (synthetic scene dicts), `test_cva.py`, `test_indices.py`, `test_mask.py`, `test_metrics.py`
- [x] `METHODOLOGY.md`, `DATA.md`
- [ ] v0.1.0 git tag
- [ ] CI (`.github/workflows` missing)

---

## Known Issues & Recent Fixes

### Resolved
1. **[RESOLVED] Categorical resampling in `ingest.py`**: SCL categorical layer uses `Resampling.nearest`, preventing synthetic intermediate classes. Verified: `TestLoadMultispectralCube::test_scl_preserves_classes` fails with bilinear (classes `{4,5,7,8,9}`), passes with nearest.
2. **[RESOLVED] Cloud cover 0.0 treated as 100.0**: `catalog.py` used `properties.get("eo:cloud_cover", 100.0) or 100.0` — `0.0` is falsy and was replaced by `100.0`. Fixed with `_extract_cloud_cover()` using explicit `None` check. Verified: `TestCloudCoverExtraction::test_zero_cloud_is_zero`.
3. **[RESOLVED] Scene pair selection and reprocessing duplicates**: STAC returns both original and Collection-1 reprocessed items for the same acquisition. `dedup_scenes()` keeps only the latest processing timestamp per product key; `select_scene_pair()` picks the DOY-closest pair with cloud tiebreaker. Verified: `TestDedup::test_keeps_latest_processing`, `TestSelectScenePair::test_prefers_doy_proximity_over_lower_cloud`.
4. **[RESOLVED] Hardcoded max-cloud in analyze**: Was `15.0`; now configurable via `--max-cloud` (default `10.0`).
5. **[RESOLVED] Reproducibility metadata in metrics**: `reports/*_metrics.json` records complete provenance (preset, bbox, scene IDs, datetimes, cloud %).

### Open Known Issues
1. **Sentinel-2 BOA processing baseline offset**: Sentinel-2 Level-2A products under processing baseline $\ge 04.00$ introduce a $+1000$ digital number offset that is not yet corrected. In multi-year comparisons (e.g. 2021 vs 2023), the $|\Delta\text{MNDWI}|$ panel and Otsu threshold are affected by this artifact. Because water classification relies on the sign ($\text{MNDWI} > 0$), hectare metrics are unaffected.
2. **Linter findings**: `ruff check .` returns lint findings across the codebase (including unused imports).
