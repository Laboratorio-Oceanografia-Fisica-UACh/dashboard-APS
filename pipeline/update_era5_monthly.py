#!/usr/bin/env python3
"""
Actualización mensual del reanálisis ERA5 desde Copernicus CDS.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3

Fase 4 del plan: descarga el mes anterior de presión media a nivel del mar
(24 horas diarias), calcula las métricas V5.3 con el motor común, hace upsert
por fecha en la caché operativa y actualiza latest_spatial_grid.json.

El flujo diario/mensual no depende del NAS: los NetCDF crudos son solo la
entrada de este script y la caché CSV es la fuente de verdad operativa.
"""

import argparse
import calendar
import datetime
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from pipeline.aps_metrics import (
    TRACK_LAT_NORTH,
    TRACK_LAT_SOUTH,
    TRACK_LON_WEST,
    TRACK_LON_EAST,
    compute_daily_aps_metrics,
)
from pipeline.file_utils import (
    atomic_csv_dump,
    atomic_json_dump,
    is_nonempty_file,
    temp_path_for,
)
from pipeline.paths import resolve_project_path
from pipeline.spatial_geometry import (
    compute_cell_areas_km2,
    download_and_load_natural_earth_10m,
    generate_ocean_mask_10m,
)

# Dominio de descarga CDS en formato [norte, oeste, sur, este].
CDS_AREA = [-10.0, -130.0, -56.0, -65.0]
CDS_DATASET = "reanalysis-era5-single-levels"
CDS_VARIABLE = "mean_sea_level_pressure"
CDS_HOURS = [f"{hour:02d}:00" for hour in range(24)]
WEB_GRID_STRIDE = 2


def previous_month(today=None):
    """
    Devuelve (año, mes) del mes calendario inmediatamente anterior.
    """
    today = today or datetime.date.today()
    first_of_month = today.replace(day=1)
    previous = first_of_month - datetime.timedelta(days=1)
    return previous.year, previous.month


def _build_cds_request(year, month, legacy=False):
    """
    Construye el request de Copernicus CDS para un mes completo cada 24 h.

    Se usa el formato moderno (data_format/download_format) y se deja una
    variante heredada (format) para instalaciones antiguas de CDS.
    """
    days_in_month = calendar.monthrange(year, month)[1]
    request = {
        "product_type": ["reanalysis"] if not legacy else "reanalysis",
        "variable": [CDS_VARIABLE] if not legacy else CDS_VARIABLE,
        "year": [f"{year:04d}"] if not legacy else f"{year:04d}",
        "month": [f"{month:02d}"] if not legacy else f"{month:02d}",
        "day": [f"{day:02d}" for day in range(1, days_in_month + 1)],
        "time": CDS_HOURS,
        "area": CDS_AREA,
    }
    if legacy:
        request["format"] = "netcdf"
    else:
        request["data_format"] = "netcdf"
        request["download_format"] = "unarchived"
    return request


def download_month(year, month, target_path, cds_url=None, cds_key=None,
                   force=False, timeout=600):
    """
    Descarga el mes solicitado a target_path con escritura atómica.
    Reutiliza el archivo si ya existe y no se fuerza la descarga.
    """
    target_path = Path(target_path)
    if is_nonempty_file(target_path) and not force:
        print(f"📦 [ERA5] Reutilizando descarga existente: {target_path}")
        return target_path

    try:
        import cdsapi
    except ImportError:
        print(
            "[ERROR] cdsapi no está instalado. Ejecuta: "
            "pip install -r pipeline/requirements.txt"
        )
        raise SystemExit(1)

    url = cds_url or os.environ.get("CDSAPI_URL")
    key = cds_key or os.environ.get("CDSAPI_KEY")
    if not url or not key:
        print(
            "[ERROR] Faltan CDSAPI_URL y CDSAPI_KEY. Configúralos como variables "
            "de entorno o mediante --cds-url/--cds-key."
        )
        raise SystemExit(1)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = temp_path_for(target_path)

    print(f"📡 [ERA5] Descargando {year}-{month:02d} desde Copernicus CDS...")
    client = cdsapi.Client(url=url, key=key, timeout=timeout)

    last_error = None
    for legacy in (False, True):
        request = _build_cds_request(year, month, legacy=legacy)
        try:
            client.retrieve(CDS_DATASET, request, str(temp_path))
            os.replace(temp_path, target_path)
            last_error = None
            break
        except Exception as error:
            last_error = error
            if temp_path.exists():
                temp_path.unlink()
            if not legacy:
                print(
                    "⚠️  El CDS rechazó el formato moderno; reintentando con "
                    "el formato heredado..."
                )

    if last_error is not None:
        raise last_error

    print(f"✅ [ERA5] Descarga mensual guardada en: {target_path}")
    return target_path


