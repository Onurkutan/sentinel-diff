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

### Morphological Post-Filtering
Single-pixel false positives (due to sub-pixel coregistration noise or wind-driven surface specular reflection) are suppressed using a $3\times3$ binary structuring element:
1. Binary opening to remove isolated spikes.
2. Binary closing to bridge narrow surface fractures.
3. Connected-component filtering discarding components smaller than 6 contiguous pixels ($< 600 \text{ m}^2$).

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
