#!/usr/bin/env python3
"""
Suite de Pruebas Unitarias Geofísicas y Validación Numérica del APS
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3

Valida:
1. Precisión submalla 2D (fit_quadratic_2d) sobre vórtice continuo analítico.
2. Continuidad matemática en períodos débiles (mayo) sin colapso a NaN.
3. Confinamiento 100% oceánico (cero centros sobre tierra continental).
4. Solución esférica exacta de Haversine y acimut de desacople.
5. Factor de corrección cósmico cos(φ) en áreas esféricas diferenciales dA.
6. Supresión estricta del efecto muro mediante convolución normalizada.
"""

import os
import sys
import glob
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd

# Asegurar path de importación
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from pipeline.spatial_geometry import (
    download_and_load_natural_earth_10m,
    compute_cell_areas_km2,
    generate_ocean_mask_10m,
    normalized_convolution_ocean,
    EARTH_RADIUS_KM
)

from pipeline.calculate_aps_metrics import (
    fit_quadratic_2d,
    compute_morphology_and_mass_metrics,
    compute_decoupling_vector,
    compute_patagonia_box_pressure
)

from pipeline.aps_metrics import (
    classify_regime,
    REGIME_SYMMETRIC,
    REGIME_COASTAL,
    REGIME_BLOCKING,
    REGIME_WEAK,
)
from pipeline.file_utils import atomic_csv_dump, atomic_json_dump

from pipeline.paths import PROJECT_ROOT, resolve_project_path


