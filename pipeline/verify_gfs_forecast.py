#!/usr/bin/env python3
"""
Verificación objetiva de pronósticos NOAA GFS contra el reanálisis ERA5.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3

Fase 3 del plan: cruza por fecha exacta el historial de pronósticos GFS con el
caché diario ERA5 y publica RMSE, BIAS, correlación, Willmott y error espacial
geodésico en data/processed/gfs_verification_metrics.json.

Si no existen pares verificados suficientes, las métricas se publican como null.
Nunca se insertan valores sintéticos.
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from pipeline.file_utils import atomic_json_dump
from pipeline.paths import resolve_project_path
from pipeline.validation_metrics import compute_gfs_verification


def _read_csv(path, label):
    """
    Lee un CSV obligatorio y falla con un mensaje explícito si no existe.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el {label} en {path}.")
    return pd.read_csv(path)


def main():
    parser = argparse.ArgumentParser(
        description="Verificación GFS vs ERA5 por fecha exacta (Fase 3)."
    )
    parser.add_argument("--history", type=str,
                        default="data/processed/gfs_forecast_history.csv",
                        help="Historial acumulado de pronósticos GFS.")
    parser.add_argument("--cache-csv", type=str,
                        default="data/processed/era5_daily_aps_metrics.csv",
                        help="Caché diario ERA5 de referencia.")
    parser.add_argument("--output", type=str,
                        default="data/processed/gfs_verification_metrics.json",
                        help="JSON de salida con métricas verificadas.")
    parser.add_argument("--min-pairs", type=int, default=2,
                        help="Mínimo de fechas verificadas para publicar métricas.")
    args = parser.parse_args()

    history_path = resolve_project_path(args.history)
    cache_path = resolve_project_path(args.cache_csv)
    output_path = resolve_project_path(args.output)

    try:
        history = _read_csv(history_path, "historial GFS")
        cache = _read_csv(cache_path, "caché ERA5")
    except FileNotFoundError as error:
        print(f"[ERROR] {error}")
        sys.exit(1)

    payload = compute_gfs_verification(history, cache, min_pairs=args.min_pairs)
    atomic_json_dump(payload, output_path, indent=2, ensure_ascii=False)

    metrics = payload["metrics"]
    print(f"✅ [VERIFICACIÓN GFS] Pares por fecha exacta: {payload['n_pairs']}")
    if payload["n_pairs"] < args.min_pairs:
        print(
            "⚠️  Sin pares verificados suficientes; se publican métricas N/D "
            f"en {output_path}."
        )
    else:
        print(
            "   RMSE={rmse_psa_hpa} hPa | BIAS={bias_psa_hpa} hPa | "
            "r={corr_psa} | d={willmott_d} | error espacial={dist_error_km} km".format(
                **metrics
            )
        )
        print(f"✅ [VERIFICACIÓN GFS] Resultado guardado en: {output_path}")


if __name__ == "__main__":
    main()
