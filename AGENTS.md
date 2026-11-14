# AGENTS.md

Static dashboard (`web/`) plus an offline Python data pipeline (`pipeline/`). No Node, package manager, build step, lint, formatter, or typecheck is configured. Docs, code comments, and UI text are Spanish; keep that convention.

## Commands

```bash
python3 -m venv venv
./venv/bin/pip install -r pipeline/requirements.txt

# Tests (unittest, not pytest)
./venv/bin/python -m unittest discover -s tests -v
./venv/bin/python -m unittest tests.test_aps_physics.TestAPSPhysics.test_may_collapse_continuity -v

# Pipeline (run from repo root)
./venv/bin/python pipeline/calculate_aps_metrics.py
./venv/bin/python pipeline/download_gfs_forecast.py
./venv/bin/python pipeline/download_era5.py --years 2024
./venv/bin/python pipeline/download_ncep_reanalysis.py --process-only

# Preview dashboard
python3 -m http.server 8000 --directory web
```

## Data flow and layout

- `calculate_aps_metrics.py` only reads `data/raw/mean_sea_level_pressure/era5_mslp_pacifico_<YYYY>.nc`. It exits with code 1 if none exist; there is no sample/demo mode.
- It writes `data/processed/latest_aps_data.json`, `data/processed/era5_daily_aps_metrics.csv`, and copies to `web/data/latest_aps_data.json` plus both `web/data/*.csv`.
- The browser reads only `web/data/` (`latest_aps_data.json`, `aps_multimodel_metrics_lofa.csv`, `era5_daily_aps_metrics.csv`). The deploy workflow publishes `web/` as the site root.
- Optional GFS forecast: `download_gfs_forecast.py` writes `data/processed/gfs_forecast_aps.json`; the main pipeline automatically includes it if present.
- Natural Earth 10m shapefiles live in `data/shapefiles/` and are gitignored. `spatial_geometry.py` auto-downloads them, so a fresh offline clone makes tests/geometry fail.
- The APS tracking domain and WMO climatology are hardcoded in `calculate_aps_metrics.py`; `docs/METODOLOGIA.md` is the physics reference. Keep them synchronized if changing either.
- `data/raw/`, `data/temp/`, and binary weather files are intentionally untracked; never commit them.

## Gotchas

- Run pipeline scripts from the repository root: all input/output paths are relative to CWD.
- `.github/workflows/update_data.yml` still passes `--generate-sample`, which was removed from `calculate_aps_metrics.py`. That scheduled workflow currently fails; do not copy its invocation.
- `tests/test_aps_physics.py` skips the coastal-land check if `web/data/aps_multimodel_metrics_lofa.csv` is absent, so a "pass" can hide missing data validation.
- Frontend uses CDN Leaflet/Plotly/KaTeX; there is nothing to bundle or install.
