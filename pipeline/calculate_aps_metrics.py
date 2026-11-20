#!/usr/bin/env python3
"""
Pipeline de Cálculo Científico de Métricas del Anticiclón del Pacífico Sur (APS / ASPS)
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3

Versión 5.3 Definitiva:
- Erradicación total de aproximaciones empíricas, placeholders y del índice de Bakun.
- Par Dinámico: Núcleo Submalla 2D (fit_quadratic_2d) y Centroide Barométrico Adaptativo.
- Métricas Termodinámicas y Morfológicas: Área A1020, Integral de Volumen I_vol y Espesor Efectivo H_eff.
- Diagnóstico Geodésico de Desacople: Distancia D_nc y Acimut Náutico θ.
- Monitoreo Sinóptico en Caja Norpatagonia ([-45°S, -41°S] x [-78°W, -72°W]).
- Convolución normalizada marina y máscara costera estricta Natural Earth 10m.
- Normal Estándar Climatológica OMM 1994–2023 (era satelital 4D-Var moderna).
"""

import os
import sys
import glob
import json
import argparse
import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

# Asegurar importación de los módulos del pipeline
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.paths import ensure_parent_dir, resolve_project_path
from pipeline.file_utils import atomic_csv_dump, atomic_json_dump
from pipeline.compute_climatology import (
    generate_doy_climatology_series,
    load_wmo_climatology,
)
from pipeline.spatial_geometry import (
    download_and_load_natural_earth_10m,
    compute_cell_areas_km2,
    generate_ocean_mask_10m,
    normalized_convolution_ocean,
    EARTH_RADIUS_KM
)
from pipeline.aps_metrics import (
    TRACK_LAT_NORTH,
    TRACK_LAT_SOUTH,
    TRACK_LON_WEST,
    TRACK_LON_EAST,
    PATAGONIA_LAT_MIN,
    PATAGONIA_LAT_MAX,
    PATAGONIA_LON_MIN,
    PATAGONIA_LON_MAX,
    P_THRESHOLD,
    R_EARTH_KM,
    fit_quadratic_2d,
    compute_morphology_and_mass_metrics,
    compute_decoupling_vector,
    compute_patagonia_box_pressure,
    compute_daily_aps_metrics,
    classify_regime,
    rmse,
    bias,
    pearson_r,
    willmott_d,
    mean_geodesic_distance,
)
from pipeline.validation_metrics import (
    build_validation_metrics,
    load_gfs_history,
)

# La climatología mensual OMM 1994-2023 se carga desde
# data/processed/wmo_climatology_1994_2023.json. No existe respaldo hardcodeado.


# Las funciones físicas del motor común viven en pipeline/aps_metrics.py.
# Se importan arriba para conservar los alias de compatibilidad usados por tests
# y scripts históricos (fit_quadratic_2d, compute_morphology_and_mass_metrics,
# compute_decoupling_vector, compute_patagonia_box_pressure).
# La interpolación diaria de la climatología vive en pipeline/compute_climatology.py
# y se importa arriba para evitar duplicación.


