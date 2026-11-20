#!/usr/bin/env python3
"""
Pruebas de la climatología normal OMM 1994-2023 y de la ventana activa.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3
"""

import json
import os
import sys
import unittest
from pathlib import Path

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from pipeline.compute_climatology import (
    circular_mean_deg,
    compute_monthly_climatology,
    filter_period,
    load_wmo_climatology,
)
from pipeline.paths import resolve_project_path


class TestClimatology(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.cache_path = resolve_project_path("data/processed/era5_daily_aps_metrics.csv")
        cls.cache_exists = cls.cache_path.exists()

    def test_period_filter_excludes_boundaries(self):
        """
        El filtro 1994-2023 debe excluir 1993-12-31 y 2024-01-01.
        """
        frame = pd.DataFrame({
            "date": ["1993-12-31", "1994-01-01", "2023-12-31", "2024-01-01"],
            "month": [12, 1, 12, 1],
        })
        filtered = filter_period(frame, 1994, 2023)
        self.assertEqual(
            filtered["date"].tolist(),
            ["1994-01-01", "2023-12-31"],
        )

    def test_circular_mean_350_10_is_zero(self):
        """
        La media circular de 350° y 10° debe ser 0° (no 180°).
        """
        result = circular_mean_deg([350.0, 10.0])
        self.assertIsNotNone(result)
        self.assertLess(min(abs(result), abs(result - 360.0)), 1e-9)

    def test_json_contains_12_months(self):
        """
        El JSON canónico debe existir y contener 12 meses completos.
        """
        climatology = load_wmo_climatology()
        self.assertEqual(len(climatology["months"]), 12)
        self.assertEqual(climatology["months"], list(range(1, 13)))
        for key in ["p_max", "lat_core", "lon_core", "area_1020", "azimuth_deg"]:
            self.assertEqual(len(climatology[key]), 12)

    def test_compute_monthly_from_cache(self):
        """
        El cálculo mensual desde el caché debe producir 12 meses finitos.
        """
        if not self.cache_exists:
            self.skipTest("Caché ERA5 no disponible")
        frame = pd.read_csv(self.cache_path)
        climatology = compute_monthly_climatology(frame, 1994, 2023)
        self.assertEqual(len(climatology["months"]), 12)
        self.assertEqual(climatology["metadata"]["n_days"], 10957)
        for value in climatology["azimuth_deg"]:
            self.assertTrue(0.0 <= value < 360.0)


class TestActiveWindowOutputs(unittest.TestCase):
    """
    Verifica el contrato de la ventana activa publicado por el pipeline.
    """

    def test_web_json_starts_1993(self):
        json_path = resolve_project_path("web/data/latest_aps_data.json")
        if not json_path.exists():
            self.skipTest("JSON web no generado aún")
        with open(json_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        era5 = data["models"]["ERA5 Reanálisis"]
        self.assertGreaterEqual(era5["dates"][0], "1993-01-01")
        self.assertIn("active_window", data["metadata"])

    def test_cache_csv_keeps_1940(self):
        cache_path = resolve_project_path("data/processed/era5_daily_aps_metrics.csv")
        if not cache_path.exists():
            self.skipTest("Caché ERA5 no disponible")
        frame = pd.read_csv(cache_path, usecols=["date"])
        self.assertEqual(str(frame["date"].min()), "1940-01-01")

    def test_web_csv_starts_1993(self):
        web_csv = resolve_project_path("web/data/era5_daily_aps_metrics.csv")
        if not web_csv.exists():
            self.skipTest("CSV web no generado aún")
        frame = pd.read_csv(web_csv, usecols=["date"])
        self.assertGreaterEqual(str(frame["date"].min()), "1993-01-01")


if __name__ == "__main__":
    unittest.main()
