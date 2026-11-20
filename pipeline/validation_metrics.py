#!/usr/bin/env python3
"""
Construcción de métricas objetivas de validación inter-modelo del APS.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3

Este módulo materializa la Fase 3 del plan de automatización:

- RMSE, BIAS, correlación de Pearson, índice de Willmott y error espacial
  geodésico, todos calculados desde datos reales.
- Referencias explícitas: Normal OMM 1994-2023 (concordancia histórica) y
  ERA5 verificante (skill de pronóstico).
- Alineación estricta por fecha, nunca por posición de índice.
- Valores ausentes se publican como None ("N/D" en la web), jamás inventados.
"""

import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.aps_metrics import (
    bias,
    mean_geodesic_distance,
    pearson_r,
    rmse,
    willmott_d,
)
from pipeline.compute_climatology import generate_doy_climatology_series

REQUIRED_COLUMNS = ["p_max_fit", "lat_core", "lon_core"]

REFERENCE_CLIMATOLOGY = "Normal OMM 1994-2023"
REFERENCE_ERA5 = "ERA5 Reanálisis"

SKILL_TYPE_CONCORDANCE = "historical_concordance"
SKILL_TYPE_CLIMATOLOGY = "concordance_with_climatology"
SKILL_TYPE_FORECAST = "forecast_skill_vs_era5"


def _to_date_frame(frame, date_column="date"):
    """
    Normaliza la columna de fecha a ISO YYYY-MM-DD y descarta filas sin fecha.
    """
    if frame is None or len(frame) == 0:
        return pd.DataFrame(columns=["date"] + REQUIRED_COLUMNS)

    out = frame.copy()
    if date_column != "date":
        if date_column not in out.columns:
            raise KeyError(f"Falta la columna de fecha '{date_column}'.")
        out = out.rename(columns={date_column: "date"})

    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out = out.dropna(subset=["date"])

    for column in REQUIRED_COLUMNS:
        if column not in out.columns:
            out[column] = np.nan
        out[column] = pd.to_numeric(out[column], errors="coerce")

    return out[["date"] + REQUIRED_COLUMNS]


def _merge_by_date(model_frame, reference_frame):
    """
    Cruza modelo y referencia por fecha exacta. La alineación nunca usa índices.
    """
    model = _to_date_frame(model_frame).rename(
        columns={column: f"{column}_model" for column in REQUIRED_COLUMNS}
    )
    reference = _to_date_frame(reference_frame).rename(
        columns={column: f"{column}_ref" for column in REQUIRED_COLUMNS}
    )
    return pd.merge(model, reference, on="date", how="inner")


def _round_or_none(value, digits):
    """
    Redondea un escalar o devuelve None si no es finito.
    """
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric):
        return None
    return round(numeric, digits)


def compute_series_metrics(model_frame, reference_frame, min_pairs=2):
    """
    Calcula el bloque de métricas para dos series alineadas por fecha.
    """
    merged = _merge_by_date(model_frame, reference_frame)
    n_pairs = int(len(merged))

    empty = {
        "n_pairs": n_pairs,
        "rmse_psa_hpa": None,
        "bias_psa_hpa": None,
        "corr_psa": None,
        "corr_lat": None,
        "dist_error_km": None,
        "willmott_d": None,
    }
    if n_pairs < min_pairs:
        return empty

    metrics = {
        "n_pairs": n_pairs,
        "rmse_psa_hpa": _round_or_none(
            rmse(merged["p_max_fit_model"], merged["p_max_fit_ref"]), 3
        ),
        "bias_psa_hpa": _round_or_none(
            bias(merged["p_max_fit_model"], merged["p_max_fit_ref"]), 3
        ),
        "corr_psa": _round_or_none(
            pearson_r(merged["p_max_fit_model"], merged["p_max_fit_ref"]), 3
        ),
        "corr_lat": _round_or_none(
            pearson_r(merged["lat_core_model"], merged["lat_core_ref"]), 3
        ),
        "dist_error_km": _round_or_none(
            mean_geodesic_distance(
                merged["lat_core_model"], merged["lon_core_model"],
                merged["lat_core_ref"], merged["lon_core_ref"],
            ),
            1,
        ),
        "willmott_d": _round_or_none(
            willmott_d(merged["p_max_fit_model"], merged["p_max_fit_ref"]), 3
        ),
    }
    return metrics


