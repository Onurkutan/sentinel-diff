# Methodology & Algorithmic Design

`sentinel-diff` provides an open, reproducible framework for estimating surface and water body changes from multi-temporal optical satellite observations. This document outlines the physical and mathematical rationale underlying each processing step.

---

## 1. Spectral Water Identification: MNDWI

Standard Normalized Difference Water Index (NDWI; McFeeters, 1996) uses the green (B03) and near-infrared (B08) bands:

$$\text{NDWI} = \frac{\text{Green} - \text{NIR}}{\text{Green} + \text{NIR}}$$

While effective for isolated open water, NDWI often misclassifies built-up impervious surfaces (concrete, asphalt) as water due to similar reflectance characteristics in NIR.

To eliminate this noise around urban reservoirs (such as Alibeyköy and Ömerli in Istanbul), `sentinel-diff` employs the **Modified Normalized Difference Water Index** (MNDWI; Xu, 2006), substituting NIR with short-wave infrared (SWIR-1 / B11, ~1.61 $\mu$m):

$$\text{MNDWI} = \frac{\text{Green} - \text{SWIR}}{\text{Green} + \text{SWIR}}$$

Water features have significantly stronger absorption in SWIR than in NIR, while built-up land displays distinctly higher reflectance in SWIR. Consequently, MNDWI values $> 0.0$ provide clean delineation of water bodies without urban edge contamination.

---

## 2. Cloud & Artifact Masking: SCL Filtering

Sentinel-2 Level-2A products include a 20m Scene Classification Layer (SCL) derived from multi-spectral thresholding and spatial consistency checks.

We construct a boolean clean-pixel mask ($M_{\text{valid}}$) by filtering out:
* `0` (No data / out of granule)
* `1` (Saturated / defective pixels)
* `3` (Cloud shadows)
* `8` (Medium probability cloud)
* `9` (High probability cloud)
* `10` (Thin cirrus)

Only pixels satisfying $M_{\text{valid}, t_1} \land M_{\text{valid}, t_2}$ are accepted into the change analysis.

---

## 3. Bi-Temporal Change Vector Analysis (CVA)

Given two normalized index matrices $I_{t_1}$ and $I_{t_2}$ sampled during identical seasonal windows across years (e.g. August 2021 vs August 2023), the pixel-wise difference is:

$$\Delta I = I_{t_2} - I_{t_1}$$

$$\Delta M = |\Delta I|$$

### Automated Otsu Thresholding
Rather than enforcing an arbitrary threshold, we derive the change decision threshold $T^*$ using Otsu's method from scratch over the finite distribution of $\Delta M$:

$$T^* = \arg\max_T \left[ \omega_0(T) \omega_1(T) (\mu_0(T) - \mu_1(T))^2 \right]$$

When an unpopulated valley forms between the unchanged background and changed targets (a flat variance plateau), the optimal threshold is evaluated at the midpoint of candidate bins.

### Morphological Cleaning of the Water Masks
Single-pixel false positives (sub-pixel coregistration noise, wind-driven specular reflection, bright roofs) are suppressed on **each scene's binary water mask** ($I_t > 0$) using a $3\times3$ binary structuring element:
1. Binary opening to remove isolated spikes (this also removes features narrower than 3 pixels, i.e. channels under ~30 m).
2. Binary closing to bridge narrow surface fractures.
3. Connected-component filtering discarding components smaller than `--min-component-px` contiguous pixels (default 6, $< 600 \text{ m}^2$; `0` disables cleaning entirely).

Before the operators run, the mask is padded by one pixel with replicated edge values and cropped afterwards. Without this, scipy treats the outside of the array as background and erodes a 1-pixel rim from any water body touching the bounding box. The trade-off is deliberate: replicated padding assumes the surface continues unchanged beyond the bounding box, which is the common case for a reservoir cut by the AOI edge, but it also lets a 1–2 pixel strip lying exactly along the border survive the opening where an identical strip in the interior would be removed. Choose the AOI so that the water body of interest does not hug the bounding-box edge.

