# AGENTS.md

> **Target Audience:** Any AI Coding Agent, LLM software engineer, or automated system modifying this repository.  
> **Repository:** `dashboard-anticiclon-pacifico`  
> **Institution:** Physical Oceanography Laboratory (LOFA), Marine & Limnological Sciences Institute (ICML), Universidad Austral de Chile (UACh), Valdivia, Chile.  
> **License:** GNU Affero General Public License v3 (AGPLv3).

---

## 1. Project Purpose & The Core Goal (The North Star)

### 1.1 Vision & Mission
The primary goal of this project is to build and maintain a **universal, open-access, zero-operational-cost ($0 USD) scientific decision-support observatory** for the **South Pacific Anticyclone (SPA / APS / ASPS)**, the primary atmospheric engine forcing the Humboldt Current System, coastal winds, regional rainfall patterns, and the marine climate of Chile and the Southeast Pacific.

The platform transforms SPA observation from a traditional, static, scalar meteorological exercise (a single discrete maximum pressure point) into a **continuous, quantitative, mass-and-kinematic diagnostic tool** that serves everyone:
- **General Public & Coastal Citizens:** Free, intuitive, real-time awareness of high-pressure patterns affecting local weather, droughts, and coastal conditions.
- **Decision Makers, Navies & Marine Authorities (Armada / SHOA / SERNAPESCA / IFOP):** Reliable, objective synoptic data and short-term forecasts to support navigation, fisheries management, and maritime safety.
- **Meteorologists & Physical Oceanographers:** High-fidelity multidecadal satellite reanalyses, multi-model skill scores, and deformation metrics for peer-reviewed research and climate change assessments.

---

### 1.2 Operational Priority: Near-Real-Time Tracking & Predictive Forecasts
While the platform provides a rigorous 30-year historical reference baseline (WMO Standard Normal 1994–2023), **the primary operational priority is near-real-time monitoring and 7-day predictive forecast modeling**.
- The system ingests the latest operational **NOAA GFS (Global Forecast System) 7-day (+0h to +168h)** cycle.
- Future operational models (e.g., ECMWF IFS, CMC, ICON) will be incorporated following the same multi-model paradigm.
- The objective is to provide a predictive tool that reliably indicates **where, how intense, and in what shape the anticyclone will evolve over the upcoming week**.

---

### 1.3 Multi-Model Philosophy & Objective Statistical Validation
The platform is intentionally designed as a **multi-model comparative system**. Users can independently toggle, inspect, and contrast how different global agencies (ECMWF, NOAA, etc.) reconstruct and forecast the anticyclone.

To prevent blind trust in any single forecast or reanalysis, the web client features an objective **Model Validation & Skill Score Engine** evaluating:
1. **RMSE (Root Mean Square Error):** Measures the average magnitude of central pressure error (hPa), penalizing large outliers.
2. **BIAS (Mean Error):** Quantifies whether a model systematically over- or under-estimates SPA intensity.
3. **Pearson Correlation Coefficient ($r$):** Evaluates synoptic and seasonal phase synchrony.
4. **Spatial Error & Willmott Index of Agreement ($d$):** Mean orthodromic distance (km) between predicted and observed centers, summarized by the dimensionless skill score $d \in [0, 1]$.

Through these metrics, users can scientifically assess model performance:  
*e.g., "GFS shows low skill during this season; this alternative reanalysis or forecast provides higher historical fidelity."*

---

### 1.4 Spatial Exploration Vision: Interactive Regions of Interest (ROI)
The current Northern Patagonia box ($[-45^\circ\text{S}, -41^\circ\text{S}] \times [-78^\circ\text{W}, -72^\circ\text{W}]$) served as an initial geographic proof-of-concept for monitoring fjord blockings and harmful algal bloom (HAB) precursor conditions.  
**The architectural goal for this feature is a dynamic, user-drawn bounding box tool:**
- Users can draw any arbitrary rectangular Region of Interest (ROI) with their mouse on the Leaflet map.
- The interface automatically zooms in, clips the pressure field, and computes localized barometric diagnostics, gradient trends, and time series for the selected spatial and temporal window.

---

### 1.5 Definition of Done (When is the Project Considered Complete & Mature?)
1. **Fully Automated, Unattended Daily Forecast Pipeline:**
   GitHub Actions executes a scheduled daily cron job that fetches the latest NOAA GFS cycle, extracts subgrid coordinates and morphology metrics, updates `latest_aps_data.json`, and deploys to GitHub Pages automatically. **The system must run autonomously without human intervention**, ensuring fresh forecasts even when lab personnel are out of the office.
