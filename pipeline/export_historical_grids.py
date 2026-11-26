#!/usr/bin/env python3
"""
Exportación diaria de campos 2D reales de presión marina para el cliente web.

Laboratorio de Oceanografía Física (LOFA) - Instituto de Ciencias Marinas y
Limnológicas (ICML) - Universidad Austral de Chile (UACh).
Licencia: GNU AGPLv3.

Este módulo NO modela ni sintetiza isóbaras: cada documento publicado es el
promedio diario del campo MSL real contenido en un NetCDF de ERA5, muestreado
en el dominio físico del APS. El trazado de contornos lo realiza el cliente
con Marching Squares sobre esos datos (web/js/maps.js).

Criterio de resolución (opción híbrida):
- Ventana operativa reciente (``--recent-days``): 0.5°, 61x101 celdas.
- Resto del histórico: 1.0°, 31x51 celdas.

Un backfill reducido jamás degrada una rejilla completa ya publicada, porque
``export_grid_documents`` conserva la de mayor resolución salvo ``--force``.
"""

import argparse
import datetime
import glob
import os
import re
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.aps_metrics import (
    TRACK_LAT_NORTH,
    TRACK_LAT_SOUTH,
    TRACK_LON_WEST,
    TRACK_LON_EAST,
)
from pipeline.file_utils import is_nonempty_file
from pipeline.grid_export import build_grid_document, export_grid_documents
from pipeline.paths import resolve_project_path

# Paso de muestreo en celdas nativas de 0.25° del producto ERA5.
FULL_STRIDE = 2   # 0.5° -> 61x101
HISTORICAL_STRIDE = 4  # 1.0° -> 31x51

ANNUAL_NAME = re.compile(r"^era5_mslp_pacifico_(\d{4})\.nc$")
MONTHLY_NAME = re.compile(r"^era5_mslp_pacifico_(\d{4})_(\d{2})\.nc$")


def discover_netcdf_files(input_dir, include_monthly=True):
    """
    Devuelve la lista ordenada de NetCDF ERA5 anuales (y mensuales, si se
    permiten) presentes en ``input_dir``. A diferencia del bucle de métricas,
    este exportador acepta ambos convenios de nomenclatura.
    """
    patron = os.path.join(resolve_project_path(input_dir), "era5_mslp_pacifico_*.nc")
    encontrados = []
    for ruta in sorted(glob.glob(patron)):
        nombre = os.path.basename(ruta)
        if not is_nonempty_file(ruta) or nombre.startswith(("#", ".")):
            continue
        if ANNUAL_NAME.match(nombre) or (include_monthly and MONTHLY_NAME.match(nombre)):
            encontrados.append(ruta)
    return encontrados


def scan_time_ranges(rutas):
    """
    Lee solo la coordenada temporal de cada NetCDF y devuelve
    ``(rangos, fecha_maxima)`` sin cargar el campo de presión.
    """
    import xarray as xr

    rangos = {}
    fecha_maxima = None
    for ruta in rutas:
        with xr.open_dataset(ruta) as ds:
            dim = "valid_time" if "valid_time" in ds.dims else "time"
            tiempos = np.atleast_1d(ds[dim].values)
            if tiempos.size == 0:
                continue
            inicio = str(tiempos[0])[:10]
            fin = str(tiempos[-1])[:10]
            rangos[ruta] = (inicio, fin)
            if fecha_maxima is None or fin > fecha_maxima:
                fecha_maxima = fin
    return rangos, fecha_maxima


def fecha_corte(fecha_maxima, recent_days):
    """
    Calcula la primera fecha de la ventana de resolución completa.
    ``recent_days <= 0`` desactiva la ventana y todo se publica a 1.0°.
    """
    if fecha_maxima is None or recent_days <= 0:
        return None
    ultima = datetime.date.fromisoformat(fecha_maxima)
    return (ultima - datetime.timedelta(days=recent_days - 1)).isoformat()


def stride_para_fecha(fecha, corte):
    """Resuelve el muestreo aplicable a una fecha real del dataset."""
    if corte is None:
        return HISTORICAL_STRIDE
    return FULL_STRIDE if fecha >= corte else HISTORICAL_STRIDE


