#!/usr/bin/env python3
"""
download_era5.py
Script para la descarga automatizada de Presión a Nivel del Mar (MSLP) de ERA5 (Copernicus CDS).
Descarga directa en formato NetCDF (.nc) sin compresión .zip innecesaria.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3
"""

import os
import sys
import argparse
from pathlib import Path

# Raíz del proyecto calculada desde la ubicación del script, no desde el CWD.
# Así, ejecutar `python pipeline/download_era5.py` desde cualquier carpeta
# siempre apunta a la estructura real del repositorio.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.file_utils import is_nonempty_file, temp_path_for
from pipeline.paths import resolve_project_path


def year_filepath(output_dir, year):
    """Ruta del NetCDF anual dentro del directorio de destino."""
    return Path(output_dir) / f"era5_mslp_pacifico_{year}.nc"


def is_already_downloaded(filepath):
    """
    Considera descargado un año solo si el archivo existe y tiene contenido.
    Un archivo vacío se trata como incompleto y se vuelve a solicitar.
    """
    return is_nonempty_file(filepath)


def check_cds_credentials():
    """
    Verifica que el usuario tenga configurado ~/.cdsapirc o las variables de entorno CDSAPI_URL y CDSAPI_KEY.
    """
    cdsapirc_path = Path.home() / ".cdsapirc"
    has_file = cdsapirc_path.exists() or Path(os.environ.get("CDSAPI_RC", "")).exists()
    has_env = bool(os.environ.get("CDSAPI_KEY") and os.environ.get("CDSAPI_URL"))

    if not (has_file or has_env):
        print("\n" + "=" * 70)
        print("❌ [ERROR DE AUTENTICACIÓN] No se encontraron credenciales de Copernicus CDS.")
        print("   Configura ~/.cdsapirc o define las variables de entorno CDSAPI_URL y CDSAPI_KEY.")
        print("=" * 70)
        return False
    return True


def download_era5_mslp(years, months, output_dir, synoptic_only=False):
    """
    Descarga Presión a Nivel del Mar (MSLP) para el Anticiclón del Pacífico Sur directamente en .nc.
    Nunca sobrescribe archivos existentes: los años ya presentes se omiten y cada
    descarga se escribe primero en un archivo temporal que solo se renombra al finalizar.
    """
    output_dir = Path(output_dir)

    pending = [y for y in years if not is_already_downloaded(year_filepath(output_dir, y))]
    if not pending:
        print("✅ [COMPLETO] Todos los años solicitados ya están descargados. No hay nada que hacer.")
        return

    if not check_cds_credentials():
        sys.exit(1)

    try:
        import cdsapi
    except ImportError:
        print("[ERROR] Falta instalar la librería cdsapi. Ejecuta:")
        print("pip install cdsapi")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client()

    # Horas a descargar:
    # 24 horas del día (00:00 a 23:00 UTC) para máxima resolución oceanográfica
    if synoptic_only:
        time_steps = ["00:00", "06:00", "12:00", "18:00"]
    else:
        time_steps = [f"{h:02d}:00" for h in range(24)]

    # Días del mes (del 01 al 31)
    days = [f"{d:02d}" for d in range(1, 32)]

    # Cuadripolo geográfico ampliado del Pacífico Suroriental y Cono Sur:
    # Formato ECMWF CDS: [Norte, Oeste, Sur, Este]
    # Dominio APS extendido: 10°S a 56°S y 130°W a 65°W (captura Chiloé, Golfo de Penas, Drake y Patagonia)
    bounding_box = [-10, -130, -56, -65]

    for year in pending:
        nc_filepath = year_filepath(output_dir, year)

        # Verificación previa: si el año ya está en disco, se respeta y se salta.
        if is_already_downloaded(nc_filepath):
            print(f"⏩ [SALTANDO] El año {year} ya existe en {nc_filepath}")
            continue

        # Archivo temporal: la descarga nunca escribe directamente sobre el NetCDF final.
        # Si falla, el archivo final previo (si existiera) queda intacto.
        temp_filepath = temp_path_for(nc_filepath)

        print("\n" + "=" * 60)
        print(f"🌊 [ERA5] Solicitando datos horarios para el año: {year}")
        print(f"📍 Dominio APS Extendido: 10°S a 56°S, 130°W a 65°W")
        print(f"⏱️ 24 horas diarias (00:00 a 23:00 UTC)")
        print(f"💾 Destino directo: {nc_filepath}")
        print("=" * 60)

        dataset = "reanalysis-era5-single-levels"
        request = {
            "product_type": ["reanalysis"],
            "variable": ["mean_sea_level_pressure"],
            "year": [str(year)],
            "month": months,
            "day": days,
            "time": time_steps,
            "area": bounding_box,
            "data_format": "netcdf",
            "download_format": "unarchived"  # Descarga directa sin .zip
        }

        try:
            client.retrieve(dataset, request, str(temp_filepath))
            if not is_already_downloaded(temp_filepath):
                raise RuntimeError("la descarga generó un archivo vacío o inexistente")
            os.replace(temp_filepath, nc_filepath)
            print(f"✅ [ÉXITO] Año {year} descargado directamente en NetCDF: {nc_filepath}")

        except Exception as e:
            if temp_filepath.exists():
                temp_filepath.unlink()
            print(f"❌ [ERROR] Falló la descarga del año {year}: {e}")
            print("El script continuará con los siguientes años...")


