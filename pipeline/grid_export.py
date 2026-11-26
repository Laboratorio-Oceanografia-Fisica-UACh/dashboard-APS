#!/usr/bin/env python3
"""
Exportación atómica de rejillas 2D reales y manifiesto de carga diferida.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3

Contrato:
- Un documento JSON por model_id/fecha en web/data/grids/.
- Manifiesto con claves model_id -> date -> metadatos del archivo.
- Validación estricta de dimensiones, finitud y coherencia model_id/date.
- Ningún valor sintético: las celdas ausentes se publican como null.
"""

import datetime
import json
import math
import re
from pathlib import Path

from pipeline.file_utils import atomic_json_dump
from pipeline.paths import resolve_project_path

SCHEMA_VERSION = 1
DEFAULT_GRIDS_DIR = "web/data/grids"
MANIFEST_NAME = "manifest.json"
_MODEL_RE = re.compile(r"^[a-z0-9_]+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _resolve_grids_dir(grids_dir=None):
    """Resuelve el directorio de rejillas contra la raíz del proyecto."""
    return resolve_project_path(grids_dir or DEFAULT_GRIDS_DIR)


def _is_finite_number(value):
    """Indica si el valor es un número real finito (excluye booleanos)."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _validate_vector(name, values, minimum=2):
    """Valida un vector numérico finito de longitud mínima."""
    if not isinstance(values, list) or len(values) < minimum:
        raise ValueError(f"{name} debe ser una lista con al menos {minimum} valores")
    if not all(_is_finite_number(value) for value in values):
        raise ValueError(f"{name} contiene valores no numéricos o no finitos")


def _validate_matrix(name, matrix, n_rows, n_cols):
    """Valida una matriz rectangular; permite null en celdas enmascaradas."""
    if not isinstance(matrix, list) or len(matrix) != n_rows:
        raise ValueError(f"{name} debe tener exactamente {n_rows} filas")
    for row in matrix:
        if not isinstance(row, list) or len(row) != n_cols:
            raise ValueError(f"{name} debe tener exactamente {n_cols} columnas por fila")
        for value in row:
            if value is not None and not _is_finite_number(value):
                raise ValueError(f"{name} contiene valores no numéricos o no finitos")


def validate_grid_document(document):
    """
    Valida el contrato completo de una rejilla 2D.
    Lanza ValueError con un mensaje explícito si algo no cumple.
    """
    if not isinstance(document, dict):
        raise ValueError("La rejilla debe ser un objeto JSON")

    model_id = document.get("model_id")
    date = document.get("date")
    if not isinstance(model_id, str) or not _MODEL_RE.match(model_id):
        raise ValueError(f"model_id inválido: {model_id!r}")
    if not isinstance(date, str) or not _DATE_RE.match(date):
        raise ValueError(f"date inválida: {date!r}")

    lats = document.get("lats")
    lons = document.get("lons")
    slp = document.get("slp")
    _validate_vector("lats", lats)
    _validate_vector("lons", lons)
    _validate_matrix("slp", slp, len(lats), len(lons))

    anomaly = document.get("anomaly")
    if anomaly is not None:
        _validate_matrix("anomaly", anomaly, len(lats), len(lons))

    forecast_hour = document.get("forecast_hour")
    if forecast_hour is not None and (isinstance(forecast_hour, bool) or not isinstance(forecast_hour, int)):
        raise ValueError("forecast_hour debe ser entero o null")

    return True


def _as_list(value):
    """Convierte arrays tipo numpy a listas nativas."""
    return value.tolist() if hasattr(value, "tolist") else value


def _round_vector(values, digits=2):
    """Convierte un vector a floats redondeados y rechaza valores no finitos."""
    result = []
    for value in _as_list(values):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("El vector contiene valores no finitos")
        result.append(round(number, digits))
    return result


def _round_matrix(matrix, digits=2):
    """Convierte una matriz a floats redondeados; NaN/inf se publican como null."""
    result = []
    for row in _as_list(matrix):
        clean_row = []
        for value in _as_list(row):
            if value is None:
                clean_row.append(None)
                continue
            number = float(value)
            clean_row.append(round(number, digits) if math.isfinite(number) else None)
        result.append(clean_row)
    return result


def build_grid_document(model_id, date, lats, lons, slp, anomaly=None,
                        forecast_hour=None, anomaly_reference=None):
    """
    Construye un documento de rejilla canónico a partir de arrays reales.
    No interpola, no rellena y no inventa celdas.
    """
    document = {
        "model_id": str(model_id),
        "date": str(date),
        "forecast_hour": int(forecast_hour) if forecast_hour is not None else None,
        "anomaly_reference": anomaly_reference,
        "lats": _round_vector(lats),
        "lons": _round_vector(lons),
        "slp": _round_matrix(slp),
        "anomaly": _round_matrix(anomaly) if anomaly is not None else None,
    }
    validate_grid_document(document)
    return document


def normalize_grid_document(document, model_id="era5_reanalysis"):
    """
    Normaliza documentos nuevos o legados (current_slp/current_anomaly).
    El documento legado debe traer 'date', 'lats', 'lons' y 'current_slp'.
    """
    if not isinstance(document, dict):
        raise ValueError("La rejilla debe ser un objeto JSON")

    if "slp" in document:
        candidate = dict(document)
        if not candidate.get("model_id"):
            raise ValueError("La rejilla nueva debe incluir model_id")
        candidate.setdefault("forecast_hour", None)
        candidate.setdefault("anomaly_reference", None)
        if candidate.get("anomaly") is None and "current_anomaly" in candidate:
            candidate["anomaly"] = candidate["current_anomaly"]
        validate_grid_document(candidate)
        return candidate

    legacy_slp = document.get("current_slp")
    legacy_anomaly = document.get("current_anomaly")
    if legacy_slp is None:
        raise ValueError("La rejilla no contiene 'slp' ni 'current_slp'")

    return build_grid_document(
        model_id=model_id,
        date=document.get("date"),
        lats=document.get("lats"),
        lons=document.get("lons"),
        slp=legacy_slp,
        anomaly=legacy_anomaly,
        forecast_hour=None,
        anomaly_reference="domain_spatial_mean" if legacy_anomaly is not None else None,
    )


def load_grid_manifest(grids_dir=None):
    """Carga el manifiesto o devuelve uno vacío si aún no existe."""
    base = _resolve_grids_dir(grids_dir)
    path = base / MANIFEST_NAME
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "generated_at": None, "grids": {}}

    with open(path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version de manifiesto no soportada en {path}")
    if not isinstance(manifest.get("grids"), dict):
        raise ValueError(f"El manifiesto {path} no contiene un objeto 'grids'")
    return manifest


def export_grid_document(document, grids_dir=None):
    """
    Escribe una rejilla de forma atómica y actualiza el manifiesto.
    Devuelve la ruta del archivo publicado.
    """
    document = normalize_grid_document(document)
    base = _resolve_grids_dir(grids_dir)
    model_id = document["model_id"]
    date = document["date"]
    relative = Path(model_id) / f"{date}.json"
    target = base / relative

    atomic_json_dump(
        document, target,
        indent=None, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )

    manifest = load_grid_manifest(base)
    manifest["generated_at"] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()
    manifest["grids"].setdefault(model_id, {})[date] = {
        "file": relative.as_posix(),
        "forecast_hour": document.get("forecast_hour"),
        "n_lats": len(document["lats"]),
        "n_lons": len(document["lons"]),
        "bytes": target.stat().st_size,
    }
    atomic_json_dump(
        manifest, base / MANIFEST_NAME,
        indent=2, ensure_ascii=False, allow_nan=False,
    )
    return target


def export_grid_documents(documents, grids_dir=None, force=False):
    """
    Publica un lote de rejillas reales y actualiza el manifiesto una sola vez.

    Es el equivalente atómico a llamar ``export_grid_document`` en bucle, pero
    evita reescribir el manifiesto por cada fecha (coste cuadrático en un
    backfill de miles de días). Las rutas se resuelven contra PROJECT_ROOT y
    cada documento se valida antes de escribirse.

    Si ``force`` es falso, una rejilla ya publicada con resolución mayor o
    igual no se sustituye: así un backfill reducido no degrada la resolución
    completa de la ventana operativa reciente.

    Devuelve ``(escritas, omitidas)``; cada elemento es ``(model_id, date)``.
    """
    base = _resolve_grids_dir(grids_dir)
    manifest = load_grid_manifest(base)
    written = []
    skipped = []

    for document in documents:
        document = normalize_grid_document(document)
        model_id = document["model_id"]
        date = document["date"]
        relative = Path(model_id) / f"{date}.json"
        target = base / relative
        entry = manifest["grids"].get(model_id, {}).get(date)
        existing_rows = entry.get("n_lats", 0) if isinstance(entry, dict) else 0

        if (not force and target.exists() and
                isinstance(existing_rows, int) and
                existing_rows >= len(document["lats"])):
            skipped.append((model_id, date))
            continue

        atomic_json_dump(
            document, target,
            indent=None, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
        manifest["grids"].setdefault(model_id, {})[date] = {
            "file": relative.as_posix(),
            "forecast_hour": document.get("forecast_hour"),
            "n_lats": len(document["lats"]),
            "n_lons": len(document["lons"]),
            "bytes": target.stat().st_size,
        }
        written.append((model_id, date))

    if written:
        manifest["generated_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        atomic_json_dump(
            manifest, base / MANIFEST_NAME,
            indent=2, ensure_ascii=False, allow_nan=False,
        )
    return written, skipped


def prune_model_grids(model_id, keep_dates, grids_dir=None):
    """
    Elimina del manifiesto y del disco las fechas de un modelo que ya no
    pertenecen al ciclo vigente. Devuelve la lista de fechas eliminadas.
    """
    base = _resolve_grids_dir(grids_dir)
    manifest = load_grid_manifest(base)
    entries = manifest["grids"].get(model_id, {})
    keep = {str(value) for value in keep_dates}
    removed = []

    for date in list(entries.keys()):
        if date in keep:
            continue
        file_path = base / entries[date]["file"]
        if file_path.exists():
            file_path.unlink()
        del entries[date]
        removed.append(date)

    if removed:
        manifest["generated_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        if not entries:
            manifest["grids"].pop(model_id, None)
        atomic_json_dump(
            manifest, base / MANIFEST_NAME,
            indent=2, ensure_ascii=False, allow_nan=False,
        )
    return removed