The transition classes of Section 4, the hectare metrics and the classified panel of the figure are all derived from these same cleaned masks, so reported numbers and the rendered map are guaranteed to agree.

---

## 4. Transition Classification & Surface Metrics

For each valid pixel $p$, the state transition is categorized as:

| Category | $I_{t_1} > 0$ (Baseline) | $I_{t_2} > 0$ (Observation) | Ecological Interpretation |
|---|---|---|---|
| **Persistent Water** | True | True | Stable reservoir body |
| **Water Contraction** | True | False | Reservoir shrinkage / drought exposure |
| **Water Expansion** | False | True | Reservoir refilling / inflow expansion |
| **Persistent Land** | False | False | Unaffected terrestrial surface |

Surface area in hectares is computed directly from pixel counts:

$$\text{Area (ha)} = \frac{N_{\text{pixels}} \times \Delta x \times \Delta y}{10{,}000}$$

where $\Delta x = \Delta y = 10\text{ m}$ for Sentinel-2 high-resolution bands.

---

## 5. Scene Pair Selection

Bi-temporal change detection requires two scenes acquired at comparable phenological states. To minimise seasonal bias while maximising image quality, the pipeline applies a three-step selection protocol:

### 5.1 Reprocessing Deduplication

ESA periodically reprocesses Sentinel-2 products (e.g. Collection-1 reprocessing in 2024). This produces multiple STAC items sharing the same acquisition but with different processing timestamps. The item ID encodes this structure:

```
S2B_MSIL2A_20230802T084609_R107_T35TPF_20241025T040038
└───────── product key (segments 1–5) ─────────┘ └── processing timestamp ──┘
```

`dedup_scenes()` groups items by their product key (first five underscore-separated segments) and retains only the item with the latest processing timestamp, ensuring the most up-to-date radiometric calibration is used.

### 5.2 Day-of-Year Proximity Scoring

All candidate `(before, after)` pairs are scored by `(d_circ(DOY_before, DOY_after), cloud_before + cloud_after)` where `d_circ(a, b) = min(|a − b|, 365 − |a − b|)`, so that late-December and early-January acquisitions are treated as neighbours. The pair with the smallest DOY difference is selected; among ties, the pair with the lowest combined cloud cover wins. This ensures the two scenes are acquired at the closest possible point in the annual vegetation cycle, minimising phenological artefacts in the change signal.

### 5.3 Cloud Cover Handling

Cloud cover values are extracted with explicit `None`-checking: a cloud cover of `0.0` (perfectly clear sky) is preserved as `0.0`, while missing values default to `100.0`. The maximum cloud cover threshold is configurable via `--max-cloud` (default: `10.0%`).

---

## 6. Radiometric Harmonisation (BOA Offset)

From processing baseline 04.00 (25 January 2022) onwards, and in every Collection-1 reprocessed product, ESA stores Level-2A surface reflectance as

$$\text{DN} = \rho \times 10{,}000 + 1000$$

whereas earlier products use $\text{DN} = \rho \times 10{,}000$. Public STAC providers redistribute the archive as-is, so a 2021 scene and a 2023 scene differ by a constant 1000 DN in every reflectance band.

`sentinel-diff` reads `s2:processing_baseline` from each STAC item and, when it is $\ge 04.00$, subtracts 1000 from B03, B08 and B11 (clamped at zero, never applied to the categorical SCL layer). The applied offset is written to `metrics.metadata.*_boa_offset_dn`.

Because subtracting the same constant from $G$ and $S$ leaves the sign of $(G - S)$ unchanged, the offset does **not** change which pixels satisfy $\text{MNDWI} > 0$ (the only exception is a pixel where both bands fall below 1000 DN and are clamped to zero, which becomes undefined and is not counted as water; real water has $G \gg 1000$ DN). Hectare metrics are therefore unaffected in practice, while $|\Delta\text{MNDWI}|$ and the Otsu threshold do change, which is why the offset is corrected.
