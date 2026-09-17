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

* **Provider:** Microsoft Planetary Computer STAC API (`https://planetarycomputer.microsoft.com/api/stac/v1`).
* **Access Method:** Direct HTTP GET / Range-request queries on Cloud-Optimized GeoTIFFs (COG).
* **Authentication:** None required for public open data catalog browsing and reading. Temporary read tokens are generated in-place via public anonymous SAS URLs.
* **Storage Policy:** `sentinel-diff` redistributes no raw imagery in this git repository. All raster arrays are streamed windowed on demand.