def process_netcdf_files(input_dir, cache_csv_path, recompute_all=False, start_year=None, end_year=None):
    """
    Procesa incrementalmente los archivos NetCDF de ERA5 aplicando la matemática V5.3.
    """
    try:
        import xarray as xr
    except ImportError:
        print("[ERROR] xarray no está instalado en el entorno. Ejecuta: pip install xarray netcdf4")
        sys.exit(1)

    nc_pattern = os.path.join(input_dir, "era5_mslp_pacifico_*.nc")
    all_nc_files = [f for f in glob.glob(nc_pattern) if not os.path.basename(f).startswith(("#", "."))]
    all_nc_files.sort()

    if not all_nc_files:
        print(f"[AVISO] No se encontraron archivos NetCDF en {input_dir}.")
        return None

    # Filtrar por año si se especifica
    if start_year is not None or end_year is not None:
        filtered = []
        for f in all_nc_files:
            try:
                y = int(os.path.basename(f).replace("era5_mslp_pacifico_", "").replace(".nc", ""))
                if (start_year is None or y >= start_year) and (end_year is None or y <= end_year):
                    filtered.append(f)
            except ValueError:
                pass
        all_nc_files = filtered

    print(f"\n🌊 [PIPELINE V5.3] Se procesarán {len(all_nc_files)} archivos NetCDF en {input_dir}.")

    # Inicializar máscara y geometría
    print("🌍 [GEOMETRÍA] Cargando máscara continental Natural Earth 10m...")
    land_union = download_and_load_natural_earth_10m()
    print("✓ Máscara Natural Earth 10m cargada exitosamente.")

    # Cargar caché si existe y verificar que sea formato V5.3
    existing_df = None
    processed_years = set()
    
    if recompute_all:
        print("🔄 [RECOMPUTAR] Bandera --recompute-all activada. Se ignorará la caché previa.")
    elif os.path.exists(cache_csv_path):
        try:
            existing_df = pd.read_csv(cache_csv_path)
            # Requisitos de esquema V5.3: p_max_fit, area_1020, dist_decoupling_km
            has_v53_columns = all(col in existing_df.columns for col in [
                "p_max_fit", "lat_core", "lon_core", "lat_centroid", "lon_centroid",
                "area_1020", "vol_integral", "dist_decoupling_km", "p_patagonia"
            ])
            
            if not has_v53_columns:
                print("⚠️ [CACHÉ OBSOLETA] La caché carece de las columnas de Par Dinámico V5.3. Invalidando...")
                existing_df = None
            else:
                processed_years = set(existing_df["year"].unique())
                print(f"📦 [CACHÉ V5.3 VÁLIDA] Se encontraron {len(processed_years)} años ya procesados con submalla y desacople.")
        except Exception as e:
            print(f"[AVISO] No se pudo leer caché existente ({e}), se reprocesará.")
            existing_df = None

    new_rows = []
    
    # Procesar cada NetCDF
    for filepath in all_nc_files:
        filename = os.path.basename(filepath)
        try:
            year_int = int(filename.replace("era5_mslp_pacifico_", "").replace(".nc", ""))
        except ValueError:
            continue

        if year_int in processed_years:
            continue

        print(f"⚙️  Procesando año {year_int} ({filename})...")
        try:
            with xr.open_dataset(filepath) as ds:
                time_dim = "valid_time" if "valid_time" in ds.dims else "time"
                
                # Recorte al dominio físico del APS [-48°S, -18°S] x [-120°W, -70°W]
                sub = ds["msl"].sel(
                    latitude=slice(TRACK_LAT_NORTH, TRACK_LAT_SOUTH),
                    longitude=slice(TRACK_LON_WEST, TRACK_LON_EAST)
                )

                # Conversión de Pascales a Hectopascales y promedio diario
                daily_da = (sub / 100.0).resample({time_dim: "1D"}).mean(dim=time_dim).compute()

                lats = sub["latitude"].values
                lons = sub["longitude"].values
                time_vals = daily_da[time_dim].values

                # Geometría esférica de celda y máscara oceánica
                dA = compute_cell_areas_km2(lats, lons)
                ocean_mask = generate_ocean_mask_10m(lats, lons, land_union)

                for i, t in enumerate(time_vals):
                    date_str = str(t)[:10]
                    grid_raw = daily_da[i].values.copy()

                    metrics = compute_daily_aps_metrics(
                        grid_raw, lats, lons, date=date_str,
                        land_union=land_union, cell_areas=dA,
                        ocean_mask=ocean_mask, sigma=1.0,
                    )
                    if metrics is None:
                        print(f"⚠️  Sin puntos oceánicos válidos para {date_str}; se omite.")
                        continue

                    dt = pd.to_datetime(date_str)
                    new_rows.append({
                        "date": date_str,
                        "year": dt.year,
                        "month": dt.month,
                        "day": dt.day,
                        "day_of_year": dt.dayofyear,
                        "p_max_fit": metrics["p_max_fit"],
                        "lat_core": metrics["lat_core"],
                        "lon_core": metrics["lon_core"],
                        "lat_centroid": metrics["lat_centroid"],
                        "lon_centroid": metrics["lon_centroid"],
                        "area_1020": metrics["area_1020"],
                        "vol_integral": metrics["vol_integral"],
                        "h_eff": metrics["h_eff"],
                        "dist_decoupling_km": metrics["dist_decoupling_km"],
                        "azimuth_deg": metrics["azimuth_deg"],
                        "p_patagonia": metrics["p_patagonia"],
                    })

        except Exception as e:
            print(f"❌ [ERROR] Falló procesamiento de {filename}: {e}")

    # Combinar registros nuevos con caché
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        if existing_df is not None:
            new_years = set(new_df["year"].unique())
            existing_df = existing_df[~existing_df["year"].isin(new_years)]
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = new_df
        combined_df = combined_df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    elif existing_df is not None:
        combined_df = existing_df
    else:
        return None

    # Guardar caché con escritura atómica
    atomic_csv_dump(combined_df, cache_csv_path, index=False)
    print(f"✅ [CACHÉ V5.3] Base consolidada con {len(combined_df)} días guardada en {cache_csv_path}")

    return combined_df