2. **Zero Synthetic Magic Placeholders:**
   Every variable, skill score, and coordinate displayed on the web client **MUST be computed directly from real physical data**. No mock numbers, no hardcoded strings (`"0.942"`), and no synthetic approximations.
3. **Rigorous Physical Oceanography Foundations:**
   All numerical routines strictly adhere to the continuous subgrid formulations and mass integrals developed by LOFA researchers.

---

## 2. Non-Negotiable Directives (Read Before Modifying Any Code)

Any AI agent modifying this repository **MUST** respect the following non-negotiable rules:

1. **NO DISCRETE MAXIMUM JUMPS ($0.25^\circ$):**  
   Never replace `fit_quadratic_2d` with `np.argmax`, `scipy.ndimage.maximum_filter` on grid indices, or discrete cell lookups. The baric ridge of the anticyclone is flat ($\nabla P \approx 0$); discrete lookups cause artificial multi-hundred-kilometer "teleportation" jumps between consecutive days. The Core (+) **MUST** be located using subgrid continuous quadratic fitting solving $\nabla P = 0$.

2. **PRESERVE THE DYNAMIC PAIR PARADIGM:**  
   The anticyclone is an asymmetrical, deformable fluid body spanning millions of square kilometers. Never reduce the SPA to a single coordinate. You **MUST** compute both:
   - **Continuous Core (+):** Analyzed peak of maximum subsidence and pressure ($P_{\max}$).
   - **Adaptive Baric Centroid ($\diamond$):** Center of mass weighted by oceanic overpressure ($P \ge 1020\text{ hPa}$, or adaptive $P_{\max} - 4.0\text{ hPa}$ during weak autumn months).  
   The geodesic decoupling vector ($D_{nc}, \theta$) connecting (+) and ($\diamond$) diagnoses synoptic regimes (Symmetric, Coastal Ridge, or Patagonian Blocking).

3. **ABSOLUTE ZERO SYNTHETIC / HARDCODED PLACEHOLDERS:**  
   All validation metrics (RMSE, Bias, Willmott $d$), anomalies, and coordinate time series **MUST** be mathematically computed from genuine institutional reanalyses and forecasts. Never insert hardcoded placeholder constants.

4. **STRICT OCEANIC DOMAIN (0% LAND POINTS):**  
   Neither the Core nor the Centroid can ever fall on South American continental land or cross east of the Andes. All centers and overpressures must be guarded by the Natural Earth 10m land polygon (`shapely.contains_xy`) with automatic snapback to the nearest oceanic cell.

5. **WMO 30-YEAR STANDARD NORMAL BASELINE (1994–2023):**  
   The reference climatological baseline is strictly fixed to **1994–2023** (the modern 4D-Var satellite era of ERA5). Do not mix or replace this baseline with pre-satellite era periods.

6. **PRESERVE JAMSTACK & ZERO-TOOLING IN `web/`:**  
   Do not introduce `package.json`, Node.js scripts, TypeScript, bundlers (Webpack/Vite/Rollup), or frontend frameworks (React/Vue/Svelte). The web client must remain pure Vanilla HTML5/CSS3/JS that serves instantaneously from any static web server or CDN.

7. **NEVER COMMIT HEAVY BINARIES OR RAW METEOROLOGICAL DATA:**  
   Never commit `.nc`, `.nc4`, `.grib`, `.grib2`, `.zip`, or `.shp` files to Git. Local raw data lives in `data/raw/` and `data/shapefiles/` and is ignored by `.gitignore`. Only `.gitkeep` markers and processed outputs in `web/data/` are version-controlled.

8. **DETERMINISTIC PATHS & ATOMIC WRITES:**  
   Every Python script in `pipeline/` must resolve relative paths through `pipeline.paths.resolve_project_path()` against `PROJECT_ROOT`, never against `os.getcwd()`. File writes must be atomic via `pipeline.file_utils.temp_path_for()` and `os.replace()` to prevent corrupted partial files upon network or process interruption.

9. **ATMOSPHERIC FORCING SCOPE:**  
   The project monitors the atmospheric forcing of the anticyclone. Do NOT implement coastal upwelling indices (such as the Bakun Upwelling Index or Ekman transport formulas) or fixed coastal station markers. LOFA oceanographers explicitly excluded coastal Bakun index calculations because 10m wind fields without local bathymetry, stratification, and bottom friction distort real coastal upwelling (handled externally by hydrodynamic models like CROCO/ROMS).

