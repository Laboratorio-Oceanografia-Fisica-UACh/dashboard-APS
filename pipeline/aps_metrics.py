#!/usr/bin/env python3
"""
Motor común de métricas del Anticiclón del Pacífico Sur (APS / ASPS).
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3

Este módulo concentra la física V5.3 compartida por todos los modelos
(ERA5, GFS, NCEP y futuros reanálisis/pronósticos):

- Dominio de seguimiento y constantes físicas.
- Ajuste parabólico 2D submalla con validaciones estrictas.
- Morfología, masa y centroide barométrico adaptativo.
- Vector geodésico de desacople núcleo-centroide.
- Presión de la caja Norpatagonia.
- Clasificación sinóptica del régimen.
- Métricas objetivas de validación (RMSE, BIAS, r, Willmott y distancia).
"""

import numpy as np

from pipeline.spatial_geometry import (
    EARTH_RADIUS_KM,
    compute_cell_areas_km2,
    generate_ocean_mask_10m,
    normalized_convolution_ocean,
)

# Dominio geográfico de seguimiento del APS en el Pacífico Suroriental
TRACK_LAT_NORTH = -18.0
TRACK_LAT_SOUTH = -48.0
TRACK_LON_WEST = -120.0
TRACK_LON_EAST = -70.0

# Caja Norpatagonia para monitoreo de bloqueos y cuñas hacia los fiordos australes
PATAGONIA_LAT_MIN = -45.0
PATAGONIA_LAT_MAX = -41.0
PATAGONIA_LON_MIN = -78.0
PATAGONIA_LON_MAX = -72.0

P_THRESHOLD = 1020.0
R_EARTH_KM = EARTH_RADIUS_KM

# Umbrales de clasificación sinóptica del vector de desacople
SYMMETRIC_DISTANCE_KM = 300.0

REGIME_SYMMETRIC = "Simétrico Concéntrico"
REGIME_COASTAL = "Dorsal Costera / Compresión"
REGIME_BLOCKING = "Bloqueo Patagónico / Migración Austral"
REGIME_WEAK = "Desacople Débil / Transición"


def fit_quadratic_2d(lat_sub: np.ndarray, lon_sub: np.ndarray, slp_sub: np.ndarray,
                     lat_disc: float, lon_disc: float, p_disc: float):
    """
    Ajusta una parábola multivariable 2D por mínimos cuadrados en una ventana 5x5:
        P(x, y) = a*x^2 + b*y^2 + c*x*y + d*x + e*y + f

    Resuelve el vértice continuo nabla P = 0 validando:
      1. Al menos 9 puntos válidos.
      2. Hessiano definido negativo (a < 0, b < 0, det(H) > 1e-4).
      3. Desplazamiento submalla acotado (|x*| <= 0.35, |y*| <= 0.35).
      4. Consistencia física |P_fit - P_disc| < 3.0 hPa.

    Si alguna validación falla, retorna el nodo discreto original.
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

    M = np.column_stack([x**2, y**2, x * y, x, y, np.ones_like(x)])
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
                p_opt = float(round(
                    a * x_opt**2 + b * y_opt**2 + c * x_opt * y_opt
                    + d * x_opt + e * y_opt + f,
                    2,
                ))
                # Validación de consistencia física contra el nodo discreto
                if abs(p_opt - p_disc) < 3.0:
                    return lat_opt, lon_opt, p_opt
        except np.linalg.LinAlgError:
            pass

    return lat_disc, lon_disc, p_disc


def compute_morphology_and_mass_metrics(slp_2d: np.ndarray, lats: np.ndarray, lons: np.ndarray,
                                        cell_areas: np.ndarray, ocean_mask: np.ndarray,
                                        p_max: float, land_union=None, lat_core=None,
                                        lon_core=None):
    """
    Calcula A_1020, I_vol, H_eff y el Centroide Barométrico Adaptativo (phi_c, lam_c).
    Garantiza que el centroide se confine 100% en el océano Pacífico.
    """
    # 1. Extensión areal A_1020 (siempre con el umbral fijo 1020 hPa)
    mask_1020 = ocean_mask & (slp_2d >= P_THRESHOLD)
    a_1020 = float(round(np.sum(cell_areas[mask_1020]) / 1e6, 3))

    # 2. Integral de masa/volumen I_vol (siempre con el umbral fijo 1020 hPa)
    overpressure_1020 = np.maximum(slp_2d - P_THRESHOLD, 0.0)
    overpressure_1020 = np.where(ocean_mask, overpressure_1020, 0.0)
    i_vol = float(round(np.sum(overpressure_1020 * cell_areas) / 1e6, 3))

    # 3. Espesor efectivo H_eff
    h_eff = float(round(i_vol / a_1020, 2)) if a_1020 > 0.05 else 0.0

    # 4. Centroide barométrico adaptativo (resuelve el colapso de mayo)
    p_base = P_THRESHOLD if p_max >= P_THRESHOLD else (p_max - 4.0)
    weights = np.maximum(slp_2d - p_base, 0.0) * cell_areas
    weights = np.where(ocean_mask, weights, 0.0)
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
                    best_idx = np.unravel_index(
                        np.argmin(np.where(valid_ocean, dist_sq, np.inf)),
                        weights.shape,
                    )
                    lat_c = float(round(lats[best_idx[0]], 2))
                    lon_c = float(round(lons[best_idx[1]], 2))
                elif lat_core is not None:
                    lat_c, lon_c = lat_core, lon_core
    else:
        lat_c, lon_c = np.nan, np.nan

    return a_1020, i_vol, h_eff, lat_c, lon_c


def compute_decoupling_vector(lat_core: float, lon_core: float,
                              lat_cent: float, lon_cent: float):
    """
    Calcula la distancia geodésica núcleo-centroide D_nc (km) y el rumbo
    náutico theta (grados) mediante Haversine y bearing esférico.
    """
    if np.isnan(lat_cent) or np.isnan(lon_cent):
        return 0.0, 0.0

    phi1 = np.radians(lat_core)
    phi2 = np.radians(lat_cent)
    d_phi = np.radians(lat_cent - lat_core)
    d_lam = np.radians(lon_cent - lon_core)

    # Haversine ortodrómica
    a = np.sin(d_phi / 2.0)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(d_lam / 2.0)**2
    dist_km = float(round(2.0 * R_EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0))), 1))

    # Rumbo náutico esférico (bearing)
    y = np.sin(d_lam) * np.cos(phi2)
    x = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(d_lam)
    theta = float(round((np.degrees(np.arctan2(y, x)) + 360.0) % 360.0, 1))

    return dist_km, theta


def compute_patagonia_box_pressure(slp_2d: np.ndarray, lats: np.ndarray, lons: np.ndarray):
    """
    Calcula la presión media ponderada esféricamente en la Caja Norpatagonia
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


