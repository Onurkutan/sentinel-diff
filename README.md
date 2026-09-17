# sentinel-diff

> Multi-temporal satellite change detection and environmental monitoring from open Sentinel-2 surface reflectance data.

`sentinel-diff` is an open, reproducible command-line tool and Python library for detecting surface, water body, and land cover changes over time without requiring expensive proprietary GIS software or cloud platform locking.

It pairs cloud-optimized windowed querying of public SpatioTemporal Asset Catalogs (STAC) with robust spectral math (MNDWI, NDVI, NDBI) and statistical change vector analysis (CVA).

---

## Key Features

* **Zero Credentials / Fully Open Data:** Queries public Sentinel-2 L2A collections via open STAC endpoints (Microsoft Planetary Computer / AWS Earth Search).
* **Windowed Streaming:** Reads only target bounding boxes via Cloud-Optimized GeoTIFF (COG) HTTP range requests—no downloading gigabytes of unneeded scenes.
* **Spectral Indices & Cloud Masking:** Automated scene classification filtering (SCL) and vectorized NumPy implementations of MNDWI, NDVI, and NDBI.
* **Statistical Change Detection:** Bi-temporal Change Vector Analysis (CVA) with Otsu thresholding and robust z-scores (MAD) to separate meaningful structural shift from seasonal noise.
* **Surface Metrics & Visualization:** Quantitative area impact in hectares / km², publication-ready comparison figures, and single-file interactive HTML slider maps.

---

## Architecture & Layout

```
sentinel-diff/
├── src/sentinel_diff/
│   ├── catalog.py       # STAC query client for spatio-temporal asset discovery
│   ├── ingest.py        # COG windowed streaming reader
│   ├── mask.py          # Scene classification layer (SCL) filtering & cloud masking
│   ├── indices.py       # Vectorized spectral index math (MNDWI, NDVI, NDBI)
│   ├── cva.py           # Change Vector Analysis & statistical thresholding
│   ├── metrics.py       # Hectare & surface area quantification
│   ├── viz.py           # Static figures and interactive slider map generator
│   └── cli.py           # Command-line interface
├── reports/
│   ├── figures/         # Generated publication-quality figures
│   └── interactive/     # Standalone HTML before/after slider maps
├── tests/               # Unit tests running against synthetic raster fixtures
├── scripts/             # check_repo_hygiene.py (zero-leak publish safety scanner)
├── docs/                # METHODOLOGY.md and DATA.md
├── pyproject.toml
└── Makefile
```

---

## Case Study: Istanbul Water Reservoirs (2019 – 2024)

The primary reference benchmark evaluates multi-year surface water contraction and drought recovery across major Istanbul reservoirs (**Ömerli, Terkos, Alibeyköy**) by contrasting late-summer cloudless passes across multiple years.

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

# Run test suite & hygiene scan
make test
make check
```

---

## License

MIT License - Copyright (c) 2026 [Onur Kutan](https://github.com/Onurkutan)
