#!/usr/bin/env python3
"""
download_ncep_reanalysis.py
Descargador automatizado de datos de Presión al Nivel del Mar (SLP) del reanálisis histórico
NCEP/NCAR Reanalysis 1 (NOAA PSL / NCEP).
Acceso público directo sin necesidad de credenciales ni API keys.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3

Versión 4.0:
- Alineado con la ventana subtropical de subsidencia del APS (-20°S a -42°S).
- Máscara oceánica estricta para evitar cualquier punto sobre la cordillera o la Patagonia.
"""

import os
import sys
import glob
import argparse
import datetime
import requests
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter

# Dominio geográfico extendido del APS (LOFA UACh)
LAT_NORTH = -10.0
LAT_SOUTH = -56.0
LON_WEST = -130.0
LON_EAST = -65.0

# Ventana oceánica subtropical de seguimiento del núcleo
TRACK_LAT_NORTH = -20.0
TRACK_LAT_SOUTH = -42.0
TRACK_LON_WEST = -115.0
TRACK_LON_EAST = -70.0

NOAA_PSL_BASE_URL = "https://downloads.psl.noaa.gov/Datasets/ncep.reanalysis/surface"


def get_pacific_coastline_lon(lat):
    """
    Límite costero sudamericano para garantizar 100% detección marina en NCEP.
    """
    ref_lats = np.array([
        -10.0, -12.0, -14.0, -16.0, -18.0,
        -20.0, -24.0, -28.0, -30.0, -33.0,
        -35.0, -37.0, -39.0, -41.0, -43.0,
        -45.0, -46.5, -48.0, -50.0, -52.0,
        -54.0, -56.0
    ])
    ref_lons = np.array([
        -78.2, -77.2, -76.2, -74.0, -71.2,
        -70.15, -70.4, -71.0, -71.35, -71.65,
        -72.3, -73.5, -73.4, -73.8, -74.2,
        -74.8, -75.7, -75.3, -75.4, -75.3,
        -73.5, -68.5
    ])
    return np.interp(lat, ref_lats[::-1], ref_lons[::-1])