def skill_rating(willmott_value, n_pairs):
    """
    Traduce el índice de Willmott a una etiqueta y clase visual.
    """
    if n_pairs < 2 or willmott_value is None:
        return "N/D", "badge-info"
    if willmott_value >= 0.95:
        return "Excelente", "badge-success"
    if willmott_value >= 0.85:
        return "Muy bueno", "badge-primary"
    if willmott_value >= 0.70:
        return "Bueno", "badge-info"
    return "Limitado", "badge-accent"


def _build_row(model, type_label, reference, skill_type, metrics, note):
    """
    Ensambla una fila del contrato validation_metrics.
    """
    rating, badge = skill_rating(metrics["willmott_d"], metrics["n_pairs"])
    return {
        "model": model,
        "type": type_label,
        "reference": reference,
        "skill_type": skill_type,
        "n_pairs": int(metrics["n_pairs"]),
        "rmse_psa_hpa": metrics["rmse_psa_hpa"],
        "bias_psa_hpa": metrics["bias_psa_hpa"],
        "corr_psa": metrics["corr_psa"],
        "corr_lat": metrics["corr_lat"],
        "dist_error_km": metrics["dist_error_km"],
        "willmott_d": metrics["willmott_d"],
        "skill_rating": rating,
        "skill_class": badge,
        "note": note,
    }


def _climatology_frame(dates, climatology):
    """
    Evalúa la Normal OMM en las fechas indicadas mediante interpolación DOY.
    """
    normalized = pd.to_datetime(pd.Series(dates), errors="coerce").dt.strftime("%Y-%m-%d")
    doy = pd.to_datetime(normalized, errors="coerce").dt.dayofyear.to_numpy(dtype=float)
    interpolators = generate_doy_climatology_series(normalized.tolist(), climatology)

    return pd.DataFrame({
        "date": normalized,
        "p_max_fit": np.asarray(interpolators["p_max"](doy), dtype=float),
        "lat_core": np.asarray(interpolators["lat_core"](doy), dtype=float),
        "lon_core": np.asarray(interpolators["lon_core"](doy), dtype=float),
    })


def _deduplicate_history(history_frame):
    """
    Conserva, por cada fecha pronosticada, el ciclo más reciente disponible.
    """
    history = _to_date_frame(history_frame, date_column="dates")
    if "generated_at" in history_frame.columns:
        original = history_frame.copy()
        original["date"] = pd.to_datetime(
            original["dates"], errors="coerce"
        ).dt.strftime("%Y-%m-%d")
        original["generated_at"] = pd.to_datetime(
            original["generated_at"], errors="coerce", utc=True
        )
        original = original.dropna(subset=["date"]).sort_values("generated_at")
        original = original.drop_duplicates(subset=["date"], keep="last")
        history = _to_date_frame(original)
    else:
        history = history.drop_duplicates(subset=["date"], keep="last")
    return history.reset_index(drop=True)


