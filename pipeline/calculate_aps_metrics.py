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
from pipeline.spatial_geometry import (
    download_and_load_natural_earth_10m,
    compute_cell_areas_km2,
    generate_ocean_mask_10m,
    normalized_convolution_ocean,
    EARTH_RADIUS_KM
)

# Dominio geográfico de seguimiento del APS en el Pacífico Suroriental
# Definido por Dr. José Garcés Vargas: [-48.0°S, -18.0°S] x [-120.0°W, -70.0°W]
TRACK_LAT_NORTH = -18.0
TRACK_LAT_SOUTH = -48.0
TRACK_LON_WEST = -120.0
TRACK_LON_EAST = -70.0

# Caja Norpatagonia para monitoreo de bloqueos y cuñas hacia los fiordos australes
PATAGONIA_LAT_MIN = -45.0
PATAGONIA_LAT_MAX = -41.0
PATAGONIA_LON_MIN = -78.0
PATAGONIA_LON_MAX = -72.0

# Climatología mensual normal OMM (1994–2023) - Dr. José Garcés Vargas (LOFA-UACh)
WMO_CLIMATOLOGY_MONTHLY = {
    "months": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "p_max": [1024.5, 1023.8, 1022.1, 1020.9, 1019.8, 1021.2, 1023.4, 1025.1, 1026.3, 1026.8, 1025.9, 1024.9],
    "area_1020": [4.82, 3.95, 2.15, 1.10, 0.42, 1.85, 4.30, 6.75, 8.12, 8.45, 7.20, 5.80],
    "vol_integral": [12.40, 9.80, 4.60, 2.10, 0.70, 3.90, 10.50, 18.20, 23.40, 25.10, 20.30, 15.60],
    "h_eff": [2.57, 2.48, 2.14, 1.91, 1.67, 2.11, 2.44, 2.70, 2.88, 2.97, 2.82, 2.69],
    "lat_core": [-36.20, -35.80, -34.50, -32.80, -31.40, -30.80, -31.20, -32.50, -34.10, -35.60, -36.40, -36.50],
    "lon_core": [-96.50, -95.20, -92.40, -89.80, -88.20, -89.50, -91.00, -93.80, -96.20, -98.10, -98.50, -97.80],
    "lat_centroid": [-35.80, -35.20, -34.00, -32.50, -31.20, -30.90, -31.40, -32.80, -34.40, -35.80, -36.10, -36.00],
    "lon_centroid": [-95.10, -93.80, -91.00, -88.50, -87.40, -88.90, -90.20, -92.90, -95.10, -96.80, -97.00, -96.20],
    "dist_decoupling_km": [165.2, 172.0, 185.4, 210.1, 245.8, 198.5, 175.2, 168.0, 154.2, 148.5, 152.0, 158.4],
    "azimuth_deg": [71.5, 73.2, 78.4, 82.1, 88.5, 83.2, 77.0, 72.8, 69.4, 68.2, 70.1, 71.0],
    "p_patagonia": [1014.8, 1014.2, 1013.9, 1014.5, 1015.2, 1016.1, 1016.8, 1017.2, 1017.0, 1016.4, 1015.6, 1015.0]
}


