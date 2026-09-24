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
- [x] AWS Earth Search (`catalog.PROVIDERS` registry, `--provider earthsearch`; canonical `B03`/`B08`/`B11`/`SCL` mapped to `green`/`nir`/`swir16`/`scl`, `earthsearch:boa_offset_applied` honoured; verified by `TestProviders`, `TestDedup.test_earthsearch_*`, `TestAssetMap`, `TestBoaOffset.test_earthsearch_boa_offset_applied_flag_disables_offset`, `test_analyze_end_to_end_earthsearch_provider`)

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
- [~] v0.1.0 git tag: CHANGELOG.md written; tag not yet on the remote (the cloud session could only push its branch). After merging to main run: `git tag -a v0.1.0 -m "sentinel-diff v0.1.0" && git push origin v0.1.0`

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
8. **[RESOLVED] Figure/metrics mismatch**: morphological cleaning was applied only to the figure's loss/gain layers while metrics used raw masks. Now cleaned once per scene and shared. Verified: `test_analyze_e2e.py::test_analyze_end_to_end_default_cleaning` (accounting self-consistency) and `::test_analyze_without_cleaning_keeps_isolated_pixel`. Effect on Alibeyköy at the time: baseline 284.73 → 249.60 ha, net −55.78 → −61.83 ha (current figures after the window-snapping fix, issue 12: 284.63 → 250.27 ha, net −53.34 → −59.12 ha).
9. **[RESOLVED] Morphological filter eroded the image border**: scipy `border_value=0` stripped a 1-px rim from regions touching the bbox edge. Fixed with edge-replicating padding. Verified: `test_cva.py::test_filter_noise_morphology_preserves_image_border` (40 px kept of 60 before the fix).
10. **[RESOLVED] DOY distance ignored the year boundary**: 30 Dec vs 2 Jan scored 362 days apart. Now circular. Verified: `TestSelectScenePair::test_doy_distance_wraps_around_new_year`.
11. **[RESOLVED] Lint depended on the installed ruff version**: no `[tool.ruff]` section, so ruff 0.15 reported 10 E712 findings that 0.16 did not. Rule set pinned; findings fixed.
12. **[RESOLVED] Window transform off by the fractional pixel offset**: `read_windowed_band` returned a transform for the unrounded window while rasterio read whole pixels, shifting exported georeferences by up to 0.5 px (5 m). The window is now snapped to whole pixels from rounded edges. Verified: `test_ingest.py::TestWindowSnapping::test_transform_is_pixel_aligned_and_shape_matches` (transform origin 666597.52 before the fix, on-grid after).
13. **[RESOLVED] Cleaned water masks could contain masked pixels**: binary closing filled 1-px cloud/no-data holes with water in the masks passed to the figure and HTML overlay (metrics were already masked). Masks are now intersected with the joint-valid grid after cleaning. Guarded by the `TRANSITION_NODATA == 4` and class-count assertions in `test_analyze_e2e.py`.
14. **[RESOLVED] Scene pairing crashed on missing cloud cover**: `None` is treated as 100 %. Verified: `test_catalog.py::TestRobustness::test_none_cloud_cover_does_not_crash_pairing`.
15. **[RESOLVED] Earth Search reprocessing sequence compared as strings** (`"9" > "10"`). Numeric compare. Verified: `TestRobustness::test_earthsearch_sequence_compares_numerically`.

### Open Known Issues
1. **Urban false positives in MNDWI > 0**: bright roofs and impervious surfaces west of Alibeyköy classify as water in both scenes and show up as speckle in the transition map (reduced but not eliminated by `--min-component-px`). Candidate fix: cross-check against SCL class 6 (`mask.isolate_water_scl`) or a stricter MNDWI threshold; not implemented.
2. **Morphological opening removes features narrower than 3 px**: streams and thin channels (< 30 m wide) are dropped from the water masks by design of the 3×3 opening. Documented in `docs/METHODOLOGY.md`; use `--min-component-px 0` to disable.
3. **Edge-padding bias in morphological cleaning**: replicated-edge padding protects water bodies cut by the bounding box but also lets 1–2 px strips lying exactly along the border survive the 3×3 opening (an interior strip of the same width is removed). Documented in `docs/METHODOLOGY.md` §3; no test covers the asymmetry.
4. **DOY distance uses a 365-day year**: on leap years the wrap-around distance is off by one day around New Year only.
5. **Provider-dependent input products**: for the same acquisition date Planetary Computer and Earth Search can serve different processing baselines (Alibeyköy 2021-08-02: PC 03.00 original vs Earth Search 05.00 Collection-1). Baseline water differs by ~26 ha (250.27 vs 276.65 ha). Documented in README; no harmonisation of SCL/atmospheric correction across baselines is possible from the pipeline side.
6. **Scene grids must match**: `analyze` raises if the two windows differ in shape (different tile/orbit). No automatic reprojection onto a common grid yet.
