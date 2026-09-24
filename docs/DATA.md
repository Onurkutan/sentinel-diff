# Data Sources & Attribution

All satellite observations in `sentinel-diff` are sourced directly from public, unauthenticated cloud endpoints. No private credentials, accounts, or proprietary licenses are required.

---

## 1. Copernicus Sentinel-2 L2A (European Space Agency)

* **Mission:** European Space Agency (ESA) Copernicus Programme.
* **Product:** Sentinel-2 Multi-Spectral Instrument (MSI) Level-2A (Bottom-of-Atmosphere / Surface Reflectance).
* **Bands Utilized:**
  * **B03 (Green):** 560 nm central wavelength, 10 m spatial resolution.
  * **B08 (NIR):** 842 nm central wavelength, 10 m spatial resolution.
  * **B11 (SWIR-1):** 1610 nm central wavelength, 20 m spatial resolution (resampled to 10 m grid).
  * **SCL (Scene Classification Layer):** 20 m thematic pixel classification.
* **Licensing:** Open Access under the [Copernicus Open Access Policy](https://sentinels.copernicus.eu/web/sentinel/copernicus-open-access-policy), allowing commercial and academic use.

---

## 2. SpatioTemporal Asset Catalog (STAC) Endpoints

Two interchangeable public providers are registered in `sentinel_diff.catalog.PROVIDERS` and selected with `--provider` (default `pc`). Both serve the `sentinel-2-l2a` collection; the pipeline always works on canonical band keys (`B03`/`B08`/`B11`/`SCL`) and translates them per provider.

### 2a. Microsoft Planetary Computer (`--provider pc`, default)

* **Provider:** Microsoft Planetary Computer STAC API (`https://planetarycomputer.microsoft.com/api/stac/v1`).
* **Asset naming:** ESA band names `B03`, `B08`, `B11`, `SCL`; item IDs are ESA product names (`S2B_MSIL2A_20230802T084609_R107_T35TPF_20241025T040038`, last segment = processing timestamp).
* **Access Method:** Direct HTTP GET / Range-request queries on Cloud-Optimized GeoTIFFs (COG).
* **Authentication:** None required for public open data catalog browsing and reading. Temporary read tokens are generated in-place via public anonymous SAS URLs (`planetary_computer.sign_inplace`).
* **BOA offset:** Not harmonised by the provider; `sentinel-diff` subtracts 1000 DN for `s2:processing_baseline >= 04.00`.

### 2b. AWS Earth Search (`--provider earthsearch`)

* **Provider:** Element 84 Earth Search STAC API (`https://earth-search.aws.element84.com/v1`), backed by the `sentinel-cogs` public S3 bucket (`us-west-2`).
* **Asset naming:** Common-name keys `green` (B03), `nir` (B08), `swir16` (B11), `scl` (SCL); item IDs are `S2B_35TPF_20230802_0_L2A` (platform, tile, date, reprocessing sequence, level). Reprocessing dedup keeps the highest sequence number.
* **Access Method:** Public HTTPS COGs; no URL signing.
* **Authentication:** None. No AWS account or credentials are needed.
* **BOA offset:** Earth Search removes the +1000 DN offset at ingestion and flags it with `earthsearch:boa_offset_applied: true`. When the flag is present and true, `sentinel-diff` applies no further correction regardless of `s2:processing_baseline`.

* **Storage Policy:** `sentinel-diff` redistributes no raw imagery in this git repository. All raster arrays are streamed windowed on demand.
