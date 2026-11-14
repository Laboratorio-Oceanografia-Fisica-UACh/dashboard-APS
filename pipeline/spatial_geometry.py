#!/usr/bin/env python3
"""
Módulo de Geometría Espacial y Máscara Costera 10m para el Dominio del Pacífico Sur
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3

Implementa:
- Carga y vectorización de Natural Earth 10m Physical Land.
- Cálculo analítico de áreas de celda esféricas dA(φ) en km².
- Generación de máscara oceánica estricta (excluyendo Sudamérica y confinada al Pacífico).
- Convolución normalizada marina (Normalized Convolution) para supresión del efecto muro costero.
"""

import os
import urllib.request
import zipfile
import numpy as np
from scipy.ndimage import gaussian_filter
import shapely
from shapely.geometry import shape
import shapefile

EARTH_RADIUS_KM = 6371.0088


def download_and_load_natural_earth_10m(target_dir=None):
    """
    Carga el polígono unificado de tierra firme de Natural Earth 10m.
    Descarga automáticamente el archivo zip si no está presente en disco.
    Filtra los polígonos relevantes para Sudamérica y el Pacífico para máxima eficiencia.
    """
    if target_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target_dir = os.path.join(base_dir, "data", "shapefiles")
        
    os.makedirs(target_dir, exist_ok=True)
    shp_path = os.path.join(target_dir, "ne_10m_land.shp")
    zip_path = os.path.join(target_dir, "ne_10m_land.zip")
    
    if not os.path.exists(shp_path):
        url = "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_land.zip"
        print(f"🌍 [GEOMETRÍA] Descargando Natural Earth 10m Land desde {url}...")
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp, open(zip_path, "wb") as out:
            out.write(resp.read())
        print("📦 [GEOMETRÍA] Descomprimiendo archivo shapefile...")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(target_dir)
        print("✅ [GEOMETRÍA] Shapefile 10m descomprimido exitosamente.")

    sf = shapefile.Reader(shp_path)
    # Filtrar geometrías que intersecan el continente sudamericano y sus islas adyacentes
    sa_geoms = []
    for s in sf.shapes():
        # bbox: (xmin, ymin, xmax, ymax)
        if s.bbox[0] < -60 and s.bbox[2] > -90 and s.bbox[1] < 10 and s.bbox[3] > -60:
            sa_geoms.append(shape(s))
            
    if not sa_geoms:
        # Fallback si el filtro no captura formas
        sa_geoms = [shape(s) for s in sf.shapes()]

    land_union = shapely.unary_union(sa_geoms)
    return land_union


def compute_cell_areas_km2(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """
    Calcula el área física de cada celda geodésica sobre la esfera terrestre en km².
    dA(φ) = R_earth² * cos(φ) * dφ * dλ
    
    Inputs:
        lats: array 1D de latitudes (grados)
        lons: array 1D de longitudes (grados)
    Output:
        dA: array 2D de dimensiones (len(lats), len(lons)) con el área en km²
    """
    d_phi = np.abs(np.gradient(np.radians(lats)))
    d_lam = np.abs(np.gradient(np.radians(lons)))
    cos_lat = np.cos(np.radians(lats))
    
    # Crear malla 2D para d_phi y d_lam
    d_lam_grid, d_phi_grid = np.meshgrid(d_lam, d_phi)
    _, cos_lat_grid = np.meshgrid(lons, cos_lat)
    
    dA = (EARTH_RADIUS_KM ** 2) * cos_lat_grid * d_phi_grid * d_lam_grid
    return dA


def generate_ocean_mask_10m(lats: np.ndarray, lons: np.ndarray, land_union=None) -> np.ndarray:
    """
    Genera una matriz booleana 2D (len(lats), len(lons)) donde:
        True  = Océano Pacífico Abierto
        False = Tierra Continental/Islas o Fuera del Límite Oriental Pacífico
    """
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    flat_lons = lon_grid.ravel()
    flat_lats = lat_grid.ravel()

    if land_union is not None:
        # Shapely 2.0+ contains_xy vectorizado sobre todas las coordenadas
        is_land = shapely.contains_xy(land_union, flat_lons, flat_lats)
        ocean_mask = ~is_land.reshape(lat_grid.shape)
    else:
        # Fallback de seguridad si no hay shapefile
        ref_lats = np.array([-18.0, -20.0, -24.0, -28.0, -30.0, -33.0, -35.0, -37.0, -40.0, -43.0, -45.0, -48.0])
        ref_lons = np.array([-70.4, -70.15, -70.4, -71.0, -71.35, -71.65, -72.3, -73.5, -73.8, -74.2, -74.8, -75.3])
        coast_lons = np.interp(lats, ref_lats[::-1], ref_lons[::-1])
        ocean_mask = lon_grid < coast_lons[:, None]

    # Confinamiento oriental pacífico absoluto: no computar este de -70.5°W
    ocean_mask = ocean_mask & (lon_grid <= -70.5)
    return ocean_mask


def normalized_convolution_ocean(grid_2d: np.ndarray, ocean_mask: np.ndarray, sigma: float = 1.0) -> np.ndarray:
    """
    Aplica convolución normalizada sobre la grilla oceánica 2D.
    P_smooth(φ, λ) = [G_σ * (P * W)] / [G_σ * W + ε]
    
    Garantiza que el valor sobre tierra no contamine los puntos marinos costeros (efecto muro).
    En tierra firme retorna NaN estrictos.
    """
    w = ocean_mask.astype(float)
    v = np.where(ocean_mask, grid_2d, 0.0)
    
    v_smooth = gaussian_filter(v, sigma=sigma, mode='reflect')
    w_smooth = gaussian_filter(w, sigma=sigma, mode='reflect')
    
    smoothed = np.full_like(grid_2d, np.nan)
    valid = w_smooth > 1e-4
    smoothed[valid] = v_smooth[valid] / w_smooth[valid]
    smoothed[~ocean_mask] = np.nan
    return smoothed