def extract_latest_spatial_grid(input_dir, df):
    """
    Extrae la última cuadrícula espacial 2D submuestreada a 0.5° para mapas.
    Sincroniza el archivo de origen con el último año presente en df.
    """
    import xarray as xr

    # 1. Identificar el archivo NetCDF correspondiente a la última fecha real de df
    last_date_str = str(df.iloc[-1]["date"])
    last_year = int(last_date_str[:4])
    expected_file = Path(input_dir) / f"era5_mslp_pacifico_{last_year}.nc"

    if expected_file.exists():
        latest_file = str(expected_file)
    else:
        nc_pattern = os.path.join(input_dir, "era5_mslp_pacifico_*.nc")
        valid_files = [f for f in glob.glob(nc_pattern) if not os.path.basename(f).startswith(("#", "."))]
        valid_files.sort()
        if not valid_files:
            return None
        latest_file = valid_files[-1]

    print(f"🗺️  Generando cuadrícula espacial para mapas a partir de: {os.path.basename(latest_file)}")

    with xr.open_dataset(latest_file) as ds:
        time_dim = "valid_time" if "valid_time" in ds.dims else "time"
        
        # Promedio diario robusto (compatible con 24h o con --synoptic-only de 4h)
        latest_slp_da = (ds["msl"] / 100.0).resample({time_dim: "1D"}).mean(dim=time_dim).isel({time_dim: -1})
        
        # Submuestreo a 0.5° para transferencia web ligera
        sampled = latest_slp_da.sel(
            latitude=slice(TRACK_LAT_NORTH, TRACK_LAT_SOUTH, 2),
            longitude=slice(TRACK_LON_WEST, TRACK_LON_EAST, 2)
        ).compute()

        lats = [float(round(y, 2)) for y in sampled["latitude"].values]
        lons = [float(round(x, 2)) for x in sampled["longitude"].values]
        slp_grid = [[float(round(val, 2)) if not np.isnan(val) else None for val in row] for row in sampled.values]

        mean_val = np.nanmean(sampled.values)
        anomaly_grid = [[float(round(val - mean_val, 2)) if val is not None else None for val in row] for row in slp_grid]

        return {
            "date": df.iloc[-1]["date"],
            "lats": lats,
            "lons": lons,
            "current_slp": slp_grid,
            "current_anomaly": anomaly_grid
        }


def _num_or_none(value, digits):
    """
    Convierte un escalar a float redondeado o a None si es ausente.
    Garantiza que el JSON publicado no contenga NaN (no válido para JSON.parse).
    """
    if value is None:
        return None
    if pd.isna(value):
        return None
    return float(round(float(value), digits))


