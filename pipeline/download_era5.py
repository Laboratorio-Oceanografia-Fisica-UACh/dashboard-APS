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


def check_cds_credentials():
    """
    Verifica que el usuario tenga configurado el archivo ~/.cdsapirc
    necesario para autenticarse con la API de Copernicus.
    """
    cdsapirc_path = Path.home() / ".cdsapirc"
    if not cdsapirc_path.exists():
        print("\n" + "=" * 70)
        print("❌ [ERROR DE AUTENTICACIÓN] No se encontró el archivo de credenciales ~/.cdsapirc")
        print("=" * 70)
        return False
    return True


def download_era5_mslp(years, months, output_dir, synoptic_only=False):
    """
    Descarga Presión a Nivel del Mar (MSLP) para el Anticiclón del Pacífico Sur directamente en .nc.
    """
    if not check_cds_credentials():
        sys.exit(1)

    try:
        import cdsapi
    except ImportError:
        print("[ERROR] Falta instalar la librería cdsapi. Ejecuta:")
        print("pip install cdsapi")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
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

    for year in years:
        nc_filename = f"era5_mslp_pacifico_{year}.nc"
        nc_filepath = os.path.join(output_dir, nc_filename)

        # Si el archivo ya existe por haber sido descargado previamente en esta corrida, se omite
        if os.path.exists(nc_filepath):
            print(f"⏩ [SALTANDO] El año {year} ya existe en {nc_filepath}")
            continue

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
            client.retrieve(dataset, request, nc_filepath)
            print(f"✅ [ÉXITO] Año {year} descargado directamente en NetCDF: {nc_filepath}")

        except Exception as e:
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
        help="Directorio de destino (por defecto: data/raw/mean_sea_level_pressure)"
    )
    parser.add_argument(
        "--synoptic-only",
        action="store_true",
        help="Descargar solo 4 horas sinópticas (00, 06, 12, 18 UTC) en vez de las 24 horas completas"
    )

    args = parser.parse_args()

    # Determinar la lista de años a procesar
    if args.years:
        years_to_download = [int(y) for y in args.years]
    else:
        years_to_download = list(range(args.start_year, args.end_year + 1))

    print(f"📋 Plan de descarga: {len(years_to_download)} años en cola ({years_to_download[0]} a {years_to_download[-1]})")
    print(f"📂 Carpeta de destino: {args.output_dir}")

    download_era5_mslp(
        years=years_to_download,
        months=args.months,
        output_dir=args.output_dir,
        synoptic_only=args.synoptic_only
    )


if __name__ == "__main__":
    main()