def main():
    parser = argparse.ArgumentParser(
        description="Descargador de datos ERA5 (MSLP) en formato NetCDF directo para el Anticiclón del Pacífico Sur (LOFA UACh)"
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=1940,
        help="Año de inicio del registro (por defecto: 1940)"
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=2026,
        help="Año final del registro (por defecto: 2026)"
    )
    parser.add_argument(
        "--years",
        nargs="+",
        help="Años específicos individuales (ej: --years 2023 2024). Si se define, anula --start-year y --end-year"
    )
    parser.add_argument(
        "--months",
        nargs="+",
        default=[f"{m:02d}" for m in range(1, 13)],
        help="Meses en dos dígitos (ej: --months 01 02 03). Por defecto: todos los meses"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/raw/mean_sea_level_pressure",
        help="Directorio de destino. Las rutas relativas se resuelven desde la raíz del proyecto "
             "(por defecto: data/raw/mean_sea_level_pressure)"
    )
    parser.add_argument(
        "--synoptic-only",
        action="store_true",
        help="Descargar solo 4 horas sinópticas (00, 06, 12, 18 UTC) en vez de las 24 horas completas"
    )

    args = parser.parse_args()

    # Determinar la lista de años a procesar (sin duplicados, conservando el orden)
    if args.years:
        years_to_download = list(dict.fromkeys(int(y) for y in args.years))
    else:
        years_to_download = list(range(args.start_year, args.end_year + 1))

    if not years_to_download:
        print("❌ [ERROR] No se definió ningún año para descargar.")
        return

    output_dir = resolve_project_path(args.output_dir)

    # Verificar qué años ya existen ANTES de solicitar nada a Copernicus.
    years_missing = [
        year for year in years_to_download
        if not is_already_downloaded(year_filepath(output_dir, year))
    ]
    years_present = len(years_to_download) - len(years_missing)

    print(f"📋 Plan de descarga: {len(years_to_download)} años solicitados "
          f"({years_to_download[0]} a {years_to_download[-1]})")
    print(f"📂 Carpeta de destino: {output_dir}")
    print(f"✅ Años ya descargados (se respetarán y omitirán): {years_present}")

    if not years_missing:
        print("🎉 [COMPLETO] No falta ningún año por descargar. No se solicitó nada a Copernicus.")
        return

    print(f"⬇️  Años faltantes en cola: {len(years_missing)} "
          f"({', '.join(str(y) for y in years_missing)})")

    download_era5_mslp(
        years=years_to_download,
        months=args.months,
        output_dir=output_dir,
        synoptic_only=args.synoptic_only
    )


if __name__ == "__main__":
    main()
