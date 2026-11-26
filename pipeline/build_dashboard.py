#!/usr/bin/env python3
"""
Construcción del payload web del APS desde la caché CSV procesada.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3

Fase 4 del plan: este script NO lee NetCDF. Toma la caché operativa
(data/processed/era5_daily_aps_metrics.csv), la climatología OMM, el pronóstico
GFS y la rejilla espacial más reciente, y reconstruye el JSON/CSVs de la web.

Uso típico:
    ./venv/bin/python pipeline/build_dashboard.py \
        --from-cache --active-start-year 1993
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from pipeline.calculate_aps_metrics import (
    build_dashboard_dataset_v53,
    write_dashboard_payloads,
)
from pipeline.compute_climatology import load_wmo_climatology
from pipeline.file_utils import atomic_csv_dump
from pipeline.grid_export import export_grid_document, normalize_grid_document
from pipeline.paths import resolve_project_path
from pipeline.validation_metrics import load_gfs_history


def _read_cache(cache_path):
    """
    Lee el caché diario y garantiza las columnas temporales mínimas.
    """
    cache_path = Path(cache_path)
    if not cache_path.exists():
        raise FileNotFoundError(
            f"No se encontró el caché ERA5 en {cache_path}. "
            "Ejecútalo con calculate_aps_metrics.py o update_era5_monthly.py."
        )

    frame = pd.read_csv(cache_path)
    if "date" not in frame.columns:
        raise KeyError(f"El caché {cache_path} no contiene la columna 'date'.")

    dates = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.loc[dates.notna()].copy()
    frame["date"] = dates[dates.notna()].dt.strftime("%Y-%m-%d")
    if "year" not in frame.columns:
        frame["year"] = pd.to_datetime(frame["date"]).dt.year
    if "day_of_year" not in frame.columns:
        frame["day_of_year"] = pd.to_datetime(frame["date"]).dt.dayofyear
    return frame


def _load_spatial_grid(path):
    """
    Carga y normaliza la rejilla espacial más reciente.
    Acepta el contrato nuevo (slp/anomaly) y migra el legado
    (current_slp/current_anomaly) sin inventar datos.
    """
    path = Path(path)
    if not path.exists():
        print(
            f"⚠️  Sin rejilla espacial en {path}; el mapa mostrará el aviso "
            "'Campo 2D no disponible para esta fecha/modelo'."
        )
        return None

    with open(path, "r", encoding="utf-8") as handle:
        document = json.load(handle)

    return normalize_grid_document(
        document,
        model_id="era5_reanalysis",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Construye el payload web del APS desde la caché CSV (Fase 4)."
    )
    parser.add_argument("--cache-csv", type=str,
                        default="data/processed/era5_daily_aps_metrics.csv",
                        help="Caché diario ERA5 de entrada.")
    parser.add_argument("--climatology", type=str,
                        default="data/processed/wmo_climatology_1994_2023.json",
                        help="JSON de la Normal OMM 1994-2023.")
    parser.add_argument("--spatial-grid", type=str,
                        default="data/processed/latest_spatial_grid.json",
                        help="JSON con la rejilla espacial más reciente.")
    parser.add_argument("--gfs-history", type=str,
                        default="data/processed/gfs_forecast_history.csv",
                        help="Historial GFS para el skill de pronóstico.")
    parser.add_argument("--output", type=str,
                        default="data/processed/latest_aps_data.json",
                        help="JSON de salida del payload principal.")
    parser.add_argument("--web-output", type=str,
                        default="web/data/latest_aps_data.json",
                        help="Copia del JSON para el cliente web.")
    parser.add_argument("--web-era5-csv", type=str,
                        default="web/data/era5_daily_aps_metrics.csv",
                        help="CSV ERA5 de la ventana activa para descarga.")
    parser.add_argument("--web-multimodel-csv", type=str,
                        default="web/data/aps_multimodel_metrics_lofa.csv",
                        help="CSV multimodelo consolidado para descarga.")
    parser.add_argument("--active-start-year", type=int, default=1993,
                        help="Primer año publicado (por defecto 1993).")
    parser.add_argument("--active-end-year", type=int,
                        default=datetime.date.today().year,
                        help="Último año publicado (por defecto el año actual).")
    parser.add_argument("--from-cache", action="store_true",
                        help="Construye desde la caché CSV sin leer NetCDF (modo por defecto).")
    args = parser.parse_args()

    cache_path = resolve_project_path(args.cache_csv)
    climatology_path = resolve_project_path(args.climatology)
    spatial_grid_path = resolve_project_path(args.spatial_grid)
    gfs_history_path = resolve_project_path(args.gfs_history)
    output_path = resolve_project_path(args.output)
    web_output_path = resolve_project_path(args.web_output)
    web_era5_path = resolve_project_path(args.web_era5_csv)
    web_multimodel_path = resolve_project_path(args.web_multimodel_csv)

    if not climatology_path.exists():
        print(
            f"[ERROR] No se encontró la climatología OMM en {climatology_path}. "
            "Genérala con pipeline/compute_climatology.py."
        )
        sys.exit(1)

    try:
        frame = _read_cache(cache_path)
    except (FileNotFoundError, KeyError) as error:
        print(f"[ERROR] {error}")
        sys.exit(1)

    # Validar explícitamente la climatología canónica antes de construir.
    climatology = load_wmo_climatology(climatology_path)

    active = frame[
        (frame["year"] >= args.active_start_year)
        & (frame["year"] <= args.active_end_year)
    ].copy().reset_index(drop=True)

    if len(active) == 0:
        print(
            f"[ERROR] La ventana activa {args.active_start_year}-{args.active_end_year} "
            "no contiene datos."
        )
        sys.exit(1)

    spatial_grid = _load_spatial_grid(spatial_grid_path)
    if spatial_grid is not None:
        grid_path = export_grid_document(spatial_grid)
        print(f"✅ [REJILLA] Campo 2D real publicado en: {grid_path}")
    gfs_history = load_gfs_history(gfs_history_path)

    dataset, multimodel = build_dashboard_dataset_v53(
        active,
        spatial_grid,
        era5_cache_df=frame,
        gfs_history_df=gfs_history,
        climatology=climatology,
    )
    dataset["metadata"]["active_window"] = {
        "start_year": args.active_start_year,
        "end_year": args.active_end_year,
        "start_date": str(active.iloc[0]["date"]),
        "end_date": str(active.iloc[-1]["date"]),
        "n_days": int(len(active)),
    }

    payload_bytes = write_dashboard_payloads(dataset, output_path, web_output_path)
    print(f"✅ [PAYLOAD] JSON compacto: {payload_bytes} bytes")
    atomic_csv_dump(active, web_era5_path, index=False)
    atomic_csv_dump(multimodel, web_multimodel_path, index=False)

    print(
        f"✅ [BUILD] Payload con {len(active)} días "
        f"({active.iloc[0]['date']} → {active.iloc[-1]['date']}) generado en "
        f"{output_path}"
    )
    print(f"✅ [BUILD] Copia web: {web_output_path}")
    print(f"✅ [BUILD] CSVs web actualizados: {web_era5_path.name}, {web_multimodel_path.name}")
    print(f"✅ [BUILD] Filas de validación publicadas: {len(dataset['validation_metrics'])}")


if __name__ == "__main__":
    main()