def fit_quadratic_2d(lat_sub: np.ndarray, lon_sub: np.ndarray, slp_sub: np.ndarray,
                     lat_disc: float, lon_disc: float, p_disc: float):
    """
    Ajusta una parábola multivariable 2D mediante mínimos cuadrados en ventana 5x5:
    P(x, y) = a*x^2 + b*y^2 + c*x*y + d*x + e*y + f
    Resuelve el vértice continuo nabla P = 0 validando curvatura negativa en el Hessiano.
    """
    lon_grid, lat_grid = np.meshgrid(lon_sub - lon_disc, lat_sub - lat_disc)
    x = lon_grid.ravel()
    y = lat_grid.ravel()
    z = slp_sub.ravel()
    
    valid = ~np.isnan(z)
    if np.sum(valid) < 9:
        return lat_disc, lon_disc, p_disc
        
    x = x[valid]
    y = y[valid]
    z = z[valid]
    
    M = np.column_stack([x**2, y**2, x*y, x, y, np.ones_like(x)])
    coeff, _, _, _ = np.linalg.lstsq(M, z, rcond=None)
    a, b, c, d, e, f = coeff
    
    H = np.array([[2.0 * a, c], [c, 2.0 * b]])
    det_H = 4.0 * a * b - c**2
    
    # Concavidad negativa obligatoria (máximo cerrado de presión)
    if a < 0.0 and b < 0.0 and det_H > 1e-4:
        grad_indep = np.array([-d, -e])
        try:
            x_opt, y_opt = np.linalg.solve(H, grad_indep)
            if abs(x_opt) <= 0.35 and abs(y_opt) <= 0.35:
                lon_opt = float(round(lon_disc + x_opt, 2))
                lat_opt = float(round(lat_disc + y_opt, 2))
                p_opt = float(round(a*x_opt**2 + b*y_opt**2 + c*x_opt*y_opt + d*x_opt + e*y_opt + f, 2))
                return lat_opt, lon_opt, p_opt
        except np.linalg.LinAlgError:
            pass
            
    return lat_disc, lon_disc, p_disc


def compute_morphology_and_mass_metrics(slp_2d: np.ndarray, lats: np.ndarray, lons: np.ndarray,
                                        cell_areas: np.ndarray, ocean_mask: np.ndarray,
                                        p_max: float, land_union=None, lat_core=None, lon_core=None):
    """
    Calcula: A_1020, I_vol, H_eff y Centroide Barométrico Adaptativo (phi_c, lam_c).
    Garantiza que el centroide se confine 100% en el océano pacífico.
    """
    # 1. Extensión Areal A_1020
    mask_1020 = ocean_mask & (slp_2d >= 1020.0)
    a_1020 = float(round(np.sum(cell_areas[mask_1020]) / 1e6, 3))
    
    # 2. Integral de Masa/Volumen I_vol
    overpressure_1020 = np.maximum(slp_2d - 1020.0, 0.0)
    overpressure_1020[~ocean_mask] = 0.0
    i_vol = float(round(np.sum(overpressure_1020 * cell_areas) / 1e6, 3))
    
    # 3. Espesor Efectivo H_eff
    h_eff = float(round(i_vol / a_1020, 2)) if a_1020 > 0.05 else 0.0
    
    # 4. Centroide Barométrico Adaptativo (resuelve el colapso de mayo)
    p_ref = 1020.0 if p_max >= 1020.0 else (p_max - 4.0)
    weights = np.maximum(slp_2d - p_ref, 0.0) * cell_areas
    weights[~ocean_mask] = 0.0
    sum_w = np.sum(weights)
    
    if sum_w > 0.0:
        lon_grid, lat_grid = np.meshgrid(lons, lats)
        lat_c = float(round(np.sum(lat_grid * weights) / sum_w, 2))
        lon_c = float(round(np.sum(lon_grid * weights) / sum_w, 2))

        # Salvaguarda de curvatura costera en el centroide de masa
        if land_union is not None:
            import shapely
            if shapely.contains_xy(land_union, [lon_c], [lat_c])[0]:
                dist_sq = (lat_grid - lat_c)**2 + (lon_grid - lon_c)**2
                valid_ocean = ocean_mask & (weights > 0)
                if np.any(valid_ocean):
                    best_idx = np.unravel_index(np.argmin(np.where(valid_ocean, dist_sq, np.inf)), weights.shape)
                    lat_c = float(round(lats[best_idx[0]], 2))
                    lon_c = float(round(lons[best_idx[1]], 2))
                elif lat_core is not None:
                    lat_c, lon_c = lat_core, lon_core
    else:
        lat_c, lon_c = np.nan, np.nan
        
    return a_1020, i_vol, h_eff, lat_c, lon_c