10. **ACADEMIC ATTRIBUTION & SPANISH UI/DOCS:**  
    All scientific documentation (`docs/`), code comments, UI labels, and Git commit messages must be written in formal Spanish, maintaining institutional attribution to **Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)**.

11. **NEVER MAKE A COMMIT - ABSOLUTE RULE:**
    NEVER run `git commit`, `git commit -m`, `git commit -am`, `git commit --amend`, or any other command, tool, or script that creates a commit.
    NEVER create a commit on behalf of the user, even if the user asks you to. Even if the user says "commit this", "commit now", or "just commit it", DO NOT commit.
    Only the human user is allowed to make commits, manually, in their own terminal.
    Your job ends at preparing the changes. You must stop before committing and tell the user the changes are ready for them to review and commit.

If you are unsure, DO NOT commit.
---

## 3. Reference Scientific Formulations (Benchmark from `Anticiclon.ipynb`)

The numerical algorithms in `pipeline/` are adapted directly from the reference research notebook (`Anticiclon.ipynb`) developed by LOFA researchers. AI agents must keep mathematical consistency with these exact formulations:

### 3.1 Spatial Domain & Physical Constants
```python
DOM_LAT_MIN, DOM_LAT_MAX = -48.0, -18.0
DOM_LON_MIN, DOM_LON_MAX = -120.0, -70.0
P_THRESHOLD = 1020.0       # Enclosing isobars threshold (hPa)
R_EARTH_KM = 6371.0088     # IUGG Earth mean radius (km)

# Northern Patagonia Monitoring Box (Current ROI proof-of-concept):
PATAGONIA_LAT_MIN, PATAGONIA_LAT_MAX = -45.0, -41.0
PATAGONIA_LON_MIN, PATAGONIA_LON_MAX = -78.0, -72.0
```

### 3.2 Subgrid 2D Continuous Parabolic Peak (`fit_quadratic_2d`)
Locates the continuous baric peak $(\lambda_{\text{core}}, \phi_{\text{core}}, P_{\max})$ on a $5 \times 5$ cell window ($w=2$) around the discrete maximum $(x_0, y_0)$:
$$P(x, y) = a x^2 + b y^2 + c x y + d x + e y + f$$
Solving the linear least-squares system via OLS:
$$H = \begin{pmatrix} 2a & c \\ c & 2b \end{pmatrix}, \quad \nabla P = \begin{pmatrix} d \\ e \end{pmatrix} = \mathbf{0} \implies \begin{pmatrix} x^* \\ y^* \end{pmatrix} = H^{-1} \begin{pmatrix} -d \\ -e \end{pmatrix}$$
**Strict Physical Constraints:**
- $a < 0$, $b < 0$ and $\det(H) = 4ab - c^2 > 10^{-4}$ (negative-definite Hessian for a true local maximum).
- $|x^*| \le 0.35^\circ$ and $|y^*| \le 0.35^\circ$ (subgrid displacement must not exceed grid cell boundary).
- $|P(x^*, y^*) - P_{\text{disc}}| < 3.0\text{ hPa}$ (reject non-physical divergences).

### 3.3 Differential Spherical Area Matrix
$$dA(\phi) = R_{\oplus}^2 \cdot \cos(\phi) \cdot \Delta\phi \cdot \Delta\lambda \quad [\text{km}^2]$$

### 3.4 Thermodynamic Dome Metrics: Area, Integrated Mass & Effective Height
- **Areal Coverage ($A_{1020}$):**
  $$A_{1020} = \sum_{\substack{i,j \in \text{Ocean} \\ P_{i,j} \ge 1020}} dA_{i,j} \times 10^{-6} \quad [\text{M km}^2]$$
- **Integrated Mass / Baric Volume ($I_{\text{vol}}$):**
  $$I_{\text{vol}} = \sum_{\substack{i,j \in \text{Ocean} \\ P_{i,j} \ge P_{\text{base}}}} (P_{i,j} - P_{\text{base}}) \cdot dA_{i,j} \times 10^{-6} \quad [\text{hPa}\cdot\text{M km}^2]$$
  *Adaptive Singularity Rule:* $P_{\text{base}} = 1020.0\text{ hPa}$ when $P_{\max} \ge 1020.0$; if $P_{\max} < 1020.0$ (May seasonal minimum), $P_{\text{base}} = P_{\max} - 4.0\text{ hPa}$ to prevent division by zero ($0/0 \to \text{NaN}$).
- **Effective Thickness ($\bar{H}$):**
  $$\bar{H} = \frac{I_{\text{vol}}}{A_{1020}} \quad [\text{hPa}]$$