class TestAPSPhysics(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Carga la geometría una sola vez para toda la suite de pruebas."""
        cls.land_union = download_and_load_natural_earth_10m()
        cls.lats = np.linspace(-18.0, -48.0, 121)
        cls.lons = np.linspace(-120.0, -70.0, 201)
        cls.dA = compute_cell_areas_km2(cls.lats, cls.lons)
        cls.ocean_mask = generate_ocean_mask_10m(cls.lats, cls.lons, cls.land_union)

    def test_fit_quadratic_2d_synthetic_vortex(self):
        """
        Prueba 1: Vórtice gaussiano continuo con vértice en (-33.37°S, -95.62°W).
        Verifica que fit_quadratic_2d recupere la posición continua con error < 0.02°
        y la presión máxima con error < 0.05 hPa respecto al vértice analítico.
        """
        true_lat = -33.37
        true_lon = -95.62
        true_pmax = 1026.85
        sigma_x, sigma_y = 6.0, 4.0

        lon_2d, lat_2d = np.meshgrid(self.lons, self.lats)
        synthetic_field = 1012.0 + (true_pmax - 1012.0) * np.exp(
            -0.5 * (((lon_2d - true_lon) / sigma_x)**2 + ((lat_2d - true_lat) / sigma_y)**2)
        )

        # Encontrar nodo discreto más cercano
        discrete_idx = np.unravel_index(np.argmax(synthetic_field), synthetic_field.shape)
        lat_disc = float(self.lats[discrete_idx[0]])
        lon_disc = float(self.lons[discrete_idx[1]])
        p_disc = float(synthetic_field[discrete_idx])

        # Extraer ventana 5x5
        w = 2
        r_min = max(0, discrete_idx[0] - w)
        r_max = min(len(self.lats), discrete_idx[0] + w + 1)
        c_min = max(0, discrete_idx[1] - w)
        c_max = min(len(self.lons), discrete_idx[1] + w + 1)

        lat_sub = self.lats[r_min:r_max]
        lon_sub = self.lons[c_min:c_max]
        slp_sub = synthetic_field[r_min:r_max, c_min:c_max]

        fitted_lat, fitted_lon, fitted_p = fit_quadratic_2d(
            lat_sub, lon_sub, slp_sub, lat_disc, lon_disc, p_disc
        )

        error_lat = abs(fitted_lat - true_lat)
        error_lon = abs(fitted_lon - true_lon)
        error_p = abs(fitted_p - true_pmax)

        self.assertLess(error_lat, 0.02, f"Error en latitud submalla ({error_lat:.4f}°) supera tolerancia de 0.02°")
        self.assertLess(error_lon, 0.02, f"Error en longitud submalla ({error_lon:.4f}°) supera tolerancia de 0.02°")
        self.assertLess(error_p, 0.05, f"Error en presión ajustada ({error_p:.4f} hPa) supera tolerancia de 0.05 hPa")

    def test_fit_quadratic_2d_rejects_pressure_jump(self):
        """
        Prueba 1b: El ajuste debe rechazarse si |P_fit - P_disc| >= 3.0 hPa.
        Se fuerza una presión discreta artificialmente baja para activar la guarda.
        """
        true_lat = -33.37
        true_lon = -95.62
        true_pmax = 1026.85

        lon_2d, lat_2d = np.meshgrid(self.lons, self.lats)
        synthetic_field = 1012.0 + (true_pmax - 1012.0) * np.exp(
            -0.5 * (((lon_2d - true_lon) / 6.0) ** 2 + ((lat_2d - true_lat) / 4.0) ** 2)
        )

        discrete_idx = np.unravel_index(np.argmax(synthetic_field), synthetic_field.shape)
        lat_disc = float(self.lats[discrete_idx[0]])
        lon_disc = float(self.lons[discrete_idx[1]])
        p_disc = float(synthetic_field[discrete_idx])

        w = 2
        lat_sub = self.lats[discrete_idx[0] - w: discrete_idx[0] + w + 1]
        lon_sub = self.lons[discrete_idx[1] - w: discrete_idx[1] + w + 1]
        slp_sub = synthetic_field[
            discrete_idx[0] - w: discrete_idx[0] + w + 1,
            discrete_idx[1] - w: discrete_idx[1] + w + 1,
        ]

        # Salto de 10 hPa: el ajuste continuo debe ser descartado.
        p_disc_corrupta = p_disc - 10.0
        result = fit_quadratic_2d(
            lat_sub, lon_sub, slp_sub, lat_disc, lon_disc, p_disc_corrupta
        )
        self.assertEqual(result, (lat_disc, lon_disc, p_disc_corrupta))

    def test_regime_classification(self):
        """
        Prueba 1c: Clasificación sinóptica por distancia y acimut.
        """
        self.assertEqual(classify_regime(120.0, 90.0), REGIME_SYMMETRIC)
        self.assertEqual(classify_regime(500.0, 60.0), REGIME_COASTAL)
        self.assertEqual(classify_regime(500.0, 180.0), REGIME_BLOCKING)
        self.assertEqual(classify_regime(500.0, 250.0), REGIME_WEAK)
        self.assertEqual(classify_regime(np.nan, 90.0), REGIME_WEAK)

    def test_atomic_write(self):
        """
        Prueba 1d: Las escrituras atómicas de JSON y CSV no dejan temporales.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "datos.json"
            csv_path = Path(temp_dir) / "datos.csv"

            atomic_json_dump({"ok": True, "valor": 1.5}, json_path)
            with open(json_path, "r", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), {"ok": True, "valor": 1.5})

            frame = pd.DataFrame({"a": [1, 2], "b": [3.0, 4.0]})
            atomic_csv_dump(frame, csv_path, index=False)
            loaded = pd.read_csv(csv_path)
            self.assertEqual(list(loaded.columns), ["a", "b"])
            self.assertEqual(loaded.shape, (2, 2))

            leftovers = glob.glob(str(Path(temp_dir) / ".*.part"))
            self.assertEqual(leftovers, [], f"Quedaron temporales: {leftovers}")

    def test_may_collapse_continuity(self):
        """
        Prueba 2: Caso singular de mayo (P_max = 1019.2 hPa < 1020.0 hPa).
        Verifica que el centroide adaptativo flote hacia (P_max - 4.0 hPa)
        produciendo coordenadas numéricas válidas sin NaN, con A_1020 = 0.0.
        """
        weak_field = np.full((len(self.lats), len(self.lons)), 1014.0)
        center_lat_idx = 40  # ~ -28°S
        center_lon_idx = 80  # ~ -100°W
        
        lon_2d, lat_2d = np.meshgrid(self.lons, self.lats)
        weak_field += 5.2 * np.exp(-0.5 * (((lon_2d - self.lons[center_lon_idx])/7.0)**2 + ((lat_2d - self.lats[center_lat_idx])/5.0)**2))
        p_max = float(np.max(weak_field))
        self.assertLess(p_max, 1020.0, "La presión máxima debe ser menor a 1020 hPa para esta prueba")

        a_1020, i_vol, h_eff, lat_c, lon_c = compute_morphology_and_mass_metrics(
            weak_field, self.lats, self.lons, self.dA, self.ocean_mask, p_max
        )

        self.assertEqual(a_1020, 0.0, "A_1020 debe ser exactamente 0 cuando P < 1020 hPa")
        self.assertEqual(i_vol, 0.0, "I_vol debe ser exactamente 0 cuando P < 1020 hPa")
        self.assertEqual(h_eff, 0.0, "H_eff debe ser 0.0 cuando A_1020 es 0")
        self.assertFalse(np.isnan(lat_c), "lat_centroid no debe ser NaN durante el mínimo de mayo")
        self.assertFalse(np.isnan(lon_c), "lon_centroid no debe ser NaN durante el mínimo de mayo")
        self.assertAlmostEqual(lat_c, self.lats[center_lat_idx], delta=0.5)
        self.assertAlmostEqual(lon_c, self.lons[center_lon_idx], delta=0.5)

    def test_coastal_zero_land_centers(self):
        """
        Prueba 3: Integridad de la máscara costera Natural Earth 10m.
        Verifica que 0.0% de los centros calculados caigan en tierra firme.
        """
        import shapely
        csv_path = os.path.join(BASE_DIR, "web", "data", "aps_multimodel_metrics_lofa.csv")
        if not os.path.exists(csv_path):
            self.skipTest("CSV no encontrado aún, salteando verificación sobre dataset completo")

        df = pd.read_csv(csv_path)
        
        # Test centros de núcleo
        core_lons = df["lon_core"].values
        core_lats = df["lat_core"].values
        core_in_land = shapely.contains_xy(self.land_union, core_lons, core_lats)
        self.assertEqual(int(np.sum(core_in_land)), 0, f"Se detectaron {np.sum(core_in_land)} núcleos sobre tierra firme")

        # Test centros de masa
        valid_cent = ~df["lat_centroid"].isna()
        cent_lons = df.loc[valid_cent, "lon_centroid"].values
        cent_lats = df.loc[valid_cent, "lat_centroid"].values
        cent_in_land = shapely.contains_xy(self.land_union, cent_lons, cent_lats)
        self.assertEqual(int(np.sum(cent_in_land)), 0, f"Se detectaron {np.sum(cent_in_land)} centroides sobre tierra firme")

    def test_decoupling_azimuth_quadrants(self):
        """
        Prueba 4: Geometría esférica de Haversine y Rumbo Azimutal Náutico θ.
        Verifica los cuatro cuadrantes cardinales exactos.
        """
        # 1. Desplazamiento puro al Este (θ = 90°)
        dist_e, theta_e = compute_decoupling_vector(-35.0, -90.0, -35.0, -85.0)
        self.assertAlmostEqual(theta_e, 90.0, delta=1.5, msg="Rumbo hacia el Este debe ser ~90°")
        self.assertGreater(dist_e, 400.0)

        # 2. Desplazamiento puro al Sur (θ = 180°)
        dist_s, theta_s = compute_decoupling_vector(-35.0, -90.0, -40.0, -90.0)
        self.assertAlmostEqual(theta_s, 180.0, delta=0.5, msg="Rumbo hacia el Sur debe ser ~180°")
        self.assertAlmostEqual(dist_s, 5.0 * 111.19, delta=5.0)

        # 3. Desplazamiento puro al Oeste (θ = 270°)
        dist_w, theta_w = compute_decoupling_vector(-35.0, -85.0, -35.0, -90.0)
        self.assertAlmostEqual(theta_w, 270.0, delta=1.5, msg="Rumbo hacia el Oeste debe ser ~270°")

        # 4. Desplazamiento puro al Norte (θ = 0°)
        dist_n, theta_n = compute_decoupling_vector(-40.0, -90.0, -35.0, -90.0)
        self.assertAlmostEqual(theta_n, 0.0, delta=0.5, msg="Rumbo hacia el Norte debe ser ~0°")

    def test_cell_areas_cos_latitude(self):
        """
        Prueba 5: Factor de corrección cósmica cos(φ) en áreas esféricas.
        Verifica que dA decrezca con la latitud y cumpla los órdenes de magnitud físicos.
        """
        # -18°S: cos(-18°) ≈ 0.951 -> ~735 km²
        # -48°S: cos(-48°) ≈ 0.669 -> ~517 km²
        area_18 = self.dA[0, 0]
        area_48 = self.dA[-1, 0]

        self.assertGreater(area_18, area_48, "El área diferencial en -18°S debe ser mayor que en -48°S")
        self.assertAlmostEqual(area_18, 735.0, delta=10.0)
        self.assertAlmostEqual(area_48, 517.0, delta=10.0)

    def test_normalized_convolution_no_wall_effect(self):
        """
        Prueba 6: Convolución normalizada marina.
        Verifica que en mar abierto no altere un campo uniforme y mantenga NaNs en tierra.
        """
        uniform_p = np.full_like(self.dA, 1022.0)
        smoothed = normalized_convolution_ocean(uniform_p, self.ocean_mask, sigma=1.0)

        # En mar abierto (e.g. -35°S, -95°W) debe ser exactamente 1022.0
        open_ocean_val = smoothed[68, 100]
        self.assertAlmostEqual(open_ocean_val, 1022.0, delta=0.01)

        # En tierra firme debe ser NaN
        land_val = smoothed[60, -1]  # Chile continental / Argentina
        self.assertTrue(np.isnan(land_val), "Puntos en tierra deben ser NaN estrictos")