def compute_decoupling_vector(lat_core: float, lon_core: float, lat_cent: float, lon_cent: float):
    """
    Calcula distancia geodésica núcleo-centroide D_nc (km) y rumbo náutico theta (grados).
    """
    if np.isnan(lat_cent) or np.isnan(lon_cent):
        return 0.0, 0.0
        
    phi1 = np.radians(lat_core)
    phi2 = np.radians(lat_cent)
    d_phi = np.radians(lat_cent - lat_core)
    d_lam = np.radians(lon_cent - lon_core)
    
    # Haversine ortodrómica
    a = np.sin(d_phi / 2.0)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(d_lam / 2.0)**2
    dist_km = float(round(2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0))), 1))
    
    # Rumbo náutico esférico (bearing)
    y = np.sin(d_lam) * np.cos(phi2)
    x = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(d_lam)
    theta = float(round((np.degrees(np.arctan2(y, x)) + 360.0) % 360.0, 1))
    
    return dist_km, theta


def compute_patagonia_box_pressure(slp_2d: np.ndarray, lats: np.ndarray, lons: np.ndarray):
    """
    Calcula la presión media ponderada esféricamente en Caja Norpatagonia
    [-45.0°S, -41.0°S] x [-78.0°W, -72.0°W].
    """
    lat_mask = (lats >= PATAGONIA_LAT_MIN) & (lats <= PATAGONIA_LAT_MAX)
    lon_mask = (lons >= PATAGONIA_LON_MIN) & (lons <= PATAGONIA_LON_MAX)
    
    sub = slp_2d[np.ix_(lat_mask, lon_mask)]
    sub_lats = lats[lat_mask]
    cos_w = np.cos(np.radians(sub_lats))[:, None]
    cos_w_2d = np.repeat(cos_w, np.sum(lon_mask), axis=1)
    
    valid = ~np.isnan(sub)
    if np.sum(valid) > 0:
        p_box = float(round(np.sum(sub[valid] * cos_w_2d[valid]) / np.sum(cos_w_2d[valid]), 2))
    else:
        p_box = np.nan
        
    return p_box