### 3.5 Adaptive Baric Centroid
Center of mass of the oceanic atmospheric dome:
$$\phi_{\text{cent}} = \frac{\sum W_{i,j} \cdot \phi_i}{\sum W_{i,j}}, \quad \lambda_{\text{cent}} = \frac{\sum W_{i,j} \cdot \lambda_j}{\sum W_{i,j}}, \quad \text{where } W_{i,j} = \max(0, P_{i,j} - P_{\text{base}}) \cdot dA_{i,j}$$

### 3.6 Geodesic Decoupling Vector & Nautical Azimuth
Connecting Core $(\phi_1, \lambda_1)$ to Centroid $(\phi_2, \lambda_2)$:
- **Orthodromic Distance ($D_{nc}$):** Haversine formula over $R_{\oplus} = 6371.0088\text{ km}$.
- **Nautical Bearing ($\theta \in [0^\circ, 360^\circ[$):**
  $$\theta = \text{atan2}(\sin\Delta\lambda \cdot \cos\phi_2, \; \cos\phi_1\sin\phi_2 - \sin\phi_1\cos\phi_2\cos\Delta\lambda) \pmod{360^\circ}$$
- **Synoptic Regimes:**
  - $D_{nc} < 300\text{ km}$: Symmetric Concentric (mature, open-ocean anticyclone).
  - $D_{nc} \ge 300\text{ km}$ and $\theta \in [30^\circ, 120^\circ]$: Coastal Ridge / Compresión (accelerated southerly coastal wind jets).
  - $D_{nc} \ge 300\text{ km}$ and $\theta \in [120^\circ, 210^\circ]$: Patagonian Blocking / Migración Austral (poleward high pressure invasion into fjords).

### 3.7 Normalized Ocean Convolution (Wall Effect Suppression)
$$P_{\text{smooth}} = \frac{G_\sigma * (P \cdot M)}{G_\sigma * M}$$
Where $M$ is the boolean ocean mask ($1$ in Pacific ocean, $0$ on land or east of $-70.5^\circ\text{W}$). Prevents Andean orographic high pressures from leaking into coastal waters.

---

## 4. Repository Architecture & Key Files

```
dashboard-anticiclon-pacifico/
├── pipeline/
│   ├── paths.py                     # Centralized PROJECT_ROOT and resolve_project_path()
│   ├── file_utils.py                # is_nonempty_file(), temp_path_for() atomic utilities
│   ├── spatial_geometry.py          # Natural Earth 10m shapefile, dA matrix, normalized convolution
│   ├── calculate_aps_metrics.py     # Main engine V5.3 (Subgrid peak, Dynamic Pair, WMO climatology)
│   ├── download_era5.py             # Copernicus CDS API automated NetCDF downloader
│   ├── download_gfs_forecast.py     # NOAA GFS NOMADS 7-day forecast downloader (GRIB2)
│   ├── download_ncep_reanalysis.py  # NOAA PSL NCEP/NCAR Reanalysis 1 downloader
│   └── requirements.txt             # Python scientific dependencies
├── web/
│   ├── index.html                   # Dashboard UI (5 KPI cards, Leaflet maps, Plotly charts)
│   ├── styles/main.css              # Deep Abyss scientific design system
│   ├── js/
│   │   ├── main.js                  # App orchestrator, timeline slider, KaTeX modal controller
│   │   ├── maps.js                  # Leaflet maps, Marching Squares 2D, Dynamic Pair markers
│   │   ├── charts.js                # Plotly 2D Phase Space chart (Lon vs Lat) + 4 time-series panels
│   │   └── model_selector.js        # Drawer model selector (ERA5, Climatology, GFS)
│   └── data/
│       ├── latest_aps_data.json     # Primary web payload (~1.6 MB)
│       ├── era5_daily_aps_metrics.csv # Daily metrics archive
│       └── aps_multimodel_metrics_lofa.csv # Multimodel dataset for researcher download
├── tests/
│   └── test_aps_physics.py          # Geophysical unit tests (6 rigorous physics checks)
├── docs/
│   └── METODOLOGIA.md               # Scientific reference documentation
└── README.md                        # Quickstart, citations, and reproducibility guide
```

---

## 5. Web Data Contracts & Statistical Skill Formulas

### 5.1 Validation Metrics (Computed on Demand)
- **Root Mean Square Error (RMSE):**
  $$\text{RMSE} = \sqrt{\frac{1}{N}\sum_{i=1}^N (P_{\text{model}, i} - P_{\text{ref}, i})^2}$$
- **Mean Bias Error (BIAS):**
  $$\text{BIAS} = \frac{1}{N}\sum_{i=1}^N (P_{\text{model}, i} - P_{\text{ref}, i})$$
- **Pearson Correlation Coefficient ($r$):**
  $$r = \frac{\sum (P_m - \bar{P}_m)(P_r - \bar{P}_r)}{\sqrt{\sum (P_m - \bar{P}_m)^2 \sum (P_r - \bar{P}_r)^2}}$$
- **Willmott Index of Agreement ($d$):**
  $$d = 1 - \frac{\sum_{i=1}^N (P_{\text{model}, i} - P_{\text{ref}, i})^2}{\sum_{i=1}^N \left(|P_{\text{model}, i} - \bar{P}_{\text{ref}}| + |P_{\text{ref}, i} - \bar{P}_{\text{ref}}|\right)^2}$$

### 5.2 `web/data/latest_aps_data.json` Schema
```json
{
  "metadata": { "project": "...", "institution": "LOFA - UACh", "version": "5.3", ... },
  "models": {
    "ERA5 Reanálisis": {
      "id": "era5_reanalisis",
      "dates": ["YYYY-MM-DD", ...],
      "p_max_fit": [1026.5, ...],
      "lat_core": [-33.5, ...],
      "lon_core": [-92.1, ...],
      "lat_centroid": [-34.2, ...],
      "lon_centroid": [-90.8, ...],
      "area_1020": [4.21, ...],
      "vol_integral": [15.3, ...],
      "h_eff": [3.63, ...],
      "dist_decoupling_km": [145.2, ...],
      "azimuth_deg": [124.5, ...],
      "p_patagonia": [1016.4, ...],
      "latest": { ... }
    },
    "Climatología Normal OMM": { ... },
    "NOAA GFS Pronóstico": { "is_forecast": true, ... }
  }
}
```

Los campos 2D ya **no** viajan en este payload. Cada rejilla real se publica
como un documento independiente en `web/data/grids/<model_id>/<fecha>.json`,
registrado en `web/data/grids/manifest.json` y cargado de forma diferida por
`web/js/grid_store.js`. El productor diario es
`pipeline/export_historical_grids.py`: publica un documento por día real del
NetCDF, sin interpolar ni sintetizar fechas ausentes.

---

## 6. Known Gotchas & Critical Traps

1. **GitHub Actions `.github/workflows/update_data.yml` Status:**  
   Currently in active redesign to implement the unattended daily GFS cron. It historically failed because it referenced an obsolete `--generate-sample` flag and runner environments lacked local NetCDFs. Do not attempt to run or depend on the legacy workflow until the update plan is applied.
2. **Offline Testing & Natural Earth Shapefiles:**  
   `spatial_geometry.py` auto-downloads `ne_10m_land.zip` from Amazon S3 on first run if missing. In strict airgapped/offline sandboxes, `data/shapefiles/` must be pre-populated or tests will fail on network timeout.
3. **Historical Maps in Frontend (`maps.js`):**  
   To preserve instantaneous web loading (< 2 MB total bundle), the payload transmits no 2D grid: each real field is lazy-loaded from `web/data/grids/<model_id>/<fecha>.json`. `maps.js` only draws isobars when `model_id` and `date` match exactly; otherwise it shows `Campo 2D no disponible para esta fecha/modelo`. Never restore the old parametric Gaussian field: that would violate directive 2.3. Run `pipeline/export_historical_grids.py` to publish real daily fields from the local NetCDFs.
4. **Test Skipping Warning:**  
   `test_aps_physics.py` skips `test_coastal_zero_land_centers` if `web/data/aps_multimodel_metrics_lofa.csv` is missing. Ensure the pipeline has produced the CSV before declaring a 100% test pass.

---

## 7. Developer & Agent Verification Protocol

Before submitting or committing any change, run this verification sequence:

```bash
# 1. Run geophysical physics unit tests (MUST pass 6/6 tests)
./venv/bin/python -m unittest discover -s tests -v

# 2. Test pipeline metric calculations
./venv/bin/python pipeline/calculate_aps_metrics.py --start-year 1994 --end-year 1994

# 3. Verify CLI interfaces and help flags
./venv/bin/python pipeline/download_era5.py --help
./venv/bin/python pipeline/download_gfs_forecast.py --help
./venv/bin/python pipeline/download_ncep_reanalysis.py --help

# 4. Preview static web client locally
python3 -m http.server 8000 --directory web
# Open: http://localhost:8000
```
