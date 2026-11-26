#!/usr/bin/env python3
"""
Descargador automatizado de pronósticos operativos a 7 días de NOAA GFS
(Global Forecast System) para el Anticiclón del Pacífico Sur (APS).
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3

El dominio de descarga es amplio, pero el recorte y todas las métricas V5.3
se calculan estrictamente en [-48°S, -18°S] x [-120°W, -70°W], con la misma
física del motor común y la máscara Natural Earth 10m usada por ERA5.
"""

import argparse
import datetime
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import requests

# Asegurar importación de los módulos del pipeline
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
from pipeline.grid_export import (
    build_grid_document,
    export_grid_document,
    prune_model_grids,
)
from pipeline.paths import resolve_project_path
from pipeline.spatial_geometry import download_and_load_natural_earth_10m

# Dominio amplio de descarga GFS (recorte posterior al dominio ERA5)
LAT_NORTH = -10
LAT_SOUTH = -56
LON_WEST = -130
LON_EAST = -65

FORECAST_HOURS = [0, 24, 48, 72, 96, 120, 144, 168]
NOMADS_BASE = "https://nomads.ncep.noaa.gov"
REQUEST_TIMEOUT = 60
MAX_RETRIES = 3
BACKOFF_BASE = 2.0

FORECAST_FIELDS = [
    "dates",
    "forecast_hours",
    "p_max_fit",
    "lat_core",
    "lon_core",
    "lat_centroid",
    "lon_centroid",
    "area_1020",
    "vol_integral",
    "h_eff",
    "dist_decoupling_km",
    "azimuth_deg",
    "p_patagonia",
    "regime",
]

ARCHIVE_COLUMNS = ["cycle", "generated_at"] + FORECAST_FIELDS


def check_gfs_dependencies():
    """
    Verifica las dependencias necesarias para leer GRIB2 antes de consultar NOAA.
    """
    missing = [
        name for name in ("xarray", "cfgrib", "eccodes")
        if importlib.util.find_spec(name) is None
    ]
    if missing:
        print("\n" + "=" * 70)
        print("❌ [ERROR] Faltan dependencias para procesar GFS GRIB2: " + ", ".join(missing))
        print("=" * 70)
        print("Instala las dependencias con:")
        print("  pip install -r pipeline/requirements.txt")
        return False
    return True


def _request_with_retries(url, timeout=REQUEST_TIMEOUT, retries=MAX_RETRIES,
                          backoff=BACKOFF_BASE):
    """
    Realiza una petición HTTP con reintentos y retroceso exponencial.
    Retorna la respuesta si el código es 200, o None si se agotan los intentos.
    """
    for attempt in range(max(1, retries)):
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                return response
            print(
                f"⚠️  HTTP {response.status_code} en intento {attempt + 1}/{retries}: "
                f"{url[:120]}"
            )
        except requests.RequestException as error:
            print(f"⚠️  Error de red en intento {attempt + 1}/{retries}: {error}")
        if attempt < retries - 1:
            time.sleep(backoff * (2 ** attempt))
    return None


def _parse_forced_cycle(cycle_text):
    """
    Parsea un ciclo forzado 'YYYYMMDD HHZ' o 'YYYYMMDD HH' a (fecha, hora).
    """
    cleaned = cycle_text.strip().upper().replace("Z", "")
    match = re.match(r"^(\d{8})\s+(\d{1,2})$", cleaned)
    if not match:
        raise ValueError("El ciclo debe tener el formato 'YYYYMMDD HHZ' o 'YYYYMMDD HH'.")
    date_str = match.group(1)
    cycle_str = f"{int(match.group(2)):02d}"
    return date_str, cycle_str


