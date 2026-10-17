#!/usr/bin/env python3
"""
download_ncep_reanalysis.py
Descargador automatizado de datos de Presión al Nivel del Mar (SLP) del reanálisis histórico
NCEP/NCAR Reanalysis 1 (NOAA PSL / NCEP).
Acceso público directo sin necesidad de credenciales ni API keys.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3
"""

import os
import sys
import argparse
import datetime
import requests
import numpy as np
import pandas as pd

# Dominio geográfico extendido del APS (LOFA UACh)
LAT_NORTH = -10.0
LAT_SOUTH = -56.0
LON_WEST = -130.0
LON_EAST = -65.0

# Ventana oceánica de seguimiento del núcleo
TRACK_LAT_NORTH = -18.0
TRACK_LAT_SOUTH = -54.0
TRACK_LON_WEST = -125.0
TRACK_LON_EAST = -72.0

NOAA_PSL_BASE_URL = "https://downloads.psl.noaa.gov/Datasets/ncep.reanalysis/surface"


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
    Procesa los archivos NetCDF de NCEP/NCAR y extrae la serie diaria del núcleo del APS.
    """
    try:
        import xarray as xr
    except ImportError:
        print("[ERROR] Falta instalar xarray. Ejecuta: pip install xarray netcdf4")
        sys.exit(1)

    import glob
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
                # Variable de presión al nivel del mar (en Pascales)
                var_name = "slp" if "slp" in ds else "msl"
                slp_da = ds[var_name]

                # Convertir longitudes si vienen en 0-360
                lons = ds["lon"].values
                if np.any(lons > 180):
                    ds = ds.assign_coords(lon=(((ds["lon"] + 180) % 360) - 180)).sortby("lon")
                    slp_da = ds[var_name]

                # Recorte al dominio oceánico
                lats = ds["lat"].values
                lat_mask = (lats <= TRACK_LAT_NORTH) & (lats >= TRACK_LAT_SOUTH)
                lon_mask = (ds["lon"].values >= TRACK_LON_WEST) & (ds["lon"].values <= TRACK_LON_EAST)

                # Convertir Pascales a hPa
                sub = slp_da / 100.0

                time_dim = "time"
                times = sub[time_dim].values

                for t_idx, t in enumerate(times):
                    date_str = str(t)[:10]
                    grid_2d = sub.isel({time_dim: t_idx}).values

                    # Aplicar máscara oceánica
                    ocean_mask = np.outer(lat_mask, lon_mask)
                    masked_grid = np.where(ocean_mask, grid_2d, np.nan)

                    max_idx = np.unravel_index(np.nanargmax(masked_grid), masked_grid.shape)
                    max_p = float(round(masked_grid[max_idx], 2))
                    lat_c = float(round(lats[max_idx[0]], 2))
                    lon_c = float(round(ds["lon"].values[max_idx[1]], 2))

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
    parser.add_argument("--end-year", type=int, default=2024, help="Año final")
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