def _daily_frames_from_netcdf(nc_path, land_union):
    """
    Abre el NetCDF mensual, recorta al dominio APS y calcula métricas diarias.
    """
    import xarray as xr

    rows = []
    grid_payload = None

    with xr.open_dataset(nc_path) as ds:
        time_dim = "valid_time" if "valid_time" in ds.dims else "time"
        sub = ds["msl"].sel(
            latitude=slice(TRACK_LAT_NORTH, TRACK_LAT_SOUTH),
            longitude=slice(TRACK_LON_WEST, TRACK_LON_EAST),
        )
        daily = (sub / 100.0).resample({time_dim: "1D"}).mean(dim=time_dim).compute()

        lats = sub["latitude"].values
        lons = sub["longitude"].values
        time_values = daily[time_dim].values

        cell_areas = compute_cell_areas_km2(lats, lons)
        ocean_mask = generate_ocean_mask_10m(lats, lons, land_union)

        for index, timestamp in enumerate(time_values):
            date_str = str(timestamp)[:10]
            grid = daily[index].values.copy()
            metrics = compute_daily_aps_metrics(
                grid, lats, lons, date=date_str,
                land_union=land_union, cell_areas=cell_areas,
                ocean_mask=ocean_mask, sigma=1.0,
            )
            if metrics is None:
                print(f"⚠️  Sin puntos oceánicos válidos para {date_str}; se omite.")
                continue

            dt = pd.to_datetime(date_str)
            rows.append({
                "date": date_str,
                "year": dt.year,
                "month": dt.month,
                "day": dt.day,
                "day_of_year": dt.dayofyear,
                **{key: metrics[key] for key in [
                    "p_max_fit", "lat_core", "lon_core", "lat_centroid",
                    "lon_centroid", "area_1020", "vol_integral", "h_eff",
                    "dist_decoupling_km", "azimuth_deg", "p_patagonia",
                ]},
            })

        if time_values.size > 0:
            last_grid = daily.isel({time_dim: -1})
            sampled = last_grid.isel(
                latitude=slice(None, None, WEB_GRID_STRIDE),
                longitude=slice(None, None, WEB_GRID_STRIDE),
            ).compute()
            sampled_values = sampled.values
            mean_value = float(np.nanmean(sampled_values))
            grid_payload = {
                "date": str(time_values[-1])[:10],
                "lats": [float(round(value, 2)) for value in sampled["latitude"].values],
                "lons": [float(round(value, 2)) for value in sampled["longitude"].values],
                "current_slp": [
                    [float(round(value, 2)) if np.isfinite(value) else None for value in row]
                    for row in sampled_values
                ],
                "current_anomaly": [
                    [float(round(value - mean_value, 2)) if np.isfinite(value) else None for value in row]
                    for row in sampled_values
                ],
            }

    return rows, grid_payload


def upsert_cache(cache_path, new_rows):
    """
    Inserta o reemplaza por fecha las filas nuevas en la caché operativa.
    """
    cache_path = Path(cache_path)
    new_frame = pd.DataFrame(new_rows)
    if new_frame.empty:
        raise ValueError("No hay filas nuevas para insertar en la caché.")

    new_frame = new_frame.drop_duplicates(subset=["date"]).sort_values("date")
    if cache_path.exists():
        existing = pd.read_csv(cache_path)
        existing = existing[~existing["date"].isin(new_frame["date"])]
        combined = pd.concat([existing, new_frame], ignore_index=True)
    else:
        combined = new_frame

    combined = combined.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    atomic_csv_dump(combined, cache_path, index=False)
    print(
        f"✅ [CACHÉ] {len(new_frame)} días insertados/actualizados. "
        f"Total: {len(combined)} días en {cache_path}"
    )
    return combined


def main():
    parser = argparse.ArgumentParser(
        description="Actualización mensual de ERA5 desde Copernicus CDS (Fase 4)."
    )
    parser.add_argument("--year", type=int, default=None,
                        help="Año del mes a descargar (por defecto el mes anterior).")
    parser.add_argument("--month", type=int, default=None,
                        help="Mes a descargar 1-12 (por defecto el mes anterior).")
    parser.add_argument("--raw-dir", type=str,
                        default="data/raw/mean_sea_level_pressure",
                        help="Directorio para el NetCDF mensual descargado.")
    parser.add_argument("--cache-csv", type=str,
                        default="data/processed/era5_daily_aps_metrics.csv",
                        help="Caché diaria a actualizar por upsert.")
    parser.add_argument("--spatial-grid", type=str,
                        default="data/processed/latest_spatial_grid.json",
                        help="JSON de la rejilla espacial más reciente.")
    parser.add_argument("--cds-url", type=str, default=None,
                        help="URL de CDS (por defecto CDSAPI_URL).")
    parser.add_argument("--cds-key", type=str, default=None,
                        help="Clave de CDS (por defecto CDSAPI_KEY).")
    parser.add_argument("--timeout", type=int, default=600,
                        help="Timeout de descarga CDS en segundos.")
    parser.add_argument("--force", action="store_true",
                        help="Fuerza una nueva descarga aunque exista el NetCDF.")
    args = parser.parse_args()

    if args.year is None or args.month is None:
        default_year, default_month = previous_month()
        year = args.year if args.year is not None else default_year
        month = args.month if args.month is not None else default_month
    else:
        year, month = args.year, args.month

    if not (1 <= month <= 12):
        print("[ERROR] El mes debe estar entre 1 y 12.")
        sys.exit(1)

    raw_dir = resolve_project_path(args.raw_dir)
    cache_path = resolve_project_path(args.cache_csv)
    spatial_grid_path = resolve_project_path(args.spatial_grid)
    target_nc = raw_dir / f"era5_mslp_pacifico_{year}_{month:02d}.nc"

    nc_path = download_month(
        year, month, target_nc,
        cds_url=args.cds_url, cds_key=args.cds_key,
        force=args.force, timeout=args.timeout,
    )

    land_union = download_and_load_natural_earth_10m()
    rows, grid_payload = _daily_frames_from_netcdf(nc_path, land_union)

    if not rows:
        print("[ERROR] El NetCDF descargado no produjo métricas diarias.")
        sys.exit(1)

    upsert_cache(cache_path, rows)

    if grid_payload is not None:
        atomic_json_dump(grid_payload, spatial_grid_path, indent=2, ensure_ascii=False)
        print(f"✅ [REJILLA] latest_spatial_grid.json actualizado: {spatial_grid_path}")
    else:
        print("⚠️  No se pudo construir la rejilla espacial del mes descargado.")


if __name__ == "__main__":
    main()
