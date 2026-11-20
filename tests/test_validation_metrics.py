#!/usr/bin/env python3
"""
Pruebas de las métricas objetivas de validación del APS (Fase 3).
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3
"""

import os
import sys
import unittest

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from pipeline.aps_metrics import willmott_d
from pipeline.compute_climatology import load_wmo_climatology
from pipeline.validation_metrics import (
    REFERENCE_CLIMATOLOGY,
    build_validation_metrics,
    compute_series_metrics,
    compute_gfs_verification,
)


def _frame(dates, p_max, lat_core, lon_core):
    return pd.DataFrame({
        "date": dates,
        "p_max_fit": p_max,
        "lat_core": lat_core,
        "lon_core": lon_core,
    })


class TestWillmott(unittest.TestCase):

    def test_perfect_agreement_is_one(self):
        values = [1020.0, 1022.0, 1024.0, 1021.0]
        self.assertAlmostEqual(willmott_d(values, values), 1.0, places=12)

    def test_constant_bias_is_zero(self):
        reference = [1020.0, 1020.0, 1020.0]
        model = [1022.0, 1022.0, 1022.0]
        self.assertAlmostEqual(willmott_d(model, reference), 0.0, places=12)

    def test_opposite_phase_is_zero(self):
        model = [1.0, 2.0, 3.0, 4.0]
        reference = [4.0, 3.0, 2.0, 1.0]
        self.assertAlmostEqual(willmott_d(model, reference), 0.0, places=12)

    def test_zero_denominator_returns_none(self):
        constant = [1020.0, 1020.0, 1020.0]
        self.assertIsNone(willmott_d(constant, constant))

    def test_insufficient_pairs_returns_none(self):
        self.assertIsNone(willmott_d([1020.0], [1020.0], min_pairs=2))


class TestSeriesAlignment(unittest.TestCase):

    def test_alignment_by_date_not_index(self):
        model = _frame(
            ["2020-01-01", "2020-01-02"],
            [1020.0, 1022.0],
            [-30.0, -31.0],
            [-90.0, -91.0],
        )
        reference = _frame(
            ["2020-01-02", "2020-01-01"],
            [1022.0, 1020.0],
            [-31.0, -30.0],
            [-91.0, -90.0],
        )
        metrics = compute_series_metrics(model, reference)
        self.assertEqual(metrics["n_pairs"], 2)
        self.assertAlmostEqual(metrics["rmse_psa_hpa"], 0.0, places=9)
        self.assertAlmostEqual(metrics["willmott_d"], 1.0, places=9)
        self.assertAlmostEqual(metrics["dist_error_km"], 0.0, places=6)

    def test_insufficient_pairs_publishes_null(self):
        model = _frame(["2020-01-01"], [1020.0], [-30.0], [-90.0])
        reference = _frame(["2020-01-01"], [1021.0], [-31.0], [-91.0])
        metrics = compute_series_metrics(model, reference)
        self.assertEqual(metrics["n_pairs"], 1)
        self.assertIsNone(metrics["rmse_psa_hpa"])
        self.assertIsNone(metrics["willmott_d"])
        self.assertIsNone(metrics["dist_error_km"])


class TestValidationRows(unittest.TestCase):

    def test_era5_vs_climatology_row(self):
        climatology = load_wmo_climatology()
        dates = pd.date_range("2020-01-01", periods=10, freq="D").strftime("%Y-%m-%d")
        era5 = _frame(dates, np.linspace(1020, 1026, 10), np.linspace(-30, -35, 10),
                      np.linspace(-90, -95, 10))
        rows = build_validation_metrics(era5, climatology)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reference"], REFERENCE_CLIMATOLOGY)
        self.assertEqual(rows[0]["skill_type"], "historical_concordance")
        self.assertEqual(rows[0]["n_pairs"], 10)

    def test_gfs_vs_era5_only_when_pairs_exist(self):
        cache = _frame(
            ["2020-01-01", "2020-01-02", "2020-01-03"],
            [1020.0, 1022.0, 1024.0],
            [-30.0, -31.0, -32.0],
            [-90.0, -91.0, -92.0],
        )
        history = pd.DataFrame({
            "cycle": ["20200101 00Z", "20200101 00Z"],
            "generated_at": ["2020-01-01T00:00:00Z", "2020-01-01T00:00:00Z"],
            "dates": ["2020-01-01", "2020-01-02"],
            "p_max_fit": [1020.0, 1022.0],
            "lat_core": [-30.0, -31.0],
            "lon_core": [-90.0, -91.0],
        })
        verification = compute_gfs_verification(history, cache)
        self.assertEqual(verification["n_pairs"], 2)
        self.assertAlmostEqual(verification["metrics"]["rmse_psa_hpa"], 0.0, places=9)
        self.assertEqual(len(verification["pairs"]), 2)


if __name__ == "__main__":
    unittest.main()