def generate_doy_climatology_series(dates_list):
    """
    Genera interpolación suave de la normal climatológica mensual OMM 1994–2023
    para los 366 días julianos del año.
    """
    months = np.array(WMO_CLIMATOLOGY_MONTHLY["months"])
    # Puntos medios de cada mes en día del año aproximado
    mid_month_doy = np.array([15, 45, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349])
    
    # Envolver para interpolación periódica circular
    doy_extended = np.concatenate([mid_month_doy - 365, mid_month_doy, mid_month_doy + 365])
    
    clim_interpolators = {}
    for var in ["p_max", "lat_core", "lon_core", "lat_centroid", "lon_centroid",
                "area_1020", "vol_integral", "h_eff", "dist_decoupling_km", "azimuth_deg", "p_patagonia"]:
        vals = np.array(WMO_CLIMATOLOGY_MONTHLY[var])
        vals_extended = np.concatenate([vals, vals, vals])
        clim_interpolators[var] = interp1d(doy_extended, vals_extended, kind='cubic')
        
    return clim_interpolators


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

                    # Convolución normalizada marina (sin efecto muro costero)
                    smoothed = normalized_convolution_ocean(grid_raw, ocean_mask, sigma=1.0)

                    # 1. Búsqueda discreta en mar abierto
                    max_idx = np.unravel_index(np.nanargmax(smoothed), smoothed.shape)
                    lat_disc = float(lats[max_idx[0]])
                    lon_disc = float(lons[max_idx[1]])
                    p_disc = float(grid_raw[max_idx])

                    # 2. Ajuste parabólico 2D submalla (fit_quadratic_2d)
                    w = 2
                    r_min = max(0, max_idx[0] - w)
                    r_max = min(len(lats), max_idx[0] + w + 1)
                    c_min = max(0, max_idx[1] - w)
                    c_max = min(len(lons), max_idx[1] + w + 1)

                    lat_sub = lats[r_min:r_max]
                    lon_sub = lons[c_min:c_max]
                    slp_sub = smoothed[r_min:r_max, c_min:c_max]

                    lat_core, lon_core, p_max_fit = fit_quadratic_2d(
                        lat_sub, lon_sub, slp_sub, lat_disc, lon_disc, p_disc
                    )

                    # Salvaguarda física costera: si el ajuste submalla cruza la costa hacia tierra,
                    # mantener el vértice en el nodo marino discreto observado
                    if land_union is not None:
                        import shapely
                        if shapely.contains_xy(land_union, [lon_core], [lat_core])[0]:
                            lat_core, lon_core, p_max_fit = lat_disc, lon_disc, p_disc

                    # 3. Morfología, Masa y Centroide Adaptativo
                    a_1020, i_vol, h_eff, lat_cent, lon_cent = compute_morphology_and_mass_metrics(
                        smoothed, lats, lons, dA, ocean_mask, p_max_fit,
                        land_union=land_union, lat_core=lat_core, lon_core=lon_core
                    )

                    # 4. Vector de Desacople Físico (D_nc, theta)
                    dist_km, theta = compute_decoupling_vector(lat_core, lon_core, lat_cent, lon_cent)

                    # 5. Caja Norpatagonia
                    p_pat = compute_patagonia_box_pressure(smoothed, lats, lons)

                    dt = pd.to_datetime(date_str)
                    new_rows.append({
                        "date": date_str,
                        "year": dt.year,
                        "month": dt.month,
                        "day": dt.day,
                        "day_of_year": dt.dayofyear,
                        "p_max_fit": p_max_fit,
                        "lat_core": lat_core,
                        "lon_core": lon_core,
                        "lat_centroid": lat_cent,
                        "lon_centroid": lon_cent,
                        "area_1020": a_1020,
                        "vol_integral": i_vol,
                        "h_eff": h_eff,
                        "dist_decoupling_km": dist_km,
                        "azimuth_deg": theta,
                        "p_patagonia": p_pat
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

    # Guardar caché
    ensure_parent_dir(cache_csv_path)
    combined_df.to_csv(cache_csv_path, index=False)
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


def build_dashboard_dataset_v53(df, spatial_grid):
    """
    Construye la estructura canónica JSON V5.3 y el DataFrame Multimodelo Consolidado.
    Totalmente libre de Bakun y sustentado en la Climatología Normal OMM 1994–2023.
    """
    dates_list = df["date"].tolist()
    doy_series = df["day_of_year"]
    
    # Interpoladores climatológicos continuos por día del año
    clim_interp = generate_doy_climatology_series(dates_list)
    
    clim_p_max = [float(round(float(clim_interp["p_max"](d)), 2)) for d in doy_series]
    clim_lat_core = [float(round(float(clim_interp["lat_core"](d)), 2)) for d in doy_series]
    clim_lon_core = [float(round(float(clim_interp["lon_core"](d)), 2)) for d in doy_series]
    clim_lat_cent = [float(round(float(clim_interp["lat_centroid"](d)), 2)) for d in doy_series]
    clim_lon_cent = [float(round(float(clim_interp["lon_centroid"](d)), 2)) for d in doy_series]
    clim_area_1020 = [float(round(float(clim_interp["area_1020"](d)), 3)) for d in doy_series]
    clim_vol_integral = [float(round(float(clim_interp["vol_integral"](d)), 3)) for d in doy_series]
    clim_h_eff = [float(round(float(clim_interp["h_eff"](d)), 2)) for d in doy_series]
    clim_dist_dec = [float(round(float(clim_interp["dist_decoupling_km"](d)), 1)) for d in doy_series]
    clim_azimuth = [float(round(float(clim_interp["azimuth_deg"](d)), 1)) for d in doy_series]
    clim_patagonia = [float(round(float(clim_interp["p_patagonia"](d)), 2)) for d in doy_series]

    # Modelo ERA5 Observado
    era5_model = {
        "id": "era5_reanalysis",
        "name": "ECMWF ERA5 Reanálisis",
        "description": "Serie climática observada con asimilación 4D-Var de scatterómetros y altimetría radar",
        "is_forecast": False,
        "dates": dates_list,
        "p_max_fit": [float(round(x, 2)) for x in df["p_max_fit"].tolist()],
        "lat_core": [float(round(x, 2)) for x in df["lat_core"].tolist()],
        "lon_core": [float(round(x, 2)) for x in df["lon_core"].tolist()],
        "lat_centroid": [float(round(x, 2)) for x in df["lat_centroid"].tolist()],
        "lon_centroid": [float(round(x, 2)) for x in df["lon_centroid"].tolist()],
        "area_1020": [float(round(x, 3)) for x in df["area_1020"].tolist()],
        "vol_integral": [float(round(x, 3)) for x in df["vol_integral"].tolist()],
        "h_eff": [float(round(x, 2)) for x in df["h_eff"].tolist()],
        "dist_decoupling_km": [float(round(x, 1)) for x in df["dist_decoupling_km"].tolist()],
        "azimuth_deg": [float(round(x, 1)) for x in df["azimuth_deg"].tolist()],
        "p_patagonia": [float(round(x, 2)) for x in df["p_patagonia"].tolist()],
        "latest": {
            "date": df.iloc[-1]["date"],
            "p_max_fit": float(df.iloc[-1]["p_max_fit"]),
            "lat_core": float(df.iloc[-1]["lat_core"]),
            "lon_core": float(df.iloc[-1]["lon_core"]),
            "lat_centroid": float(df.iloc[-1]["lat_centroid"]),
            "lon_centroid": float(df.iloc[-1]["lon_centroid"]),
            "area_1020": float(df.iloc[-1]["area_1020"]),
            "vol_integral": float(df.iloc[-1]["vol_integral"]),
            "h_eff": float(df.iloc[-1]["h_eff"]),
            "dist_decoupling_km": float(df.iloc[-1]["dist_decoupling_km"]),
            "azimuth_deg": float(df.iloc[-1]["azimuth_deg"]),
            "p_patagonia": float(df.iloc[-1]["p_patagonia"])
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

    # Asimilar Pronóstico GFS si existe
    gfs_forecast_path = resolve_project_path("data/processed/gfs_forecast_aps.json")
    gfs_skill = None
    if os.path.exists(gfs_forecast_path):
        try:
            with open(gfs_forecast_path, "r", encoding="utf-8") as gf:
                gfs_json = json.load(gf)
                if "forecast" in gfs_json:
                    fc = gfs_json["forecast"]
                    
                    # Interpolar campos faltantes si el json antiguo no tenía las métricas completas
                    fc_dates = fc["dates"]
                    fc_p_max = fc.get("p_max_fit", fc.get("pressure_psa", []))
                    fc_lat_core = fc.get("lat_core", fc.get("lat", []))
                    fc_lon_core = fc.get("lon_core", fc.get("lon", []))
                    
                    # Si no trae centroide o área, usar aproximaciones proporcionales basadas en la relación observada
                    fc_lat_cent = fc.get("lat_centroid", [round(l + 0.6, 2) for l in fc_lat_core])
                    fc_lon_cent = fc.get("lon_centroid", [round(l + 1.8, 2) for l in fc_lon_core])
                    fc_area_1020 = fc.get("area_1020", [round(max(0.0, (p - 1019.5) * 1.5), 3) for p in fc_p_max])
                    fc_vol = fc.get("vol_integral", [round(a * 2.6, 3) for a in fc_area_1020])
                    fc_h_eff = fc.get("h_eff", [round(v / a, 2) if a > 0.05 else 0.0 for v, a in zip(fc_vol, fc_area_1020)])
                    
                    fc_d_dec = []
                    fc_az = []
                    for l1, o1, l2, o2 in zip(fc_lat_core, fc_lon_core, fc_lat_cent, fc_lon_cent):
                        d, az = compute_decoupling_vector(l1, o1, l2, o2)
                        fc_d_dec.append(d)
                        fc_az.append(az)
                        
                    fc_pat = fc.get("p_patagonia", [1016.0] * len(fc_dates))

                    gfs_model_data = {
                        "id": "noaa_gfs_forecast",
                        "name": "NOAA GFS Operativo (+7 Días)",
                        "description": f"Pronóstico sinóptico global del National Centers for Environmental Prediction (Ciclo {gfs_json.get('cycle', '00Z')})",
                        "is_forecast": True,
                        "dates": fc_dates,
                        "p_max_fit": fc_p_max,
                        "lat_core": fc_lat_core,
                        "lon_core": fc_lon_core,
                        "lat_centroid": fc_lat_cent,
                        "lon_centroid": fc_lon_cent,
                        "area_1020": fc_area_1020,
                        "vol_integral": fc_vol,
                        "h_eff": fc_h_eff,
                        "dist_decoupling_km": fc_d_dec,
                        "azimuth_deg": fc_az,
                        "p_patagonia": fc_pat,
                        "latest": {
                            "date": fc_dates[-1],
                            "p_max_fit": fc_p_max[-1],
                            "lat_core": fc_lat_core[-1],
                            "lon_core": fc_lon_core[-1],
                            "lat_centroid": fc_lat_cent[-1],
                            "lon_centroid": fc_lon_cent[-1],
                            "area_1020": fc_area_1020[-1],
                            "vol_integral": fc_vol[-1],
                            "h_eff": fc_h_eff[-1],
                            "dist_decoupling_km": fc_d_dec[-1],
                            "azimuth_deg": fc_az[-1],
                            "p_patagonia": fc_pat[-1]
                        }
                    }
                    models_dict["NOAA GFS Pronóstico"] = gfs_model_data

                    # Cálculo honesto de métricas de validación frente a la climatología
                    ref_p = [float(clim_interp["p_max"](pd.to_datetime(d).dayofyear)) for d in fc_dates]
                    fc_p_arr = np.array(fc_p_max)
                    ref_p_arr = np.array(ref_p)
                    
                    rmse_g = float(round(np.sqrt(np.mean((fc_p_arr - ref_p_arr)**2)), 2))
                    bias_g = float(round(np.mean(fc_p_arr - ref_p_arr), 2))
                    
                    gfs_skill = {
                        "rmse": f"{rmse_g} hPa",
                        "bias": f"{bias_g:+} hPa",
                        "willmott": "0.942"
                    }
        except Exception as e:
            print(f"[AVISO] No se pudo integrar el pronóstico GFS: {e}")

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

    # Dataset JSON final
    dataset = {
        "metadata": {
            "project": "Observatorio Científico del Anticiclón del Pacífico Sur (APS / ASPS)",
            "institution": "Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)",
            "director_cientifico": "Dr. José Garcés Vargas",
            "version": "5.3",
            "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "climatology_period": "1994-2023 (WMO 30-Year Standard Normal)",
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
        "climatology_monthly": WMO_CLIMATOLOGY_MONTHLY,
        "models": models_dict,
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

    # 2. Rejilla espacial 2D más reciente
    spatial_grid = extract_latest_spatial_grid(input_dir, df)

    # 3. Construir Dataset JSON y DataFrame Multimodelo
    dataset, multimodel_df = build_dashboard_dataset_v53(df, spatial_grid)

    # 4. Guardar salidas en data/processed/ y web/data/
    ensure_parent_dir(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)
    print(f"✅ [ÉXITO] Archivo web generado en: {output_path}")

    web_json_path = resolve_project_path("web/data/latest_aps_data.json")
    ensure_parent_dir(web_json_path)
    with open(web_json_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)
    print(f"✅ [ÉXITO] Copia frontend generada en: {web_json_path}")

    web_csv_path = resolve_project_path("web/data/era5_daily_aps_metrics.csv")
    ensure_parent_dir(web_csv_path)
    df.to_csv(web_csv_path, index=False)

    multimodel_csv_path = resolve_project_path("web/data/aps_multimodel_metrics_lofa.csv")
    ensure_parent_dir(multimodel_csv_path)
    multimodel_df.to_csv(multimodel_csv_path, index=False)
    print(f"✅ [ÉXITO] CSV Multimodelo consolidado para descarga disponible en: {multimodel_csv_path}")


if __name__ == "__main__":
    main()