def build_validation_metrics(era5_frame, climatology, gfs_forecast=None,
                             gfs_history_frame=None, era5_cache_frame=None,
                             min_pairs=2):
    """
    Construye la lista validation_metrics del payload web.

    Referencias:
      1. ERA5 vs Normal OMM 1994-2023: concordancia histórica.
      2. GFS vs Normal OMM: concordancia provisional, no skill verificado.
      3. GFS vs ERA5: skill de pronóstico, solo si existen fechas verificadas.
    """
    rows = []

    era5 = _to_date_frame(era5_frame)
    if len(era5) > 0:
        climatology_frame = _climatology_frame(era5["date"], climatology)
        metrics = compute_series_metrics(era5, climatology_frame, min_pairs=min_pairs)
        rows.append(_build_row(
            model="ERA5 Reanálisis",
            type_label="Reanálisis vs Normal OMM 1994-2023",
            reference=REFERENCE_CLIMATOLOGY,
            skill_type=SKILL_TYPE_CONCORDANCE,
            metrics=metrics,
            note=(
                "Concordancia histórica diaria con la Normal OMM 1994-2023. "
                "La climatología se calcula desde ERA5, por lo que mide "
                "representatividad climática, no habilidad independiente."
            ),
        ))

    if gfs_forecast:
        gfs_frame = _to_date_frame(
            pd.DataFrame({
                "date": gfs_forecast.get("dates", []),
                "p_max_fit": gfs_forecast.get("p_max_fit", []),
                "lat_core": gfs_forecast.get("lat_core", []),
                "lon_core": gfs_forecast.get("lon_core", []),
            })
        )
        if len(gfs_frame) > 0:
            climatology_frame = _climatology_frame(gfs_frame["date"], climatology)
            metrics = compute_series_metrics(gfs_frame, climatology_frame, min_pairs=min_pairs)
            rows.append(_build_row(
                model="NOAA GFS Pronóstico",
                type_label="Pronóstico vs Normal OMM",
                reference=REFERENCE_CLIMATOLOGY,
                skill_type=SKILL_TYPE_CLIMATOLOGY,
                metrics=metrics,
                note=(
                    "Concordancia provisional del pronóstico con la Normal OMM. "
                    "No constituye skill verificado: la referencia es "
                    "climatológica, no un análisis del día pronosticado."
                ),
            ))

    if gfs_history_frame is not None and era5_cache_frame is not None:
        history = _deduplicate_history(gfs_history_frame)
        if len(history) > 0:
            cache = _to_date_frame(era5_cache_frame)
            metrics = compute_series_metrics(history, cache, min_pairs=min_pairs)
            if metrics["n_pairs"] >= min_pairs:
                rows.append(_build_row(
                    model="NOAA GFS Pronóstico",
                    type_label="Pronóstico vs ERA5 verificante",
                    reference=REFERENCE_ERA5,
                    skill_type=SKILL_TYPE_FORECAST,
                    metrics=metrics,
                    note=(
                        "Skill de pronóstico calculado por fecha exacta entre el "
                        "historial GFS y el reanálisis ERA5. Solo incluye fechas "
                        "ya verificadas; si no hay pares suficientes se omite."
                    ),
                ))

    return rows


def compute_gfs_verification(gfs_history_frame, era5_cache_frame, min_pairs=2):
    """
    Calcula el payload de verificación GFS vs ERA5 y sus pares por fecha.
    """
    history = _deduplicate_history(gfs_history_frame) if gfs_history_frame is not None else pd.DataFrame()
    cache = _to_date_frame(era5_cache_frame)
    metrics = compute_series_metrics(history, cache, min_pairs=min_pairs)
    merged = _merge_by_date(history, cache)

    pairs = []
    for _, row in merged.iterrows():
        pair = {
            "date": row["date"],
            "gfs_p_max_fit": _round_or_none(row["p_max_fit_model"], 2),
            "era5_p_max_fit": _round_or_none(row["p_max_fit_ref"], 2),
            "error_hpa": _round_or_none(
                row["p_max_fit_model"] - row["p_max_fit_ref"], 3
            ),
            "gfs_lat_core": _round_or_none(row["lat_core_model"], 2),
            "gfs_lon_core": _round_or_none(row["lon_core_model"], 2),
            "era5_lat_core": _round_or_none(row["lat_core_ref"], 2),
            "era5_lon_core": _round_or_none(row["lon_core_ref"], 2),
        }
        distance = mean_geodesic_distance(
            [row["lat_core_model"]], [row["lon_core_model"]],
            [row["lat_core_ref"]], [row["lon_core_ref"]],
            min_pairs=1,
        )
        pair["dist_error_km"] = _round_or_none(distance, 1)
        pairs.append(pair)

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "reference": REFERENCE_ERA5,
        "skill_type": SKILL_TYPE_FORECAST,
        "min_pairs": int(min_pairs),
        "n_pairs": int(metrics["n_pairs"]),
        "metrics": {
            "rmse_psa_hpa": metrics["rmse_psa_hpa"],
            "bias_psa_hpa": metrics["bias_psa_hpa"],
            "corr_psa": metrics["corr_psa"],
            "corr_lat": metrics["corr_lat"],
            "dist_error_km": metrics["dist_error_km"],
            "willmott_d": metrics["willmott_d"],
        },
        "pairs": pairs,
        "note": (
            "Verificación por fecha exacta entre pronósticos GFS archivados y "
            "ERA5. Los valores nulos indican que aún no existen pares "
            "verificados suficientes; nunca se reemplazan por constantes."
        ),
    }


def load_gfs_history(path):
    """
    Carga el historial GFS archivado. Devuelve None si no existe.
    """
    path = Path(path)
    if not path.exists():
        return None
    return pd.read_csv(path)


def load_gfs_forecast(path):
    """
    Carga el bloque 'forecast' del JSON GFS. Devuelve None si no existe.
    """
    path = Path(path)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    forecast = payload.get("forecast")
    return forecast if isinstance(forecast, dict) else None
