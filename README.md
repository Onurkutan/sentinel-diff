# sentinel-diff

> Multi-temporal satellite change detection and environmental monitoring from open Sentinel-2 surface reflectance data.

`sentinel-diff` is an open, reproducible command-line tool and Python library for detecting surface water body changes over time from optical satellite observations without requiring commercial GIS software or proprietary cloud platforms.

The current pipeline queries public SpatioTemporal Asset Catalogs (STAC), streams Cloud-Optimized GeoTIFF (COG) crops on demand, applies Scene Classification Layer (SCL) cloud masking, and computes the Modified Normalized Difference Water Index (MNDWI) to quantify surface water gains and losses.

---

## Verified Status & Features

Implementation progress is tracked against the codebase in [`PLAN.md`](PLAN.md). Only features wired into the executable pipeline are claimed below:

* **Zero Credentials / Open Data:** Queries public Sentinel-2 L2A collections via Microsoft Planetary Computer STAC endpoint anonymously (*AWS Earth Search support planned*).
* **Windowed Streaming:** Fetches bounding box subsets on demand via Cloud-Optimized GeoTIFF (COG) HTTP range requests—no full granule downloads required.
* **Spectral Water Delineation:** Automated SCL valid-pixel masking (filtering clouds, shadows, and defective pixels) and vectorized MNDWI computation (*NDVI and NDBI are implemented in `indices.py` but not yet wired to `analyze`*).
* **Diagnostic Change Analysis:** Bi-temporal Change Vector Analysis (CVA) magnitude heatmap and automated Otsu thresholding for visual diagnostics.  
  *(Note: CVA magnitude and Otsu thresholding currently serve as diagnostic layers in the 4-panel figure; water classification and hectare accounting are computed directly from MNDWI > 0 thresholding).*
* **Quantitative Accounting & Reports:** Computes surface water transition metrics (persistent water, shrinkage, expansion, net change) in hectares, outputs a 4-panel publication-ready diagnostic figure, and generates a static HTML summary dashboard linking to the figure (*single-file interactive swipe slider planned*).

---

## Results: Istanbul Alibeyköy Reservoir (2021 vs 2023)

The pipeline was executed to evaluate the severe late-summer drought across Istanbul's **Alibeyköy Reservoir**, comparing cloudless acquisitions from **2021-08-02** against **2023-08-02**:

```bash
sentinel-diff analyze --preset alibeykoy --before-date "2021-08-01/2021-08-31" --after-date "2023-08-01/2023-08-31"
```

### Quantitative Metrics (`reports/alibeykoy_metrics.json`)

| Metric | Value |
|---|---|
| **Preset Area** | `alibeykoy` (BBox: `[28.87, 41.10, 28.96, 41.17]`) |
| **Baseline Date** | 2021-08-02 (`S2B_MSIL2A_20210802T084559_R107_T35TPF`) |
| **Observation Date** | 2023-08-02 (`S2B_MSIL2A_20230802T084609_R107_T35TPF`) |
| **Baseline Water Area** | **271.70 ha** |
| **Observation Water Area** | **222.89 ha** |
| **Persistent Water Area** | **180.57 ha** |
| **Water Loss (Drought / Shrinkage)** | **91.13 ha** |
| **Water Gain (Inflow / Expansion)** | **42.32 ha** |
| **Net Surface Water Change** | **−48.81 ha (−17.96 %)** |

### Diagnostic Figure

The pipeline outputs a publication-quality 4-panel diagnostic figure saved to `reports/figures/alibeykoy_change_analysis.png`:

![Alibeykoy Reservoir Change Analysis](reports/figures/alibeykoy_change_analysis.png)

* **Top Left & Right:** Baseline (2021) and observation (2023) MNDWI water index fields.
* **Bottom Left:** $|\Delta\text{MNDWI}|$ change magnitude with automated Otsu thresholding.
* **Bottom Right:** Classified water transitions (Persistent Water in blue, Water Loss in red, Water Gain in green).

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
├── tests/               # Unit tests running against in-memory NumPy arrays
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
