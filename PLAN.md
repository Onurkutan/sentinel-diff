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
- [x] Offline unit tests (small in-memory NumPy arrays; not synthetic raster fixtures), `METHODOLOGY.md`, `DATA.md`
- [ ] v0.1.0 git tag

---

## Known Issues & Recent Fixes

### Resolved in Recent Commits
1. **[RESOLVED] Categorical resampling in `ingest.py`**: SCL categorical layer now strictly uses `Resampling.nearest` rather than bilinear, preventing synthetic intermediate classes along classification boundaries. Verified via `tests/test_ingest.py`.
2. **[RESOLVED] STAC query semantics in `catalog.py`**: `pystac-client` query now uses `max_items` instead of page `limit`, and `analyze` sorts by cloud cover (`sort_by_cloud=True`) to automatically pick the cleanest observation in the requested window.
3. **[RESOLVED] Reproducibility metadata in metrics**: `reports/*_metrics.json` now records complete provenance metadata (preset, bbox, scene IDs, acquisition datetimes, and cloud percentages) for standalone reproducibility.

### Open Known Issues
1. **Sentinel-2 BOA processing baseline offset**: Sentinel-2 Level-2A products under processing baseline $\ge 04.00$ introduce a $+1000$ digital number offset that is not yet corrected. In multi-year comparisons (e.g. 2021 vs 2023), the $|\Delta\text{MNDWI}|$ panel and Otsu threshold are affected by this artifact. Because water classification relies on the sign ($\text{MNDWI} > 0$), hectare metrics are unaffected.
2. **Linter findings**: `ruff check .` returns lint findings across the codebase (including unused imports).