def get_latest_gfs_cycle(timeout=REQUEST_TIMEOUT, retries=MAX_RETRIES):
    """
    Identifica la fecha y ciclo (00, 06, 12, 18Z) más reciente disponible
    en NOAA NOMADS.
    """
    print("[INFO] Consultando ciclos disponibles en NOAA NOMADS...")
    try:
        response = _request_with_retries(
            f"{NOMADS_BASE}/pub/data/nccf/com/gfs/prod/",
            timeout=timeout, retries=retries,
        )
        if response is None:
            raise ValueError("No se pudo consultar el índice de GFS.")

        dates = re.findall(r'href="(gfs\.\d{8})/"', response.text)
        if not dates:
            raise ValueError("No se encontraron carpetas de GFS en el servidor.")

        latest_date_folder = dates[-1].replace("gfs.", "")
        for cycle in ["18", "12", "06", "00"]:
            check_url = (
                f"{NOMADS_BASE}/cgi-bin/filter_gfs_0p25.pl"
                f"?dir=%2Fgfs.{latest_date_folder}%2F{cycle}%2Fatmos"
            )
            result = _request_with_retries(check_url, timeout=timeout, retries=1)
            if result is not None and "gfs.t" in result.text:
                return latest_date_folder, cycle

        previous = dates[-2].replace("gfs.", "") if len(dates) >= 2 else latest_date_folder
        return previous, "00"
    except Exception as error:
        print(f"[AVISO] Error consultando ciclos ({error}). Usando ciclo estimado.")
        yesterday = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        ).strftime("%Y%m%d")
        return yesterday, "00"


def _normalize_and_crop_grid(pressure, lats, lons):
    """
    Normaliza longitudes a [-180, 180], ordena la grilla y recorta al dominio
    de seguimiento ERA5 [-48°S, -18°S] x [-120°W, -70°W].
    """
    lats = np.asarray(lats, dtype=float)
    lons = np.asarray(lons, dtype=float)
    pressure = np.asarray(pressure, dtype=float)

    lons = ((lons + 180.0) % 360.0) - 180.0

    lat_order = np.argsort(lats)
    lon_order = np.argsort(lons)
    lats = lats[lat_order]
    lons = lons[lon_order]
    pressure = pressure[np.ix_(lat_order, lon_order)]

    lat_mask = (lats >= TRACK_LAT_SOUTH) & (lats <= TRACK_LAT_NORTH)
    lon_mask = (lons >= TRACK_LON_WEST) & (lons <= TRACK_LON_EAST)

    lats = lats[lat_mask]
    lons = lons[lon_mask]
    pressure = pressure[np.ix_(lat_mask, lon_mask)]

    return pressure, lats, lons


def _load_cropped_pressure(grib_path):
    """
    Lee un GRIB2, normaliza longitudes y recorta al dominio ERA5.
    Devuelve presión en hPa, latitudes y longitudes reales.
    """
    import xarray as xr

    with xr.open_dataset(os.fspath(grib_path), engine="cfgrib") as ds:
        pressure = (ds["prmsl"] / 100.0).values
        lats = ds["latitude"].values
        lons = ds["longitude"].values

    return _normalize_and_crop_grid(pressure, lats, lons)


def _extract_metrics_and_grid(grib_path, land_union, valid_date, forecast_hour):
    """
    Calcula métricas V5.3 y construye el documento de rejilla 2D real.
    No genera anomalías GFS: no existe una climatología 2D cargada en este flujo.
    """
    pressure, lats, lons = _load_cropped_pressure(grib_path)
    if pressure.size == 0:
        return None, None

    metrics = compute_daily_aps_metrics(
        pressure, lats, lons,
        land_union=land_union,
        sigma=1.0,
    )
    if metrics is None:
        return None, None

    grid_document = build_grid_document(
        model_id="noaa_gfs_forecast",
        date=valid_date,
        lats=lats,
        lons=lons,
        slp=pressure,
        anomaly=None,
        forecast_hour=forecast_hour,
        anomaly_reference=None,
    )
    return metrics, grid_document


def _download_step(date_str, cycle_str, f_step, target_grib,
                   timeout=REQUEST_TIMEOUT, retries=MAX_RETRIES):
    """
    Descarga un paso GFS de forma atómica. Retorna True si el archivo es válido.
    """
    f_str = f"{f_step:03d}"
    url = (
        f"{NOMADS_BASE}/cgi-bin/filter_gfs_0p25.pl"
        f"?dir=%2Fgfs.{date_str}%2F{cycle_str}%2Fatmos"
        f"&file=gfs.t{cycle_str}z.pgrb2.0p25.f{f_str}"
        f"&var_PRMSL=on"
        f"&subregion=on"
        f"&toplat={LAT_NORTH}&bottomlat={LAT_SOUTH}&leftlon={LON_WEST}&rightlon={LON_EAST}"
    )
    response = _request_with_retries(url, timeout=timeout, retries=retries)
    if response is None:
        return False
    if len(response.content) <= 1000 or not response.content.startswith(b"GRIB"):
        print(f"⚠️  Paso f{f_str} no disponible o respuesta no válida.")
        return False

    temp_grib = temp_path_for(target_grib)
    try:
        temp_grib.write_bytes(response.content)
        os.replace(temp_grib, target_grib)
    except Exception:
        if temp_grib.exists():
            temp_grib.unlink()
        raise
    return True