def download_ncep_year(year, output_dir):
    """
    Descarga el archivo NetCDF anual de Sea Level Pressure de NCEP/NCAR desde NOAA PSL.
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = f"slp.{year}.nc"
    target_path = os.path.join(output_dir, filename)

    if os.path.exists(target_path):
        print(f"⏩ [SALTANDO] {filename} ya existe en {output_dir}")
        return target_path

    url = f"{NOAA_PSL_BASE_URL}/{filename}"
    print(f"\n📡 [NOAA NCEP/NCAR] Descargando año {year} desde NOAA PSL...")
    print(f"   URL: {url}")

    try:
        res = requests.get(url, stream=True, timeout=60)
        if res.status_code == 200:
            total_bytes = 0
            with open(target_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        total_bytes += len(chunk)
            print(f"✅ [ÉXITO] {filename} descargado ({total_bytes / (1024*1024):.1f} MB): {target_path}")
            return target_path
        else:
            print(f"⚠️ [AVISO] Año {year} no disponible en NOAA PSL (código HTTP {res.status_code}).")
            return None
    except Exception as e:
        print(f"❌ [ERROR] Falló la descarga de {year}: {e}")
        return None


def process_ncep_files(input_dir, output_csv):
    """
    Procesa los archivos NetCDF de NCEP/NCAR y extrae la serie diaria del núcleo del APS
    confortada con la máscara marina y ventana subtropical.
    """
    try:
        import xarray as xr
    except ImportError:
        print("[ERROR] Falta instalar xarray. Ejecuta: pip install xarray netcdf4")
        sys.exit(1)

    nc_files = glob.glob(os.path.join(input_dir, "slp.*.nc"))
    nc_files.sort()

    if not nc_files:
        print(f"[AVISO] No se encontraron archivos slp.*.nc en {input_dir}")
        return None

    rows = []
    print(f"\n⚙️  Procesando {len(nc_files)} archivos NetCDF de NCEP/NCAR...")

    for fpath in nc_files:
        fname = os.path.basename(fpath)
        try:
            with xr.open_dataset(fpath) as ds:
                var_name = "slp" if "slp" in ds else "msl"
                slp_da = ds[var_name]

                # Convertir longitudes si vienen en 0-360
                lons = ds["lon"].values
                if np.any(lons > 180):
                    ds = ds.assign_coords(lon=(((ds["lon"] + 180) % 360) - 180)).sortby("lon")
                    slp_da = ds[var_name]

                # Recorte al dominio oceánico subtropical
                lats = ds["lat"].values
                lat_mask = (lats <= TRACK_LAT_NORTH) & (lats >= TRACK_LAT_SOUTH)
                lon_mask = (ds["lon"].values >= TRACK_LON_WEST) & (ds["lon"].values <= TRACK_LON_EAST)

                # Subconjunto
                sub = (slp_da / 100.0).sel(lat=slice(TRACK_LAT_NORTH, TRACK_LAT_SOUTH) if lats[0] > lats[-1] else slice(TRACK_LAT_SOUTH, TRACK_LAT_NORTH),
                                          lon=slice(TRACK_LON_WEST, TRACK_LON_EAST))

                sub_lats = sub["lat"].values
                sub_lons = sub["lon"].values
                time_dim = "time"
                times = sub[time_dim].values

                lon_grid, lat_grid = np.meshgrid(sub_lons, sub_lats)
                coast_limits = get_pacific_coastline_lon(sub_lats)[:, None]
                ocean_mask = (lon_grid < coast_limits)

                for t_idx, t in enumerate(times):
                    date_str = str(t)[:10]
                    grid_2d = sub.isel({time_dim: t_idx}).values.copy()
                    grid_2d[~ocean_mask] = np.nan

                    # Suavizado leve
                    v = np.nan_to_num(grid_2d, nan=1010.0)
                    smoothed = gaussian_filter(v, sigma=0.8)
                    smoothed[~ocean_mask] = np.nan

                    max_idx = np.unravel_index(np.nanargmax(smoothed), smoothed.shape)
                    max_p = float(round(grid_2d[max_idx], 2))
                    lat_c = float(round(sub_lats[max_idx[0]], 2))
                    lon_c = float(round(sub_lons[max_idx[1]], 2))

                    dt = pd.to_datetime(date_str)
                    rows.append({
                        "date": date_str,
                        "year": dt.year,
                        "month": dt.month,
                        "day": dt.day,
                        "pressure_psa": max_p,
                        "lat": lat_c,
                        "lon": lon_c
                    })

        except Exception as e:
            print(f"⚠️  Error procesando {fname}: {e}")

    if rows:
        df = pd.DataFrame(rows).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
        os.makedirs(os.path.dirname(output_csv), exist_ok=True)
        df.to_csv(output_csv, index=False)
        print(f"✅ [ÉXITO] Serie histórica de NCEP/NCAR procesada ({len(df)} días) en: {output_csv}")
        return df
    return None


def main():
    parser = argparse.ArgumentParser(description="Descargador de Reanálisis NCEP/NCAR (NOAA PSL) para el APS")
    parser.add_argument("--start-year", type=int, default=1948, help="Año inicial (mínimo: 1948)")
    parser.add_argument("--end-year", type=int, default=1972, help="Año final homólogo")
    parser.add_argument("--years", nargs="+", help="Años específicos (ej: --years 2022 2023)")
    parser.add_argument("--output-dir", type=str, default="data/raw/ncep_reanalysis", help="Directorio de destino")
    parser.add_argument("--output-csv", type=str, default="data/processed/ncep_daily_aps_metrics.csv", help="Ruta del CSV procesado")
    parser.add_argument("--process-only", action="store_true", help="Solo procesar archivos locales existentes sin descargar")

    args = parser.parse_args()

    if not args.process_only:
        years_to_get = [int(y) for y in args.years] if args.years else list(range(args.start_year, args.end_year + 1))
        print(f"📋 Descargando {len(years_to_get)} años de NCEP/NCAR ({years_to_get[0]} a {years_to_get[-1]})...")
        for y in years_to_get:
            download_ncep_year(y, args.output_dir)

    process_ncep_files(args.output_dir, args.output_csv)


if __name__ == "__main__":
    main()