def build_dashboard_dataset_v53(df, spatial_grid, era5_cache_df=None,
                                gfs_history_df=None, climatology=None):
    """
    Construye la estructura canónica JSON V5.3 y el DataFrame Multimodelo Consolidado.
    Totalmente libre de Bakun y sustentado en la Climatología Normal OMM 1994–2023.
    Incluye validation_metrics calculado por fecha exacta desde datos reales.
    """
    dates_list = df["date"].tolist()
    doy_series = df["day_of_year"]

    # Climatología canónica cargada desde JSON; falla si no existe.
    if climatology is None:
        climatology = load_wmo_climatology()

    # Interpoladores climatológicos continuos por día del año
    clim_interp = generate_doy_climatology_series(dates_list, climatology)
    
    clim_p_max = [_num_or_none(clim_interp["p_max"](d), 2) for d in doy_series]
    clim_lat_core = [_num_or_none(clim_interp["lat_core"](d), 2) for d in doy_series]
    clim_lon_core = [_num_or_none(clim_interp["lon_core"](d), 2) for d in doy_series]
    clim_lat_cent = [_num_or_none(clim_interp["lat_centroid"](d), 2) for d in doy_series]
    clim_lon_cent = [_num_or_none(clim_interp["lon_centroid"](d), 2) for d in doy_series]
    clim_area_1020 = [_num_or_none(clim_interp["area_1020"](d), 3) for d in doy_series]
    clim_vol_integral = [_num_or_none(clim_interp["vol_integral"](d), 3) for d in doy_series]
    clim_h_eff = [_num_or_none(clim_interp["h_eff"](d), 2) for d in doy_series]
    clim_dist_dec = [_num_or_none(clim_interp["dist_decoupling_km"](d), 1) for d in doy_series]
    clim_azimuth = [_num_or_none(clim_interp["azimuth_deg"](d), 1) for d in doy_series]
    clim_patagonia = [_num_or_none(clim_interp["p_patagonia"](d), 2) for d in doy_series]

    # Modelo ERA5 Observado
    era5_model = {
        "id": "era5_reanalysis",
        "name": "ECMWF ERA5 Reanálisis",
        "description": "Serie climática observada con asimilación 4D-Var de scatterómetros y altimetría radar",
        "is_forecast": False,
        "dates": dates_list,
        "p_max_fit": [_num_or_none(x, 2) for x in df["p_max_fit"].tolist()],
        "lat_core": [_num_or_none(x, 2) for x in df["lat_core"].tolist()],
        "lon_core": [_num_or_none(x, 2) for x in df["lon_core"].tolist()],
        "lat_centroid": [_num_or_none(x, 2) for x in df["lat_centroid"].tolist()],
        "lon_centroid": [_num_or_none(x, 2) for x in df["lon_centroid"].tolist()],
        "area_1020": [_num_or_none(x, 3) for x in df["area_1020"].tolist()],
        "vol_integral": [_num_or_none(x, 3) for x in df["vol_integral"].tolist()],
        "h_eff": [_num_or_none(x, 2) for x in df["h_eff"].tolist()],
        "dist_decoupling_km": [_num_or_none(x, 1) for x in df["dist_decoupling_km"].tolist()],
        "azimuth_deg": [_num_or_none(x, 1) for x in df["azimuth_deg"].tolist()],
        "p_patagonia": [_num_or_none(x, 2) for x in df["p_patagonia"].tolist()],
        "latest": {
            "date": df.iloc[-1]["date"],
            "p_max_fit": _num_or_none(df.iloc[-1]["p_max_fit"], 2),
            "lat_core": _num_or_none(df.iloc[-1]["lat_core"], 2),
            "lon_core": _num_or_none(df.iloc[-1]["lon_core"], 2),
            "lat_centroid": _num_or_none(df.iloc[-1]["lat_centroid"], 2),
            "lon_centroid": _num_or_none(df.iloc[-1]["lon_centroid"], 2),
            "area_1020": _num_or_none(df.iloc[-1]["area_1020"], 3),
            "vol_integral": _num_or_none(df.iloc[-1]["vol_integral"], 3),
            "h_eff": _num_or_none(df.iloc[-1]["h_eff"], 2),
            "dist_decoupling_km": _num_or_none(df.iloc[-1]["dist_decoupling_km"], 1),
            "azimuth_deg": _num_or_none(df.iloc[-1]["azimuth_deg"], 1),
            "p_patagonia": _num_or_none(df.iloc[-1]["p_patagonia"], 2)
        }
    }

    # Modelo Climatología Normal OMM 1994–2023
    clim_model = {
        "id": "wmo_climatology_1994_2023",
        "name": "Climatología Normal OMM (1994–2023)",
        "description": "Línea base estándar multidecadal OMM de 30 años (era satelital moderna 4D-Var)",
        "is_forecast": False,
        "dates": dates_list,
        "p_max_fit": clim_p_max,
        "lat_core": clim_lat_core,
        "lon_core": clim_lon_core,
        "lat_centroid": clim_lat_cent,
        "lon_centroid": clim_lon_cent,
        "area_1020": clim_area_1020,
        "vol_integral": clim_vol_integral,
        "h_eff": clim_h_eff,
        "dist_decoupling_km": clim_dist_dec,
        "azimuth_deg": clim_azimuth,
        "p_patagonia": clim_patagonia,
        "latest": {
            "date": df.iloc[-1]["date"],
            "p_max_fit": clim_p_max[-1],
            "lat_core": clim_lat_core[-1],
            "lon_core": clim_lon_core[-1],
            "lat_centroid": clim_lat_cent[-1],
            "lon_centroid": clim_lon_cent[-1],
            "area_1020": clim_area_1020[-1],
            "vol_integral": clim_vol_integral[-1],
            "h_eff": clim_h_eff[-1],
            "dist_decoupling_km": clim_dist_dec[-1],
            "azimuth_deg": clim_azimuth[-1],
            "p_patagonia": clim_patagonia[-1]
        }
    }

    models_dict = {
        "ERA5 Reanálisis": era5_model,
        "Climatología Normal OMM": clim_model
    }

    # Asimilar pronóstico GFS solo si trae el esquema V5.3 completo.
    # Nunca se inventan centroides, áreas, volúmenes ni presión Norpatagonia.
    gfs_forecast_block = None
    gfs_forecast_path = resolve_project_path("data/processed/gfs_forecast_aps.json")
    gfs_required_fields = [
        "dates", "forecast_hours", "p_max_fit", "lat_core", "lon_core",
        "lat_centroid", "lon_centroid", "area_1020", "vol_integral", "h_eff",
        "dist_decoupling_km", "azimuth_deg", "p_patagonia", "regime",
    ]
    if os.path.exists(gfs_forecast_path):
        try:
            with open(gfs_forecast_path, "r", encoding="utf-8") as gf:
                gfs_json = json.load(gf)
            fc = gfs_json.get("forecast")
            if not isinstance(fc, dict):
                raise KeyError("El JSON GFS no contiene el bloque 'forecast'.")

            missing = [key for key in gfs_required_fields if key not in fc]
            if missing:
                raise KeyError(
                    "El JSON GFS está incompleto; faltan campos V5.3: "
                    + ", ".join(missing)
                    + ". Regenéralo con pipeline/download_gfs_forecast.py."
                )

            lengths = {
                key: len(fc[key]) for key in gfs_required_fields
            }
            if len(set(lengths.values())) != 1:
                raise ValueError(f"El JSON GFS tiene longitudes inconsistentes: {lengths}")

            gfs_model_data = {
                "id": "noaa_gfs_forecast",
                "name": "NOAA GFS Operativo (+7 Días)",
                "description": (
                    "Pronóstico sinóptico global del National Centers for Environmental "
                    f"Prediction (Ciclo {gfs_json.get('cycle', 'N/D')})"
                ),
                "is_forecast": True,
                "cycle": gfs_json.get("cycle"),
                "forecast_hours": fc["forecast_hours"],
                "dates": fc["dates"],
                "p_max_fit": fc["p_max_fit"],
                "lat_core": fc["lat_core"],
                "lon_core": fc["lon_core"],
                "lat_centroid": fc["lat_centroid"],
                "lon_centroid": fc["lon_centroid"],
                "area_1020": fc["area_1020"],
                "vol_integral": fc["vol_integral"],
                "h_eff": fc["h_eff"],
                "dist_decoupling_km": fc["dist_decoupling_km"],
                "azimuth_deg": fc["azimuth_deg"],
                "p_patagonia": fc["p_patagonia"],
                "regime": fc["regime"],
                "latest": {
                    "date": fc["dates"][-1],
                    "forecast_hours": fc["forecast_hours"][-1],
                    "p_max_fit": fc["p_max_fit"][-1],
                    "lat_core": fc["lat_core"][-1],
                    "lon_core": fc["lon_core"][-1],
                    "lat_centroid": fc["lat_centroid"][-1],
                    "lon_centroid": fc["lon_centroid"][-1],
                    "area_1020": fc["area_1020"][-1],
                    "vol_integral": fc["vol_integral"][-1],
                    "h_eff": fc["h_eff"][-1],
                    "dist_decoupling_km": fc["dist_decoupling_km"][-1],
                    "azimuth_deg": fc["azimuth_deg"][-1],
                    "p_patagonia": fc["p_patagonia"][-1],
                    "regime": fc["regime"][-1],
                },
            }
            models_dict["NOAA GFS Pronóstico"] = gfs_model_data
            gfs_forecast_block = fc
        except Exception as e:
            print(f"[AVISO] GFS omitido: {e}")

    # DataFrame Multimodelo Consolidado para descarga científica directa
    multimodel_df = pd.DataFrame({
        "date": dates_list,
        "day_of_year": doy_series.tolist(),
        "p_max_fit": df["p_max_fit"],
        "lat_core": df["lat_core"],
        "lon_core": df["lon_core"],
        "lat_centroid": df["lat_centroid"],
        "lon_centroid": df["lon_centroid"],
        "area_1020": df["area_1020"],
        "vol_integral": df["vol_integral"],
        "h_eff": df["h_eff"],
        "dist_decoupling_km": df["dist_decoupling_km"],
        "azimuth_deg": df["azimuth_deg"],
        "p_patagonia": df["p_patagonia"],
        "clim_p_max": clim_p_max,
        "clim_lat_core": clim_lat_core,
        "clim_lon_core": clim_lon_core,
        "clim_area_1020": clim_area_1020,
        "clim_dist_decoupling_km": clim_dist_dec
    })

    # Métricas objetivas de validación (Fase 3): referencias explícitas y
    # alineación por fecha exacta. Nunca se publican valores sintéticos.
    validation_rows = build_validation_metrics(
        df,
        climatology,
        gfs_forecast=gfs_forecast_block,
        gfs_history_frame=gfs_history_df,
        era5_cache_frame=era5_cache_df if era5_cache_df is not None else df,
    )

    # Dataset JSON final
    dataset = {
        "metadata": {
            "project": "Observatorio Científico del Anticiclón del Pacífico Sur (APS / ASPS)",
            "institution": "Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)",
            "director_cientifico": "Dr. José Garcés Vargas",
            "version": "5.3",
            "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "climatology_period": "1994-2023 (WMO 30-Year Standard Normal)",
            "climatology_source": "data/processed/wmo_climatology_1994_2023.json",
            "willmott_reference": (
                "Normal OMM 1994-2023 para concordancia histórica; "
                "ERA5 verificante para skill de pronóstico"
            ),
            "domain": {
                "lat_north": TRACK_LAT_NORTH,
                "lat_south": TRACK_LAT_SOUTH,
                "lon_west": TRACK_LON_WEST,
                "lon_east": TRACK_LON_EAST
            },
            "units": {
                "pressure": "hPa",
                "coordinates": "grados decimales (WGS84)",
                "area": "10^6 km^2",
                "volume": "hPa * 10^6 km^2",
                "distance": "km",
                "bearing": "grados náuticos (0=N, 90=E, 180=S, 270=W)"
            }
        },
        "climatology_monthly": climatology,
        "models": models_dict,
        "validation_metrics": validation_rows,
        "spatial_grid": spatial_grid
    }

    return dataset, multimodel_df