def fetch_gfs_forecast_steps(date_str, cycle_str, output_dir, land_union,
                             min_steps=5, strict=False, timeout=REQUEST_TIMEOUT,
                             retries=MAX_RETRIES):
    """
    Descarga y procesa los pasos de pronóstico de 0 a 168 horas (7 días).
    Devuelve un diccionario con todas las métricas V5.3 por paso.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    forecast = {field: [] for field in FORECAST_FIELDS}
    failed_steps = []
    base_time = datetime.datetime.strptime(f"{date_str} {cycle_str}", "%Y%m%d %H")

    print(f"\n📡 [NOAA GFS] Procesando pronóstico operativo ciclo {date_str} {cycle_str}Z...")

    for f_step in FORECAST_HOURS:
        f_str = f"{f_step:03d}"
        target_grib = output_dir / f"gfs_{date_str}_{cycle_str}z_f{f_str}.grib2"
        valid_date = (base_time + datetime.timedelta(hours=f_step)).strftime("%Y-%m-%d")

        if not is_nonempty_file(target_grib):
            if not _download_step(
                date_str, cycle_str, f_step, target_grib,
                timeout=timeout, retries=retries,
            ):
                failed_steps.append(f_step)
                continue

        try:
            metrics, grid_document = _extract_metrics_and_grid(
                target_grib, land_union, valid_date, f_step
            )
        except Exception as error:
            if target_grib.exists():
                target_grib.unlink()
            print(f"⚠️  Error procesando GRIB f{f_str}: {error}")
            failed_steps.append(f_step)
            continue

        if metrics is None or grid_document is None:
            print(f"⚠️  f{f_str} sin puntos oceánicos válidos; se omite.")
            failed_steps.append(f_step)
            continue

        try:
            export_grid_document(grid_document)
        except Exception as error:
            print(f"⚠️  No se pudo publicar la rejilla 2D de f{f_str}: {error}")
            failed_steps.append(f_step)
            continue

        forecast["dates"].append(valid_date)
        forecast["forecast_hours"].append(f_step)
        for field in FORECAST_FIELDS:
            if field in ("dates", "forecast_hours"):
                continue
            forecast[field].append(metrics[field])

        print(
            f"  + Pronóstico +{f_step}h ({valid_date}): "
            f"PSA={metrics['p_max_fit']} hPa, "
            f"Centro: {metrics['lat_core']}°S, {metrics['lon_core']}°W, "
            f"Régimen: {metrics['regime']}"
        )

    n_steps = len(forecast["dates"])
    if failed_steps:
        print(f"⚠️  Pasos no disponibles: {failed_steps}")
    if n_steps < min_steps:
        message = (
            f"Solo se obtuvieron {n_steps} pasos válidos; el mínimo requerido es {min_steps}."
        )
        if strict:
            raise RuntimeError(message)
        print(f"⚠️  {message}")
    elif strict and failed_steps:
        raise RuntimeError(
            f"Modo estricto: fallaron los pasos {failed_steps} aunque hay {n_steps} válidos."
        )

    # Solo un ciclo completo puede retirar fechas del manifiesto anterior.
    if not failed_steps and n_steps == len(FORECAST_HOURS):
        removed = prune_model_grids("noaa_gfs_forecast", forecast["dates"])
        if removed:
            print(f"🧹 [REJILLAS] Fechas GFS antiguas retiradas: {removed}")

    return forecast


def _build_archive_rows(forecast, cycle, generated_at):
    """
    Convierte el bloque de pronóstico en filas tabulares para el historial.
    """
    rows = []
    n_steps = len(forecast["dates"])
    for index in range(n_steps):
        row = {"cycle": cycle, "generated_at": generated_at}
        for field in FORECAST_FIELDS:
            row[field] = forecast[field][index]
        rows.append(row)
    return rows


def archive_forecast(forecast, cycle, generated_at, history_path, web_csv_path):
    """
    Actualiza el historial GFS por ciclo y publica el CSV del pronóstico vigente.
    """
    import pandas as pd

    forecast_df = pd.DataFrame(_build_archive_rows(forecast, cycle, generated_at))
    forecast_df = forecast_df[ARCHIVE_COLUMNS]
    atomic_csv_dump(forecast_df, web_csv_path, index=False)
    print(f"✅ [GFS] CSV del pronóstico vigente publicado en: {web_csv_path}")

    history_df = forecast_df
    if Path(history_path).exists():
        existing = pd.read_csv(history_path)
        existing = existing[existing["cycle"] != cycle]
        history_df = pd.concat([existing, forecast_df], ignore_index=True)

    for column in ARCHIVE_COLUMNS:
        if column not in history_df.columns:
            history_df[column] = None
    history_df = history_df[ARCHIVE_COLUMNS]
    history_df = history_df.sort_values(["cycle", "forecast_hours"]).reset_index(drop=True)
    atomic_csv_dump(history_df, history_path, index=False)
    print(f"✅ [GFS] Historial de pronósticos actualizado en: {history_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Descargador de pronóstico NOAA GFS para el APS (V5.3)"
    )
    parser.add_argument("--output-json", type=str,
                        default="data/processed/gfs_forecast_aps.json",
                        help="Ruta del JSON con el pronóstico completo.")
    parser.add_argument("--temp-dir", type=str, default="data/temp/gfs",
                        help="Directorio temporal para archivos GRIB2.")
    parser.add_argument("--history-csv", type=str,
                        default="data/processed/gfs_forecast_history.csv",
                        help="Historial acumulado de pronósticos GFS.")
    parser.add_argument("--web-csv", type=str,
                        default="web/data/gfs_forecast_aps_metrics.csv",
                        help="CSV del pronóstico vigente para descarga web.")
    parser.add_argument("--archive", action="store_true",
                        help="Agrega o actualiza el historial GFS por ciclo.")
    parser.add_argument("--min-steps", type=int, default=5,
                        help="Mínimo de pasos válidos exigidos (por defecto 5).")
    parser.add_argument("--strict", action="store_true",
                        help="Falla si no se alcanza --min-steps o si falta algún paso.")
    parser.add_argument("--cycle", type=str, default=None,
                        help="Ciclo forzado 'YYYYMMDD HHZ' (útil con GRIB ya descargados).")
    parser.add_argument("--timeout", type=int, default=REQUEST_TIMEOUT,
                        help="Timeout HTTP en segundos (por defecto 60).")
    parser.add_argument("--retries", type=int, default=MAX_RETRIES,
                        help="Número de reintentos HTTP (por defecto 3).")
    args = parser.parse_args()

    if not check_gfs_dependencies():
        sys.exit(1)

    output_json = resolve_project_path(args.output_json)
    temp_dir = resolve_project_path(args.temp_dir)
    history_csv = resolve_project_path(args.history_csv)
    web_csv = resolve_project_path(args.web_csv)

    if args.cycle:
        date_str, cycle_str = _parse_forced_cycle(args.cycle)
    else:
        date_str, cycle_str = get_latest_gfs_cycle(
            timeout=args.timeout, retries=args.retries
        )

    land_union = download_and_load_natural_earth_10m()

    try:
        forecast = fetch_gfs_forecast_steps(
            date_str, cycle_str, temp_dir, land_union,
            min_steps=args.min_steps, strict=args.strict,
            timeout=args.timeout, retries=args.retries,
        )
    except RuntimeError as error:
        print(f"[ERROR] {error}")
        sys.exit(1)

    if not forecast["dates"]:
        print("[ERROR] No se pudo compilar el pronóstico de GFS.")
        sys.exit(1)

    generated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cycle_label = f"{date_str} {cycle_str}Z"
    payload = {
        "model_id": "noaa_gfs_forecast",
        "model_name": "NOAA GFS (Pronóstico Operativo 7 Días)",
        "cycle": cycle_label,
        "generated_at": generated_at,
        "forecast": forecast,
    }

    atomic_json_dump(payload, output_json, indent=2, ensure_ascii=False)
    print(f"\n✅ [ÉXITO] Pronóstico GFS a 7 días guardado en: {output_json}")

    if args.archive:
        archive_forecast(forecast, cycle_label, generated_at, history_csv, web_csv)
    else:
        import pandas as pd
        forecast_df = pd.DataFrame(_build_archive_rows(forecast, cycle_label, generated_at))
        atomic_csv_dump(forecast_df[ARCHIVE_COLUMNS], web_csv, index=False)
        print(f"✅ [GFS] CSV del pronóstico vigente publicado en: {web_csv}")


if __name__ == "__main__":
    main()
