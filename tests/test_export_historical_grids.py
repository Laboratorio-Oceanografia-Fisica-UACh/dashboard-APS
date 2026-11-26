#!/usr/bin/env python3
"""
Regresiones del exportador diario de rejillas 2D reales.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from pipeline.calculate_aps_metrics import extract_latest_spatial_grid
from pipeline.export_historical_grids import (
    ANNUAL_NAME,
    MONTHLY_NAME,
    FULL_STRIDE,
    HISTORICAL_STRIDE,
    discover_netcdf_files,
    fecha_corte,
    stride_para_fecha,
)
from pipeline.grid_export import build_grid_document, load_grid_manifest, export_grid_documents


def _documento(modelo, fecha, filas, columnas):
    """Construye una rejilla mínima válida para pruebas de contrato."""
    lats = [-18.0 - i for i in range(filas)]
    lons = [-120.0 + i for i in range(columnas)]
    slp = [[1014.0 + 0.1 * i for _ in lons] for i, _ in enumerate(lats)]
    return build_grid_document(
        model_id=modelo,
        date=fecha,
        lats=lats,
        lons=lons,
        slp=slp,
        anomaly=[[0.0 for _ in lons] for _ in lats],
        forecast_hour=None,
        anomaly_reference="domain_spatial_mean",
    )


class TestExportadorHistorico(unittest.TestCase):

    def test_resolucion_por_ventana_reciente(self):
        """La ventana reciente usa 0.5° y el histórico 1.0°, sin interpolationes."""
        corte = fecha_corte("2026-11-10", 90)
        self.assertEqual(corte, "2026-08-13")
        self.assertEqual(stride_para_fecha("2026-11-10", corte), FULL_STRIDE)
        self.assertEqual(stride_para_fecha("2026-08-13", corte), FULL_STRIDE)
        self.assertEqual(stride_para_fecha("2026-08-12", corte), HISTORICAL_STRIDE)
        self.assertIsNone(fecha_corte("2026-11-10", 0))
        self.assertEqual(stride_para_fecha("1994-01-01", None), HISTORICAL_STRIDE)

    def test_nomenclatura_anual_y_mensual(self):
        """El exportador acepta ambos convenios, a diferencia del motor de métricas."""
        self.assertTrue(ANNUAL_NAME.match("era5_mslp_pacifico_1994.nc"))
        self.assertTrue(MONTHLY_NAME.match("era5_mslp_pacifico_2026_10.nc"))
        self.assertFalse(ANNUAL_NAME.match("era5_mslp_pacifico_2026_10.nc"))

        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            (raiz / "era5_mslp_pacifico_1994.nc").write_bytes(b"x")
            (raiz / "era5_mslp_pacifico_2026_10.nc").write_bytes(b"x")
            (raiz / "otro.nc").write_bytes(b"x")
            self.assertEqual(len(discover_netcdf_files(raiz)), 2)
            self.assertEqual(len(discover_netcdf_files(raiz, include_monthly=False)), 1)

    def test_lote_no_degrada_resolucion_publicada(self):
        """Un backfill reducido no debe sobrescribir una rejilla completa."""
        with tempfile.TemporaryDirectory() as temporal:
            completo = _documento("era5_reanalysis", "2026-10-31", 4, 5)
            reducido = _documento("era5_reanalysis", "2026-10-31", 2, 3)

            escritas, omitidas = export_grid_documents([completo], grids_dir=temporal)
            self.assertEqual(len(escritas), 1)

            escritas, omitidas = export_grid_documents([reducido], grids_dir=temporal)
            self.assertEqual(escritas, [])
            self.assertEqual(omitidas, [("era5_reanalysis", "2026-10-31")])

            manifiesto = load_grid_manifest(temporal)
            entrada = manifiesto["grids"]["era5_reanalysis"]["2026-10-31"]
            self.assertEqual(entrada["n_lats"], 4)

            # Con --force sí se permite la sustitución explícita.
            export_grid_documents([reducido], grids_dir=temporal, force=True)
            manifiesto = load_grid_manifest(temporal)
            self.assertEqual(
                manifiesto["grids"]["era5_reanalysis"]["2026-10-31"]["n_lats"], 2
            )

    def test_lote_actualiza_manifiesto_una_sola_vez(self):
        """Todas las fechas del lote quedan registradas y coherentes."""
        with tempfile.TemporaryDirectory() as temporal:
            documentos = [
                _documento("era5_reanalysis", "1994-01-01", 2, 3),
                _documento("era5_reanalysis", "1994-01-02", 2, 3),
                _documento("era5_reanalysis", "1994-01-03", 2, 3),
            ]
            escritas, _ = export_grid_documents(documentos, grids_dir=temporal)
            self.assertEqual(len(escritas), 3)

            manifiesto = load_grid_manifest(temporal)
            entradas = manifiesto["grids"]["era5_reanalysis"]
            self.assertEqual(len(entradas), 3)
            for fecha, entrada in entradas.items():
                ruta = Path(temporal) / entrada["file"]
                self.assertTrue(ruta.exists())
                documento = json.loads(ruta.read_text(encoding="utf-8"))
                self.assertEqual(documento["date"], fecha)
                self.assertEqual(documento["model_id"], "era5_reanalysis")

    def test_exportador_sin_campo_sintetico(self):
        """El exportador solo publica datos leídos: sin gaussianos ni aleatoriedad."""
        codigo = (BASE_DIR / "pipeline" / "export_historical_grids.py").read_text(
            encoding="utf-8"
        )
        for prohibido in ("np.random", "gauss", "generateSynopticPressureGrid"):
            self.assertNotIn(prohibido, codigo)

    def test_rejilla_vigente_debe_coincidir_con_payload(self):
        """Una rejilla desfasada nunca se publica como campo del mapa inicial."""
        import pandas as pd
        import xarray as xr

        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "era5_mslp_pacifico_2026_10.nc"
            tiempos = pd.date_range("2026-10-30", periods=2, freq="D")
            lats = np.arange(-18.0, -48.01, -0.25)
            lons = np.arange(-120.0, -69.99, 0.25)
            valores = np.full((2, len(lats), len(lons)), 102000.0, dtype="float32")
            ds = xr.Dataset(
                {"msl": (("valid_time", "latitude", "longitude"), valores)},
                coords={"valid_time": tiempos, "latitude": lats, "longitude": lons},
            )
            ds.to_netcdf(ruta)

            desfasado = pd.DataFrame({"date": ["2026-11-10"]})
            self.assertIsNone(extract_latest_spatial_grid(temporal, desfasado))

            coherente = pd.DataFrame({"date": ["2026-10-31"]})
            documento = extract_latest_spatial_grid(temporal, coherente)
            self.assertIsNotNone(documento)
            self.assertEqual(documento["date"], "2026-10-31")


if __name__ == "__main__":
    unittest.main()
