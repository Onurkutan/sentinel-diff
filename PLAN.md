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

## Known Issues

The following known issues are catalogued and verified against the codebase:

1. **Categorical resampling in `ingest.py`**: The SCL (Scene Classification Layer) categorical layer is resampled using bilinear interpolation, producing spurious intermediate classes (e.g. classes 5, 7, 8) along class boundaries; should be nearest-neighbor.
2. **STAC query semantics in `catalog.py`**: In `pystac-client`, `limit` is page size rather than the total item upper bound; `max_items` should be used instead. Furthermore, `analyze` selects the earliest chronological scene in the date range rather than the least cloudy scene.
3. **Sentinel-2 BOA processing baseline offset**: Sentinel-2 Level-2A products under processing baseline $\ge 04.00$ introduce a $+1000$ digital number offset that is not yet corrected. In multi-year comparisons (e.g. 2021 vs 2023), the $|\Delta\text{MNDWI}|$ panel and Otsu threshold are affected by this artifact. Because water classification relies on the sign ($\text{MNDWI} > 0$), hectare metrics are unaffected.
4. **Reproducibility metadata in metrics**: `reports/*_metrics.json` outputs lack scene IDs, acquisition dates, and bounding box coordinates, so results cannot be reproduced standalone from the JSON file alone.
5. **Linter findings**: `ruff check .` returns 61 findings across the codebase (including unused imports).
