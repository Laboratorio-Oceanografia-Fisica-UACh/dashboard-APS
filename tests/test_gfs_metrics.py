#!/usr/bin/env python3
"""
Pruebas del pronóstico NOAA GFS con métricas V5.3 completas.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3
"""

import json
import os
import sys
import unittest

import numpy as np
import shapely

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from pipeline.aps_metrics import (
    TRACK_LAT_NORTH,
    TRACK_LAT_SOUTH,
    TRACK_LON_WEST,
    TRACK_LON_EAST,
    compute_daily_aps_metrics,
)
from pipeline.download_gfs_forecast import FORECAST_FIELDS
from pipeline.paths import resolve_project_path
from pipeline.spatial_geometry import download_and_load_natural_earth_10m


class TestGFSMetrics(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.gfs_path = resolve_project_path("data/processed/gfs_forecast_aps.json")
        cls.land_union = download_and_load_natural_earth_10m()
        cls.lats = np.linspace(-48.0, -18.0, 121)
        cls.lons = np.linspace(-120.0, -70.0, 201)

    def _load_forecast(self):
        if not self.gfs_path.exists():
            self.skipTest("JSON GFS no generado aún")
        with open(self.gfs_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload["forecast"]

    def test_schema_and_lengths(self):
        """
        El JSON GFS debe traer todos los campos V5.3 con longitudes iguales.
        """
        forecast = self._load_forecast()
        missing = [field for field in FORECAST_FIELDS if field not in forecast]
        self.assertEqual(missing, [], f"Faltan campos GFS: {missing}")

        lengths = {field: len(forecast[field]) for field in FORECAST_FIELDS}
        self.assertEqual(len(set(lengths.values())), 1, f"Longitudes inconsistentes: {lengths}")
        self.assertGreaterEqual(lengths["dates"], 5)

    def test_centers_within_domain_and_ocean(self):
        """
        Los centros GFS deben quedar dentro del dominio ERA5 y fuera de tierra.
        """
        forecast = self._load_forecast()

        for key in ["lat_core", "lat_centroid"]:
            values = np.asarray(forecast[key], dtype=float)
            valid = values[np.isfinite(values)]
            self.assertTrue(np.all(valid >= TRACK_LAT_SOUTH))
            self.assertTrue(np.all(valid <= TRACK_LAT_NORTH))

        for key in ["lon_core", "lon_centroid"]:
            values = np.asarray(forecast[key], dtype=float)
            valid = values[np.isfinite(values)]
            self.assertTrue(np.all(valid >= TRACK_LON_WEST))
            self.assertTrue(np.all(valid <= TRACK_LON_EAST))

        core_lons = np.asarray(forecast["lon_core"], dtype=float)
        core_lats = np.asarray(forecast["lat_core"], dtype=float)
        cent_lons = np.asarray(forecast["lon_centroid"], dtype=float)
        cent_lats = np.asarray(forecast["lat_centroid"], dtype=float)

        core_land = shapely.contains_xy(self.land_union, core_lons, core_lats)
        cent_land = shapely.contains_xy(self.land_union, cent_lons, cent_lats)
        self.assertEqual(int(np.sum(core_land)), 0, "Núcleos GFS sobre tierra")
        self.assertEqual(int(np.sum(cent_land)), 0, "Centroides GFS sobre tierra")

    def test_synthetic_vortex_recovered(self):
        """
        Un vórtice gaussiano sintético debe recuperarse con error < 0.02°.
        """
        true_lat = -33.37
        true_lon = -95.62
        true_pmax = 1026.85

        lon_2d, lat_2d = np.meshgrid(self.lons, self.lats)
        synthetic = 1012.0 + (true_pmax - 1012.0) * np.exp(
            -0.5 * (((lon_2d - true_lon) / 6.0) ** 2 + ((lat_2d - true_lat) / 4.0) ** 2)
        )

        metrics = compute_daily_aps_metrics(
            synthetic, self.lats, self.lons,
            land_union=self.land_union,
            apply_smoothing=False,
        )
        self.assertIsNotNone(metrics)
        self.assertLess(abs(metrics["lat_core"] - true_lat), 0.02)
        self.assertLess(abs(metrics["lon_core"] - true_lon), 0.02)
        self.assertLess(abs(metrics["p_max_fit"] - true_pmax), 0.05)


if __name__ == "__main__":
    unittest.main()