def classify_regime(dist_km: float, theta: float) -> str:
    """
    Clasifica el régimen sinóptico a partir del vector de desacople.
    """
    if dist_km is None or theta is None:
        return REGIME_WEAK
    if not np.isfinite(dist_km) or not np.isfinite(theta):
        return REGIME_WEAK
    if dist_km < SYMMETRIC_DISTANCE_KM:
        return REGIME_SYMMETRIC
    if 30.0 <= theta <= 120.0:
        return REGIME_COASTAL
    if 120.0 < theta <= 210.0:
        return REGIME_BLOCKING
    return REGIME_WEAK


def compute_daily_aps_metrics(slp_2d: np.ndarray, lats: np.ndarray, lons: np.ndarray,
                              date=None, land_union=None, cell_areas=None,
                              ocean_mask=None, sigma: float = 1.0,
                              apply_smoothing: bool = True):
    """
    Calcula todas las métricas diarias del APS con la física V5.3.

    Retorna un diccionario con fecha, núcleo continuo, centroide adaptativo,
    masa/morfología, desacople, presión Norpatagonia y régimen sinóptico.
    Retorna None si la grilla no contiene puntos oceánicos válidos.
    """
    lats = np.asarray(lats, dtype=float)
    lons = np.asarray(lons, dtype=float)
    slp_2d = np.asarray(slp_2d, dtype=float)

    if cell_areas is None:
        cell_areas = compute_cell_areas_km2(lats, lons)
    if ocean_mask is None:
        ocean_mask = generate_ocean_mask_10m(lats, lons, land_union)

    if apply_smoothing:
        smoothed = normalized_convolution_ocean(slp_2d, ocean_mask, sigma=sigma)
    else:
        smoothed = np.where(ocean_mask, slp_2d, np.nan)

    if np.all(np.isnan(smoothed)):
        return None

    # 1. Búsqueda discreta en mar abierto
    max_idx = np.unravel_index(np.nanargmax(smoothed), smoothed.shape)
    lat_disc = float(round(float(lats[max_idx[0]]), 4))
    lon_disc = float(round(float(lons[max_idx[1]]), 4))
    p_disc = float(round(float(smoothed[max_idx]), 2))

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

    # Salvaguarda física costera: si el vértice submalla cruza a tierra,
    # mantener el nodo marino discreto observado.
    if land_union is not None:
        import shapely
        if shapely.contains_xy(land_union, [lon_core], [lat_core])[0]:
            lat_core, lon_core, p_max_fit = lat_disc, lon_disc, p_disc

    # Salvaguarda de dominio: el núcleo no puede salir del recorte de seguimiento.
    if not (TRACK_LAT_SOUTH <= lat_core <= TRACK_LAT_NORTH
            and TRACK_LON_WEST <= lon_core <= TRACK_LON_EAST):
        lat_core, lon_core, p_max_fit = lat_disc, lon_disc, p_disc

    # 3. Morfología, masa y centroide adaptativo
    a_1020, i_vol, h_eff, lat_cent, lon_cent = compute_morphology_and_mass_metrics(
        smoothed, lats, lons, cell_areas, ocean_mask, p_max_fit,
        land_union=land_union, lat_core=lat_core, lon_core=lon_core,
    )

    # 4. Vector de desacople físico (D_nc, theta)
    dist_km, theta = compute_decoupling_vector(lat_core, lon_core, lat_cent, lon_cent)

    # 5. Caja Norpatagonia
    p_pat = compute_patagonia_box_pressure(smoothed, lats, lons)

    return {
        "date": date,
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
        "p_patagonia": p_pat,
        "regime": classify_regime(dist_km, theta),
    }