class TestRutasNAS(unittest.TestCase):
    """
    Pruebas de resolución de rutas con APS_DATA_ROOT para la Fase 5.
    """

    def test_ruta_absoluta_no_se_modifica(self):
        """
        Una ruta absoluta debe conservarse aunque APS_DATA_ROOT esté definida.
        """
        with patch.dict(os.environ, {"APS_DATA_ROOT": "/mnt/nas/aps"}):
            self.assertEqual(
                resolve_project_path("/mnt/nas/aps/raw/mean_sea_level_pressure"),
                Path("/mnt/nas/aps/raw/mean_sea_level_pressure")
            )

    def test_ruta_data_se_resuelve_contra_aps_data_root(self):
        """
        Las rutas data/... se redirigen a la raíz externa cuando está definida.
        """
        with patch.dict(os.environ, {"APS_DATA_ROOT": "/mnt/nas/aps"}):
            self.assertEqual(
                resolve_project_path("data/raw/mean_sea_level_pressure"),
                Path("/mnt/nas/aps/data/raw/mean_sea_level_pressure")
            )

    def test_ruta_web_no_se_redirige_a_aps_data_root(self):
        """
        Las rutas web/... permanecen dentro del proyecto aunque exista APS_DATA_ROOT.
        """
        with patch.dict(os.environ, {"APS_DATA_ROOT": "/mnt/nas/aps"}):
            self.assertEqual(
                resolve_project_path("web/data/latest_aps_data.json"),
                PROJECT_ROOT / "web/data/latest_aps_data.json"
            )

    def test_sin_aps_data_root_se_usa_raiz_del_proyecto(self):
        """
        Sin la variable de entorno, toda ruta relativa usa PROJECT_ROOT.
        """
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APS_DATA_ROOT", None)
            self.assertEqual(
                resolve_project_path("data/processed/era5_daily_aps_metrics.csv"),
                PROJECT_ROOT / "data/processed/era5_daily_aps_metrics.csv"
            )


if __name__ == "__main__":
    unittest.main()