def main():
    parser = argparse.ArgumentParser(description="Pipeline V5.3 - Métricas del Anticiclón del Pacífico Sur (LOFA UACh)")
    parser.add_argument("--input-dir", type=str, default="data/raw/mean_sea_level_pressure",
                        help="Directorio con archivos NetCDF. Las rutas relativas se resuelven desde la raíz del proyecto")
    parser.add_argument("--output", type=str, default="data/processed/latest_aps_data.json",
                        help="Ruta del archivo JSON de salida. Las rutas relativas se resuelven desde la raíz del proyecto")
    parser.add_argument("--cache-csv", type=str, default="data/processed/era5_daily_aps_metrics.csv",
                        help="Ruta de caché CSV de series diarias. Las rutas relativas se resuelven desde la raíz del proyecto")
    parser.add_argument("--recompute-all", action="store_true", help="Fuerza reprocesamiento completo ignorando caché previa")
    parser.add_argument("--start-year", type=int, default=None, help="Año de inicio de procesamiento")
    parser.add_argument("--end-year", type=int, default=None, help="Año final de procesamiento")
    parser.add_argument("--active-start-year", type=int, default=1993,
                        help="Primer año publicado en JSON y CSVs web (por defecto 1993)")
    parser.add_argument("--active-end-year", type=int, default=datetime.date.today().year,
                        help="Último año publicado en JSON y CSVs web (por defecto el año actual)")

    args = parser.parse_args()

    # Resolver rutas una sola vez: relativas a la raíz del proyecto, absolutas tal cual.
    input_dir = resolve_project_path(args.input_dir)
    output_path = resolve_project_path(args.output)
    cache_csv_path = resolve_project_path(args.cache_csv)

    # 1. Procesar NetCDFs con la matemática V5.3
    df = process_netcdf_files(
        input_dir, cache_csv_path,
        recompute_all=args.recompute_all,
        start_year=args.start_year,
        end_year=args.end_year
    )
    
    if df is None or len(df) == 0:
        print("[ERROR] No se pudieron generar métricas. Verifica la carpeta de entrada.")
        print(f"        Ruta esperada: {input_dir}")
        print("        Descarga primero los datos ERA5 con pipeline/download_era5.py.")
        sys.exit(1)

    # 2. Ventana activa publicada: el caché completo se conserva en data/processed.
    active_df = df[
        (df["year"] >= args.active_start_year)
        & (df["year"] <= args.active_end_year)
    ].copy().reset_index(drop=True)

    if len(active_df) == 0:
        print(f"[ERROR] La ventana activa {args.active_start_year}-{args.active_end_year} no contiene datos.")
        sys.exit(1)

    # 3. Rejilla espacial 2D más reciente
    spatial_grid = extract_latest_spatial_grid(input_dir, df)

    # 4. Construir Dataset JSON y DataFrame Multimodelo
    gfs_history_df = load_gfs_history(
        resolve_project_path("data/processed/gfs_forecast_history.csv")
    )
    dataset, multimodel_df = build_dashboard_dataset_v53(
        active_df,
        spatial_grid,
        era5_cache_df=df,
        gfs_history_df=gfs_history_df,
    )
    dataset["metadata"]["active_window"] = {
        "start_year": args.active_start_year,
        "end_year": args.active_end_year,
        "start_date": str(active_df.iloc[0]["date"]),
        "end_date": str(active_df.iloc[-1]["date"]),
        "n_days": int(len(active_df)),
    }

    # 5. Guardar salidas en data/processed/ y web/data/ con escritura atómica
    atomic_json_dump(dataset, output_path, indent=2, ensure_ascii=False, allow_nan=False)
    print(f"✅ [ÉXITO] Archivo web generado en: {output_path}")

    web_json_path = resolve_project_path("web/data/latest_aps_data.json")
    atomic_json_dump(dataset, web_json_path, indent=2, ensure_ascii=False, allow_nan=False)
    print(f"✅ [ÉXITO] Copia frontend generada en: {web_json_path}")

    web_csv_path = resolve_project_path("web/data/era5_daily_aps_metrics.csv")
    atomic_csv_dump(active_df, web_csv_path, index=False)

    multimodel_csv_path = resolve_project_path("web/data/aps_multimodel_metrics_lofa.csv")
    atomic_csv_dump(multimodel_df, multimodel_csv_path, index=False)
    print(f"✅ [ÉXITO] CSV Multimodelo consolidado para descarga disponible en: {multimodel_csv_path}")


if __name__ == "__main__":
    main()
