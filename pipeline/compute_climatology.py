#!/usr/bin/env python3
"""
Cálculo de la Climatología Normal OMM 1994-2023 a partir del caché ERA5.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3

Genera data/processed/wmo_climatology_1994_2023.json con las medias mensuales
de todas las métricas V5.3. El acimut se promedia de forma circular y cada
variable se valida contra rangos físicos antes de publicarse.
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.file_utils import atomic_json_dump
from pipeline.paths import resolve_project_path

DEFAULT_START_YEAR = 1994
DEFAULT_END_YEAR = 2023
DEFAULT_OUTPUT = "data/processed/wmo_climatology_1994_2023.json"

# Columnas del caché -> claves publicadas en el JSON climatológico.
CLIMATOLOGY_COLUMNS = {
    "p_max": "p_max_fit",
    "lat_core": "lat_core",
    "lon_core": "lon_core",
    "lat_centroid": "lat_centroid",
    "lon_centroid": "lon_centroid",
    "area_1020": "area_1020",
    "vol_integral": "vol_integral",
    "h_eff": "h_eff",
    "dist_decoupling_km": "dist_decoupling_km",
    "azimuth_deg": "azimuth_deg",
    "p_patagonia": "p_patagonia",
}

# Rangos físicos admisibles para las medias mensuales publicadas.
PHYSICAL_RANGES = {
    "p_max": (980.0, 1060.0),
    "lat_core": (-50.0, -16.0),
    "lon_core": (-122.0, -68.0),
    "lat_centroid": (-50.0, -16.0),
    "lon_centroid": (-122.0, -68.0),
    "area_1020": (0.0, 50.0),
    "vol_integral": (0.0, 500.0),
    "h_eff": (0.0, 50.0),
    "dist_decoupling_km": (0.0, 6000.0),
    "azimuth_deg": (0.0, 360.0),
    "p_patagonia": (950.0, 1060.0),
}


def circular_mean_deg(values):
    """
    Media circular de ángulos en grados: atan2(mean(sin), mean(cos)).
    Retorna None si no hay valores finitos.
    """
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return None
    radians = np.radians(arr)
    mean_angle = np.arctan2(np.mean(np.sin(radians)), np.mean(np.cos(radians)))
    return float((np.degrees(mean_angle) + 360.0) % 360.0)


def filter_period(df, start_year=DEFAULT_START_YEAR, end_year=DEFAULT_END_YEAR):
    """
    Filtra el DataFrame diario al período climatológico inclusivo.
    """
    dates = pd.to_datetime(df["date"])
    start = pd.Timestamp(f"{start_year}-01-01")
    end = pd.Timestamp(f"{end_year}-12-31")
    return df.loc[(dates >= start) & (dates <= end)].copy()


def compute_monthly_climatology(df, start_year=DEFAULT_START_YEAR,
                                end_year=DEFAULT_END_YEAR):
    """
    Calcula las medias mensuales del período indicado y valida rangos físicos.
    """
    period_df = filter_period(df, start_year, end_year)
    if len(period_df) == 0:
        raise ValueError(
            f"Sin datos entre {start_year}-01-01 y {end_year}-12-31 en el caché."
        )

    period_df["month"] = pd.to_datetime(period_df["date"]).dt.month
    grouped = period_df.groupby("month", sort=True)

    monthly = {"months": list(range(1, 13))}
    for output_key, source_column in CLIMATOLOGY_COLUMNS.items():
        if source_column not in period_df.columns:
            raise KeyError(f"Falta la columna '{source_column}' en el caché ERA5.")

        if output_key == "azimuth_deg":
            values = [
                circular_mean_deg(grouped.get_group(month)[source_column])
                if month in grouped.groups else None
                for month in monthly["months"]
            ]
        else:
            means = grouped[source_column].mean()
            values = [
                None if month not in means.index or pd.isna(means.loc[month])
                else float(round(float(means.loc[month]), 4))
                for month in monthly["months"]
            ]

        _validate_physical_range(output_key, values)
        monthly[output_key] = values

    monthly["metadata"] = {
        "source": "data/processed/era5_daily_aps_metrics.csv",
        "institution": "Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)",
        "period": f"{start_year}-01-01/{end_year}-12-31",
        "start_year": int(start_year),
        "end_year": int(end_year),
        "n_days": int(len(period_df)),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_columns": CLIMATOLOGY_COLUMNS,
        "circular_azimuth": True,
        "version": "5.3",
    }
    return monthly


def _validate_physical_range(key, values):
    """
    Verifica que todos los valores mensuales estén dentro del rango físico.
    """
    low, high = PHYSICAL_RANGES[key]
    for index, value in enumerate(values, start=1):
        if value is None:
            continue
        if not np.isfinite(value) or value < low or value > high:
            raise ValueError(
                f"Valor climatológico fuera de rango para {key} en mes {index}: "
                f"{value} no pertenece a [{low}, {high}]."
            )


def load_wmo_climatology(path=None):
    """
    Carga la climatología mensual OMM 1994-2023 desde su JSON canónico.
    Falla de forma explícita si el archivo no existe o está incompleto.
    """
    if path is None:
        path = resolve_project_path(DEFAULT_OUTPUT)
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró la climatología OMM en {path}. "
            "Genérala con: ./venv/bin/python pipeline/compute_climatology.py "
            "--start-year 1994 --end-year 2023"
        )

    with open(path, "r", encoding="utf-8") as handle:
        climatology = json.load(handle)

    required = ["months"] + list(CLIMATOLOGY_COLUMNS.keys())
    missing = [key for key in required if key not in climatology]
    if missing:
        raise KeyError(
            f"Climatología incompleta en {path}; faltan claves: {', '.join(missing)}"
        )
    if len(climatology["months"]) != 12:
        raise ValueError(f"La climatología de {path} no contiene 12 meses.")

    return climatology


def generate_doy_climatology_series(dates_list, climatology=None):
    """
    Genera interpoladores continuos por día del año (DOY) a partir de la
    climatología mensual OMM 1994-2023 cargada desde su JSON canónico.

    El acimut se interpola de forma circular sobre sus componentes seno/coseno
    para evitar discontinuidades entre 359° y 0°.
    """
    if climatology is None:
        climatology = load_wmo_climatology()

    # Puntos medios aproximados de cada mes expresados como día del año
    mid_month_doy = np.array([15, 45, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349])

    # Envolver para interpolación periódica circular
    doy_extended = np.concatenate([mid_month_doy - 365, mid_month_doy, mid_month_doy + 365])

    clim_interpolators = {}
    for var in ["p_max", "lat_core", "lon_core", "lat_centroid", "lon_centroid",
                "area_1020", "vol_integral", "h_eff", "dist_decoupling_km", "azimuth_deg", "p_patagonia"]:
        vals = np.asarray(climatology[var], dtype=float)
        if vals.size != 12 or not np.all(np.isfinite(vals)):
            raise ValueError(f"La climatología mensual de '{var}' debe tener 12 valores finitos.")

        if var == "azimuth_deg":
            # Interpolación circular sobre componentes seno/coseno
            sin_interp = interp1d(
                doy_extended,
                np.concatenate([np.sin(np.radians(vals))] * 3),
                kind="cubic",
            )
            cos_interp = interp1d(
                doy_extended,
                np.concatenate([np.cos(np.radians(vals))] * 3),
                kind="cubic",
            )
            clim_interpolators[var] = (
                lambda doy, si=sin_interp, ci=cos_interp:
                (np.degrees(np.arctan2(si(doy), ci(doy))) + 360.0) % 360.0
            )
        else:
            vals_extended = np.concatenate([vals, vals, vals])
            clim_interpolators[var] = interp1d(doy_extended, vals_extended, kind="cubic")

    return clim_interpolators


def main():
    parser = argparse.ArgumentParser(
        description="Calcula la Climatología Normal OMM 1994-2023 desde el caché ERA5."
    )
    parser.add_argument("--cache-csv", type=str,
                        default="data/processed/era5_daily_aps_metrics.csv",
                        help="Caché diario ERA5 de entrada.")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT,
                        help="Ruta del JSON climatológico de salida.")
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR,
                        help="Primer año del período climatológico (por defecto 1994).")
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR,
                        help="Último año del período climatológico (por defecto 2023).")
    args = parser.parse_args()

    cache_path = resolve_project_path(args.cache_csv)
    output_path = resolve_project_path(args.output)

    if not cache_path.exists():
        print(f"[ERROR] No se encontró el caché ERA5 en {cache_path}.")
        sys.exit(1)

    df = pd.read_csv(cache_path)
    climatology = compute_monthly_climatology(df, args.start_year, args.end_year)
    atomic_json_dump(climatology, output_path, indent=2, ensure_ascii=False)

    print(
        f"✅ [CLIMATOLOGÍA] Normal OMM {args.start_year}-{args.end_year} "
        f"({climatology['metadata']['n_days']} días) guardada en {output_path}"
    )


if __name__ == "__main__":
    main()
