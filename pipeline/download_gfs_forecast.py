#!/usr/bin/env python3
"""
download_gfs_forecast.py
Descargador automatizado de pronósticos operativos a 7 días de NOAA GFS (Global Forecast System)
para el Anticiclón del Pacífico Sur (APS).
Sin cuentas, sin API keys (Acceso público directo a NOAA NOMADS).
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3
"""

import os
import sys
import re
import json
import argparse
import datetime
import requests
import numpy as np

# Dominio geográfico del APS extendido (captura Chiloé, Golfo de Penas, Drake y Patagonia)
LAT_NORTH = -10
LAT_SOUTH = -56
LON_WEST = -130
LON_EAST = -65

NOMADS_BASE = "https://nomads.ncep.noaa.gov"


def get_latest_gfs_cycle():
    """
    Identifica la fecha y ciclo (00, 06, 12, 18z) más reciente y disponible en NOAA NOMADS.
    """
    print("[INFO] Consultando ciclos disponibles en NOAA NOMADS...")
    try:
        r = requests.get(f"{NOMADS_BASE}/pub/data/nccf/com/gfs/prod/", timeout=10)
        dates = re.findall(r'href="(gfs\.\d{8})/"', r.text)
        if not dates:
            raise ValueError("No se encontraron carpetas de GFS en el servidor.")
        
        latest_date_folder = dates[-1].replace("gfs.", "")
        # Verificar ciclos de hoy o ayer
        cycles = ["18", "12", "06", "00"]
        for c in cycles:
            check_url = f"{NOMADS_BASE}/cgi-bin/filter_gfs_0p25.pl?dir=%2Fgfs.{latest_date_folder}%2F{c}%2Fatmos"
            res = requests.get(check_url, timeout=5)
            if res.status_code == 200 and "gfs.t" in res.text:
                return latest_date_folder, c
        
        # Si la fecha más reciente aún no tiene subidas completas, probar con la anterior
        prev_date_folder = dates[-2].replace("gfs.", "")
        return prev_date_folder, "00"
    except Exception as e:
        print(f"[AVISO] Error consultando índice de ciclos ({e}). Usando ciclo estimado.")
        yesterday = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).strftime("%Y%m%d")
        return yesterday, "00"


def fetch_gfs_forecast_steps(date_str, cycle_str, output_dir):
    """
    Descarga los pasos de pronóstico de 0 a 168 horas (7 días) para la variable PRMSL.
    """
    try:
        import xarray as xr
    except ImportError:
        print("[ERROR] Se requiere xarray y cfgrib. Ejecuta: pip install xarray cfgrib eccodes")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
    # Pasos de pronóstico: cada 24 horas hasta el día 7 (168 horas)
    forecast_hours = [0, 24, 48, 72, 96, 120, 144, 168]
    
    forecast_results = {
        "dates": [],
        "pressure_psa": [],
        "lat": [],
        "lon": []
    }

    base_time = datetime.datetime.strptime(f"{date_str} {cycle_str}", "%Y%m%d %H")
    print(f"\n📡 [NOAA GFS] Descargando pronóstico operativo ciclo {date_str} {cycle_str}Z...")

    for f_step in forecast_hours:
        f_str = f"{f_step:03d}"
        target_grib = os.path.join(output_dir, f"gfs_{date_str}_{cycle_str}z_f{f_str}.grib2")
        valid_date = (base_time + datetime.timedelta(hours=f_step)).strftime("%Y-%m-%d")

        url = (
            f"{NOMADS_BASE}/cgi-bin/filter_gfs_0p25.pl"
            f"?dir=%2Fgfs.{date_str}%2F{cycle_str}%2Fatmos"
            f"&file=gfs.t{cycle_str}z.pgrb2.0p25.f{f_str}"
            f"&var_PRMSL=on"
            f"&subregion=on"
            f"&toplat={LAT_NORTH}&bottomlat={LAT_SOUTH}&leftlon={LON_WEST}&rightlon={LON_EAST}"
        )

        # Descargar si no existe
        if not os.path.exists(target_grib):
            try:
                res = requests.get(url, timeout=20)
                if res.status_code == 200 and len(res.content) > 1000:
                    with open(target_grib, "wb") as f:
                        f.write(res.content)
                else:
                    print(f"⚠️  Paso f{f_str} no disponible (código {res.status_code}).")
                    continue
            except Exception as e:
                print(f"⚠️  Error de red descargando f{f_str}: {e}")
                continue

        # Procesar GRIB con xarray y detectar centro del APS
        try:
            with xr.open_dataset(target_grib, engine="cfgrib") as ds:
                p_var = ds["prmsl"] / 100.0 # Pascales a hPa
                lats = ds["latitude"].values
                lons = ds["longitude"].values

                # Convertir longitudes si vienen en rango 0-360
                if np.any(lons > 180):
                    lons = np.where(lons > 180, lons - 360, lons)

                grid = p_var.values
                max_idx = np.unravel_index(np.nanargmax(grid), grid.shape)
                
                max_p = float(round(grid[max_idx], 2))
                lat_c = float(round(lats[max_idx[0]], 2))
                lon_c = float(round(lons[max_idx[1]], 2))

                forecast_results["dates"].append(valid_date)
                forecast_results["pressure_psa"].append(max_p)
                forecast_results["lat"].append(lat_c)
                forecast_results["lon"].append(lon_c)

                print(f"  + Pronóstico +{f_step}h ({valid_date}): PSA={max_p} hPa, Centro: {lat_c}°S, {lon_c}°W")

        except Exception as e:
            print(f"⚠️  Error procesando GRIB f{f_str}: {e}")

    return forecast_results


def main():
    parser = argparse.ArgumentParser(description="Descargador de pronóstico NOAA GFS para el APS")
    parser.add_argument("--output-json", type=str, default="data/processed/gfs_forecast_aps.json", help="Ruta del JSON con el pronóstico")
    parser.add_argument("--temp-dir", type=str, default="data/temp/gfs", help="Directorio temporal para archivos GRIB2")
    
    args = parser.parse_args()

    date_str, cycle_str = get_latest_gfs_cycle()
    forecast = fetch_gfs_forecast_steps(date_str, cycle_str, args.temp_dir)

    if forecast["dates"]:
        os.makedirs(os.path.dirname(args.output_json), exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump({
                "model_id": "noaa_gfs_forecast",
                "model_name": "NOAA GFS (Pronóstico Operativo 7 Días)",
                "cycle": f"{date_str} {cycle_str}Z",
                "forecast": forecast
            }, f, indent=2)
        print(f"\n✅ [ÉXITO] Pronóstico GFS a 7 días guardado en: {args.output_json}")
    else:
        print("[ERROR] No se pudo compilar el pronóstico de GFS.")


if __name__ == "__main__":
    main()
