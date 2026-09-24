# Roadmap & Implementation Status (PLAN.md)

This document tracks the verified implementation status of `sentinel-diff`. All status markers reflect empirical verification against the codebase:

- `[x]` **done**: Wired into the `sentinel-diff analyze` pipeline and verified with reproducible output (metrics JSON, figure, or HTML report).
- `[~]` **implemented, not wired**: Function/algorithm is implemented and covered by unit tests, but not currently called or utilized in the main `analyze` pipeline output.
- `[ ]` **not started**: Planned but not yet implemented.

---

## Roadmap

### Phase 1 – Scaffold & safety
- [x] `pyproject.toml`, `.gitignore`, `scripts/check_repo_hygiene.py`
- [x] Test fixtures (`tests/conftest.py` with shared GeoTIFF helpers and pytest fixtures)
- [x] CI (`.github/workflows/ci.yml`: lint + test + hygiene on Python 3.10–3.12)
- [x] Version-independent lint (`[tool.ruff]` rule set pinned in `pyproject.toml`; Makefile runs tooling via `python -m`)

### Phase 2 – Data ingestion
- [x] Microsoft Planetary Computer STAC + windowed COG reading
- [x] BOA offset harmonisation from `s2:processing_baseline` (`ingest.boa_offset_for_item`, verified by `TestBoaOffset`)
- [x] Scene pairing with reprocessing dedup and circular DOY distance
- [ ] AWS Earth Search (asset keys are PC-specific: `B03`/`B08`/`B11`/`SCL`; Earth Search uses `green`/`nir`/`swir16`/`scl`)

### Phase 3 – Spectral core
- [x] SCL valid mask, MNDWI
- [~] NDVI, NDBI (implemented in `indices.py`, not called by `analyze`)

### Phase 4 – Change detection
- [x] CVA magnitude + Otsu (diagnostic layer: Otsu change mask outlined on the magnitude panel; `otsu_threshold_abs_delta_mndwi` recorded in metrics JSON; no impact on hectare accounting by design)
- [~] MAD threshold (implemented in `cva.py`, never called)
- [x] Morphological filter applied once to each scene's water mask; metrics AND figure derive from the same cleaned masks (`--min-component-px`, verified by `test_analyze_e2e.py`)

### Phase 5 – Metrics & reporting
- [x] Hectare metrics, matplotlib 4-panel figure
- [x] GeoTIFF + GeoJSON export of the transition map (`export.py`, `--no-export` flag). Verified: `test_export.py::test_write_transition_geotiff_roundtrip`, `test_export.py::test_write_transition_geojson_features_areas_and_wgs84`, `test_analyze_e2e.py::test_analyze_end_to_end_default_cleaning` (GeoJSON water_loss area == `water_loss_hectares` == 0.80 ha), `test_analyze_e2e.py::test_analyze_no_export_skips_gis_files`
- [x] Single-file HTML slider map: before/after MNDWI swipe slider (CSS `clip-path` + `<input type="range">`), toggleable transition overlay, metric cards, legend and provenance table; the three rasters are embedded as base64 palette PNGs (longest side <= 900 px), no external assets or relative links (`test_viz.py::test_generate_interactive_slider_html_is_single_file`, HTML assertions in `test_analyze_e2e.py`)

### Phase 6 – Docs, tests, release
- [x] Real offline unit tests: `test_ingest.py` (GeoTIFF rasters via `tmp_path`), `test_catalog.py` (synthetic scene dicts), `test_cva.py`, `test_indices.py`, `test_mask.py`, `test_metrics.py`
- [x] Offline end-to-end test of `analyze` (`test_analyze_e2e.py`: STAC search monkeypatched, stub items backed by local GeoTIFFs, exact hectare assertions)
- [x] `METHODOLOGY.md`, `DATA.md`
- [ ] v0.1.0 git tag

---

## Known Issues & Recent Fixes

