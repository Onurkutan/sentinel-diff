# sentinel-diff

> Multi-temporal satellite change detection and environmental monitoring from open Sentinel-2 surface reflectance data.

`sentinel-diff` is an open, reproducible command-line tool and Python library for detecting surface water body changes over time from optical satellite observations without requiring commercial GIS software or proprietary cloud platforms.

The current pipeline queries public SpatioTemporal Asset Catalogs (STAC), streams Cloud-Optimized GeoTIFF (COG) crops on demand, applies Scene Classification Layer (SCL) cloud masking, and computes the Modified Normalized Difference Water Index (MNDWI) to quantify surface water gains and losses.

---

## Verified Status & Features

Implementation progress is tracked against the codebase in [`PLAN.md`](PLAN.md). Only features wired into the executable pipeline are claimed below:

* **Zero Credentials / Open Data:** Queries public Sentinel-2 L2A collections via Microsoft Planetary Computer STAC endpoint anonymously (*AWS Earth Search support planned*).
* **Windowed Streaming:** Fetches bounding box subsets on demand via Cloud-Optimized GeoTIFF (COG) HTTP range requests—no full granule downloads required.
* **Radiometric Harmonisation:** Reads `s2:processing_baseline` from each STAC item and removes the +1000 DN BOA offset introduced with processing baseline 04.00, so pre-2022 and Collection-1 reprocessed scenes are compared on the same reflectance scale.
* **Scene Pairing:** Deduplicates reprocessed products, then picks the pair with the smallest circular day-of-year distance (cloud cover as tiebreaker) to minimise seasonal bias.
* **Spectral Water Delineation:** Automated SCL valid-pixel masking (filtering clouds, shadows, and defective pixels) and vectorized MNDWI computation (*NDVI and NDBI are implemented in `indices.py` but not yet wired to `analyze`*).
* **Consistent Morphological Cleaning:** A 3×3 opening/closing plus minimum-component filter (`--min-component-px`, default 6 px = 600 m²) is applied to each scene's water mask **once**; the hectare metrics and the figure are derived from the same cleaned masks, so the numbers and the picture always agree.
* **Diagnostic Change Analysis:** Bi-temporal Change Vector Analysis (CVA) magnitude heatmap with the automated Otsu change threshold outlined on the panel.  
  *(Note: CVA magnitude and Otsu thresholding are diagnostic layers only; water classification and hectare accounting use MNDWI > 0).*
* **Quantitative Accounting & Reports:** Computes surface water transition metrics (persistent water, shrinkage, expansion, net change) in hectares with full provenance metadata, outputs a 4-panel publication-ready diagnostic figure, and generates a static HTML summary dashboard linking to the figure (*single-file interactive swipe slider planned*).
* **Offline End-to-End Test:** `tests/test_analyze_e2e.py` runs the complete `analyze` command against stub STAC items backed by local GeoTIFFs and asserts exact hectare values.

---

## Results: Istanbul Alibeyköy Reservoir (2021 vs 2023)

The pipeline was executed to evaluate the severe late-summer drought across Istanbul's **Alibeyköy Reservoir**, comparing DOY-matched cloudless acquisitions from **2021-08-02** against **2023-08-02**:

```bash
sentinel-diff analyze --preset alibeykoy --before-date "2021-08-01/2021-08-31" --after-date "2023-08-01/2023-08-31"
```

### Quantitative Metrics (`reports/alibeykoy_metrics.json`)

| Metric | Value |
|---|---|
| **Preset Area** | `alibeykoy` (BBox: `[28.87, 41.10, 28.96, 41.17]`) |
| **Baseline Date** | 2021-08-02 (`S2B_MSIL2A_20210802T084559_R107_T35TPF_20210802T203106`, cloud: 0.72%) |
| **Observation Date** | 2023-08-02 (`S2B_MSIL2A_20230802T084609_R107_T35TPF_20241025T040038`, cloud: 0.35%) |
| **Processing Baselines** | 03.00 (no BOA offset) vs 05.10 (+1000 DN offset removed) |
| **Morphological Cleaning** | `--min-component-px 6` (default) |
| **Baseline Water Area** | **249.60 ha** |
| **Observation Water Area** | **187.77 ha** |
| **Persistent Water Area** | **166.34 ha** |
| **Water Loss (Drought / Shrinkage)** | **83.26 ha** |
| **Water Gain (Inflow / Expansion)** | **21.43 ha** |
| **Net Surface Water Change** | **−61.83 ha (−24.77 %)** |
| **Otsu threshold on \|ΔMNDWI\|** | 0.263 |