def documentos_diarios(ruta, corte, fecha_inicio=None, fecha_fin=None):
    """
    Genera un documento de rejilla real por cada día del NetCDF.
    El promedio diario y el muestreo se calculan de forma diferida: solo se
    materializa la fecha que se está publicando, para no cargar un año entero
    de MSLP en memoria.
    """
    import xarray as xr

    documentos = []
    with xr.open_dataset(ruta) as ds:
        dim = "valid_time" if "valid_time" in ds.dims else "time"
        diario = (ds["msl"] / 100.0).resample({dim: "1D"}).mean(dim=dim)

        total = diario.sizes.get(dim, 0)
        for indice in range(total):
            paso = diario.isel({dim: indice})
            fecha = str(np.atleast_1d(paso[dim].values)[0])[:10]
            if fecha_inicio and fecha < fecha_inicio:
                continue
            if fecha_fin and fecha > fecha_fin:
                continue

            stride = stride_para_fecha(fecha, corte)
            muestra = paso.sel(
                latitude=slice(TRACK_LAT_NORTH, TRACK_LAT_SOUTH, stride),
                longitude=slice(TRACK_LON_WEST, TRACK_LON_EAST, stride),
            ).squeeze(drop=True).compute()

            valores = np.asarray(muestra.values, dtype=float)
            if valores.ndim != 2:
                print(f"⚠️  {fecha}: dimensión inesperada {valores.shape}; se omite.")
                continue
            media = float(np.nanmean(valores))
            if not np.isfinite(media):
                print(f"⚠️  {fecha}: campo no finito; se omite.")
                continue

            documentos.append(build_grid_document(
                model_id="era5_reanalysis",
                date=fecha,
                lats=muestra["latitude"].values,
                lons=muestra["longitude"].values,
                slp=valores,
                anomaly=valores - media,
                forecast_hour=None,
                anomaly_reference="domain_spatial_mean",
            ))
    return documentos


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Publica una rejilla 2D real por día a partir de NetCDF ERA5. "
            "No genera campos sintéticos ni interpola fechas ausentes."
        )
    )
    parser.add_argument(
        "--input-dir", default="data/raw/mean_sea_level_pressure",
        help="Directorio con los NetCDF de ERA5 (ruta relativa a PROJECT_ROOT).",
    )
    parser.add_argument(
        "--grids-dir", default="web/data/grids",
        help="Directorio destino de rejillas y manifiesto.",
    )
    parser.add_argument("--start-year", type=int, help="Primer año a publicar.")
    parser.add_argument("--end-year", type=int, help="Último año a publicar.")
    parser.add_argument("--start-date", help="Fecha inicial AAAA-MM-DD (opcional).")
    parser.add_argument("--end-date", help="Fecha final AAAA-MM-DD (opcional).")
    parser.add_argument(
        "--recent-days", type=int, default=90,
        help="Días finales que se publican a 0.5° (0 = todo a 1.0°).",
    )
    parser.add_argument(
        "--no-monthly", action="store_true",
        help="Ignorar archivos mensuales era5_mslp_pacifico_AAAA_MM.nc.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Permitir sustituir rejillas completas por versiones reducidas.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Calcular y validar sin escribir archivos.",
    )
    args = parser.parse_args()

    rutas = discover_netcdf_files(args.input_dir, include_monthly=not args.no_monthly)
    if not rutas:
        print(f"[AVISO] No hay NetCDF ERA5 en {args.input_dir}. No se publica nada.")
        return 0

    rangos, fecha_maxima = scan_time_ranges(rutas)
    corte = fecha_corte(fecha_maxima, args.recent_days)
    print(f"🌊 [REJILLAS REALES] {len(rutas)} archivos; última fecha: {fecha_maxima}.")
    print(f"   Resolución completa desde {corte or 'ninguna fecha'} "
          f"({FULL_STRIDE} celdas de paso); resto a {HISTORICAL_STRIDE}.")

    documentos = []
    for ruta in rutas:
        inicio, fin = rangos[ruta]
        anio_inicio = int(inicio[:4])
        anio_fin = int(fin[:4])
        if args.start_year and anio_fin < args.start_year:
            continue
        if args.end_year and anio_inicio > args.end_year:
            continue
        fecha_inicio = args.start_date or (f"{args.start_year:04d}-01-01" if args.start_year else None)
        fecha_fin = args.end_date or (f"{args.end_year:04d}-12-31" if args.end_year else None)
        print(f"⚙️  {os.path.basename(ruta)} ({inicio} → {fin})...")
        documentos.extend(documentos_diarios(ruta, corte, fecha_inicio, fecha_fin))

    if not documentos:
        print("[AVISO] Ningún día cumplió el filtro solicitado.")
        return 0

    completas = sum(1 for d in documentos if len(d["lats"]) > 40)
    print(f"📐 Documentos reales generados: {len(documentos)} "
          f"({completas} a 0.5°, {len(documentos) - completas} a 1.0°).")

    if args.dry_run:
        print("🔎 Modo dry-run: no se escribió ningún archivo.")
        return 0

    escritas, omitidas = export_grid_documents(
        documentos, grids_dir=args.grids_dir, force=args.force
    )
    print(f"✅ Publicadas {len(escritas)} rejillas reales; "
          f"{len(omitidas)} omitidas por resolución igual o superior.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