### Resolved
1. **[RESOLVED] Categorical resampling in `ingest.py`**: SCL categorical layer uses `Resampling.nearest`, preventing synthetic intermediate classes. Verified: `TestLoadMultispectralCube::test_scl_preserves_classes` fails with bilinear (classes `{4,5,7,8,9}`), passes with nearest.
2. **[RESOLVED] Cloud cover 0.0 treated as 100.0**: `catalog.py` used `properties.get("eo:cloud_cover", 100.0) or 100.0` — `0.0` is falsy and was replaced by `100.0`. Fixed with `_extract_cloud_cover()` using explicit `None` check. Verified: `TestCloudCoverExtraction::test_zero_cloud_is_zero`.
3. **[RESOLVED] Scene pair selection and reprocessing duplicates**: STAC returns both original and Collection-1 reprocessed items for the same acquisition. `dedup_scenes()` keeps only the latest processing timestamp per product key; `select_scene_pair()` picks the DOY-closest pair with cloud tiebreaker. Verified: `TestDedup::test_keeps_latest_processing`, `TestSelectScenePair::test_prefers_doy_proximity_over_lower_cloud`.
4. **[RESOLVED] Hardcoded max-cloud in analyze**: Was `15.0`; now configurable via `--max-cloud` (default `10.0`).
5. **[RESOLVED] Reproducibility metadata in metrics**: `reports/*_metrics.json` records complete provenance (preset, bbox, scene IDs, datetimes, cloud %).
6. **[RESOLVED] Linter findings**: `ruff check src/ tests/` returns 0 errors. Fixed import sorting (I001), unused imports (F401), deprecated type annotations (UP006/UP035), unused variables (F841, RUF059).
7. **[RESOLVED] Sentinel-2 BOA processing baseline offset**: products with baseline $\ge 04.00$ carry a $+1000$ DN offset. `load_multispectral_cube` now subtracts it from reflectance bands (never SCL) based on `s2:processing_baseline`; the applied offset is recorded in `metrics.metadata`. Verified: `TestBoaOffset::test_cube_subtracts_offset_from_reflectance_but_not_scl`. Effect on the Alibeyköy run: hectares unchanged (sign-based classification), $|\Delta\text{MNDWI}|$ panel and Otsu threshold corrected.
8. **[RESOLVED] Figure/metrics mismatch**: morphological cleaning was applied only to the figure's loss/gain layers while metrics used raw masks. Now cleaned once per scene and shared. Verified: `test_analyze_e2e.py::test_analyze_end_to_end_default_cleaning` (accounting self-consistency) and `::test_analyze_without_cleaning_keeps_isolated_pixel`. Effect on Alibeyköy: baseline 284.73 → 249.60 ha, net −55.78 → −61.83 ha.
9. **[RESOLVED] Morphological filter eroded the image border**: scipy `border_value=0` stripped a 1-px rim from regions touching the bbox edge. Fixed with edge-replicating padding. Verified: `test_cva.py::test_filter_noise_morphology_preserves_image_border` (40 px kept of 60 before the fix).
10. **[RESOLVED] DOY distance ignored the year boundary**: 30 Dec vs 2 Jan scored 362 days apart. Now circular. Verified: `TestSelectScenePair::test_doy_distance_wraps_around_new_year`.
11. **[RESOLVED] Lint depended on the installed ruff version**: no `[tool.ruff]` section, so ruff 0.15 reported 10 E712 findings that 0.16 did not. Rule set pinned; findings fixed.

### Open Known Issues
1. **Urban false positives in MNDWI > 0**: bright roofs and impervious surfaces west of Alibeyköy classify as water in both scenes and show up as speckle in the transition map (reduced but not eliminated by `--min-component-px`). Candidate fix: cross-check against SCL class 6 (`mask.isolate_water_scl`) or a stricter MNDWI threshold; not implemented.
2. **Morphological opening removes features narrower than 3 px**: streams and thin channels (< 30 m wide) are dropped from the water masks by design of the 3×3 opening. Documented in `docs/METHODOLOGY.md`; use `--min-component-px 0` to disable.
3. **Scene grids must match**: `analyze` raises if the two windows differ in shape (different tile/orbit). No automatic reprojection onto a common grid yet.