Running the same pair with `--min-component-px 0` (no morphological cleaning) yields 284.73 ha → 228.95 ha, net −55.78 ha (−19.59 %). The ~35 ha difference in the baseline is isolated speckle and features narrower than 3 pixels (mostly bright urban roofs west of the reservoir) that the default cleaning removes. The BOA offset harmonisation does not change the hectare figures at all, because water classification depends only on the sign of MNDWI; it corrects the |ΔMNDWI| panel and the Otsu threshold.

### Diagnostic Figure

The pipeline outputs a publication-quality 4-panel diagnostic figure saved to `reports/figures/alibeykoy_change_analysis.png`:

![Alibeykoy Reservoir Change Analysis](reports/figures/alibeykoy_change_analysis.png)

* **Top Left & Right:** Baseline (2021) and observation (2023) MNDWI water index fields.
* **Bottom Left:** $|\Delta\text{MNDWI}|$ change magnitude; the cyan outline is the automated Otsu change mask.
* **Bottom Right:** Classified water transitions (Persistent Water in blue, Water Loss in red, Water Gain in green), drawn from the same cleaned masks that produce the hectare metrics.

---

## Repository Layout

```
sentinel-diff/
├── PLAN.md              # Ground-truth roadmap with verified [x], [~], [ ] status
├── src/sentinel_diff/
│   ├── catalog.py       # STAC query client for spatio-temporal asset discovery
│   ├── ingest.py        # COG windowed streaming reader
│   ├── mask.py          # Scene classification layer (SCL) cloud/shadow filter
│   ├── indices.py       # Spectral indices (MNDWI, NDWI, NDVI, NDBI)
│   ├── cva.py           # Change Vector Analysis & Otsu/MAD thresholding
│   ├── metrics.py       # Hectare & transition area accounting
│   ├── viz.py           # 4-panel diagnostic figure & HTML summary report generator
│   └── cli.py           # Command-line interface
├── reports/
│   ├── alibeykoy_metrics.json
│   ├── figures/alibeykoy_change_analysis.png
│   └── interactive/alibeykoy_report.html
├── tests/               # Unit + offline end-to-end tests (real GeoTIFF rasters, stub STAC items)
├── scripts/             # check_repo_hygiene.py (zero-leak publish safety scanner)
├── docs/                # METHODOLOGY.md and DATA.md
├── pyproject.toml
└── Makefile
```

---

## CLI Usage

```bash
# Show pipeline status
sentinel-diff status

# List available reservoir presets (alibeykoy, terkos, omerli, etc.)
sentinel-diff presets

# Search for cloudless Sentinel-2 scenes in STAC
sentinel-diff search --preset alibeykoy --date-range "2023-07-01/2023-08-31" --max-cloud 5

# Run bi-temporal change analysis
sentinel-diff analyze --preset alibeykoy --before-date "2021-08-01/2021-08-31" --after-date "2023-08-01/2023-08-31"

# Same, without morphological cleaning (raw MNDWI > 0 accounting)
sentinel-diff analyze --preset alibeykoy --before-date "2021-08-01/2021-08-31" --after-date "2023-08-01/2023-08-31" --min-component-px 0
```

---

## Development & Reproducibility

```bash
# Clone
git clone https://github.com/Onurkutan/sentinel-diff.git
cd sentinel-diff

# Create isolated virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Unix:
source .venv/bin/activate

# Install editable with dev dependencies
pip install -e ".[dev]"

# Run offline test suite
make test

# Run publish-safety scan
make check
```

---

## License

MIT License - Copyright (c) 2026 [Onur Kutan](https://github.com/Onurkutan)