def _paired_arrays(model, reference):
    """
    Alinea dos series por posición descartando pares no finitos.
    """
    m = np.asarray(model, dtype=float)
    o = np.asarray(reference, dtype=float)
    if m.shape != o.shape:
        raise ValueError("Las series model y reference deben tener la misma longitud")
    valid = np.isfinite(m) & np.isfinite(o)
    return m[valid], o[valid]


def rmse(model, reference, min_pairs=2):
    """Error cuadrático medio entre modelo y referencia (hPa)."""
    m, o = _paired_arrays(model, reference)
    if m.size < min_pairs:
        return None
    return float(np.sqrt(np.mean((m - o) ** 2)))


def bias(model, reference, min_pairs=2):
    """Sesgo medio (modelo - referencia) en hPa."""
    m, o = _paired_arrays(model, reference)
    if m.size < min_pairs:
        return None
    return float(np.mean(m - o))


def pearson_r(model, reference, min_pairs=3):
    """Coeficiente de correlación de Pearson."""
    m, o = _paired_arrays(model, reference)
    if m.size < min_pairs:
        return None
    m_std = np.std(m)
    o_std = np.std(o)
    if m_std <= 1e-12 or o_std <= 1e-12:
        return None
    return float(np.corrcoef(m, o)[0, 1])


def willmott_d(model, reference, min_pairs=2):
    """
    Índice de acuerdo de Willmott (d in [0, 1]).
    Retorna None si no hay pares suficientes o el denominador es nulo.
    """
    m, o = _paired_arrays(model, reference)
    if m.size < min_pairs:
        return None
    o_bar = float(np.mean(o))
    num = float(np.sum((m - o) ** 2))
    den = float(np.sum((np.abs(m - o_bar) + np.abs(o - o_bar)) ** 2))
    if den <= 1e-12:
        return None
    return float(1.0 - num / den)


def mean_geodesic_distance(lat_model, lon_model, lat_ref, lon_ref, min_pairs=2):
    """
    Distancia geodésica media (km) entre dos pares de centros.
    """
    lat_m = np.asarray(lat_model, dtype=float)
    lon_m = np.asarray(lon_model, dtype=float)
    lat_r = np.asarray(lat_ref, dtype=float)
    lon_r = np.asarray(lon_ref, dtype=float)
    if not (lat_m.shape == lon_m.shape == lat_r.shape == lon_r.shape):
        raise ValueError("Todas las series de coordenadas deben tener la misma longitud")

    valid = (
        np.isfinite(lat_m) & np.isfinite(lon_m)
        & np.isfinite(lat_r) & np.isfinite(lon_r)
    )
    if np.sum(valid) < min_pairs:
        return None

    phi1 = np.radians(lat_m[valid])
    phi2 = np.radians(lat_r[valid])
    d_phi = phi2 - phi1
    d_lam = np.radians(lon_r[valid] - lon_m[valid])

    a = np.sin(d_phi / 2.0)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(d_lam / 2.0)**2
    dist = 2.0 * R_EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return float(np.mean(dist))
