#!/usr/bin/env python3
"""
Regresiones de contratos de rejillas 2D, climatología y umbrales sinópticos.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh)
Licencia: GNU AGPLv3
"""

import json
import re
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from pipeline.grid_export import validate_grid_document


class TestGridContracts(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.web_js = BASE_DIR / "web" / "js"
        cls.grids_dir = BASE_DIR / "web" / "data" / "grids"
        cls.manifest_path = cls.grids_dir / "manifest.json"
        cls.payload_path = BASE_DIR / "web" / "data" / "latest_aps_data.json"
        cls.climatology_path = BASE_DIR / "web" / "data" / "climatology_series.json"

    def test_no_synthetic_grid_generator(self):
        """Ningún archivo JS del cliente puede contener el generador gaussiano."""
        offenders = []
        for path in sorted(self.web_js.glob("*.js")):
            text = path.read_text(encoding="utf-8")
            if "generateSynopticPressureGrid" in text:
                offenders.append(path.name)
        self.assertEqual(offenders, [], f"Generador sintético presente en: {offenders}")

    def test_frontend_regime_thresholds(self):
        """Los umbrales deben ser 300 km, 30-120° y 120-210°."""
        maps = (self.web_js / "maps.js").read_text(encoding="utf-8")
        main = (self.web_js / "main.js").read_text(encoding="utf-8")

        self.assertRegex(maps, r"distKm\s*&&\s*distKm\s*>=\s*300")
        self.assertRegex(maps, r"azimuth\s*>=\s*30\s*&&\s*azimuth\s*<\s*120")
        self.assertRegex(maps, r"azimuth\s*>=\s*120\s*&&\s*azimuth\s*<\s*210")

        self.assertRegex(main, r"distDec\s*<\s*300")
        self.assertRegex(main, r"azimuth\s*>=\s*30\s*&&\s*azimuth\s*<\s*120")
        self.assertRegex(main, r"azimuth\s*>=\s*120\s*&&\s*azimuth\s*<\s*210")

        self.assertNotRegex(maps, r"distKm\s*&&\s*distKm\s*>=\s*200")
        self.assertNotRegex(main, r"distDec\s*<\s*200")
        self.assertNotRegex(maps, r"azimuth\s*>=\s*45")
        self.assertNotRegex(main, r"azimuth\s*>=\s*45")

    def test_main_has_no_synthetic_defaults(self):
        """No deben reaparecer 1024.0, -33.5 ni -91.0 como respaldos."""
        main = (self.web_js / "main.js").read_text(encoding="utf-8")
        self.assertNotIn("1024.0", main)
        self.assertNotIn("-33.5", main)
        self.assertNotIn("-91.0", main)
        self.assertNotIn("Climatología Histórica LOFA", main)
        self.assertIn("Climatología Normal OMM", main)
        self.assertIn("p_max_fit", main)

    def test_web_payload_size_and_split(self):
        """El payload principal debe ser < 2 MB y no duplicar climatología."""
        self.assertTrue(self.payload_path.exists(), "Falta latest_aps_data.json")
        self.assertLess(
            self.payload_path.stat().st_size, 2_000_000,
            "El payload web alcanza o supera 2 MB",
        )
        payload = json.loads(self.payload_path.read_text(encoding="utf-8"))
        self.assertNotIn("spatial_grid", payload)
        self.assertNotIn("Climatología Normal OMM", payload.get("models", {}))

        self.assertTrue(
            self.climatology_path.exists(),
            "Falta climatology_series.json separado",
        )
        clim = json.loads(self.climatology_path.read_text(encoding="utf-8"))
        self.assertEqual(clim.get("schema_version"), 1)
        model = clim.get("model") or {}
        self.assertEqual(model.get("id"), "wmo_climatology_1994_2023")
        self.assertTrue(model.get("dates"))
        self.assertTrue(model.get("p_max_fit"))

    def test_climatology_series_reinserted_under_canonical_key(self):
        """La climatología separada debe quedar bajo la clave que consume el KPI."""
        main = (self.web_js / "main.js").read_text(encoding="utf-8")
        self.assertIn("payload.models['Climatología Normal OMM']", main)
        self.assertIn("rawData.models['Climatología Normal OMM']", main)
        self.assertIn("wmo_climatology_1994_2023", main)

    def test_exported_grids_match_manifest(self):
        """Cada rejilla debe coincidir con model_id/date y dimensiones del manifiesto."""
        if not self.manifest_path.exists():
            self.skipTest("Manifiesto de rejillas aún no generado")

        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest.get("schema_version"), 1)
        grids = manifest.get("grids") or {}
        self.assertIsInstance(grids, dict)

        for model_id, entries in grids.items():
            self.assertIsInstance(entries, dict)
            for date, entry in entries.items():
                relative = entry.get("file")
                self.assertTrue(relative, f"{model_id}/{date} sin archivo")
                grid_path = (self.grids_dir / relative).resolve()
                self.assertTrue(
                    str(grid_path).startswith(str(self.grids_dir.resolve())),
                    f"Ruta de rejilla fuera del directorio permitido: {relative}",
                )
                self.assertTrue(grid_path.exists(), f"Falta rejilla {relative}")

                document = json.loads(grid_path.read_text(encoding="utf-8"))
                self.assertEqual(document.get("model_id"), model_id)
                self.assertEqual(document.get("date"), date)
                self.assertIn("slp", document)
                self.assertEqual(len(document["slp"]), len(document["lats"]))
                for row in document["slp"]:
                    self.assertEqual(len(row), len(document["lons"]))
                if document.get("anomaly") is not None:
                    self.assertEqual(len(document["anomaly"]), len(document["lats"]))
                    for row in document["anomaly"]:
                        self.assertEqual(len(row), len(document["lons"]))
                validate_grid_document(document)

    def test_grid_validator_rejects_bad_shape(self):
        """La validación debe rechazar matrices incompletas y fechas inválidas."""
        bad_shape = {
            "model_id": "era5_reanalysis",
            "date": "2026-11-10",
            "lats": [-18.0, -18.5],
            "lons": [-120.0, -119.5],
            "slp": [[1014.0, 1014.2]],
            "anomaly": None,
        }
        with self.assertRaises(ValueError):
            validate_grid_document(bad_shape)

        bad_date = dict(bad_shape)
        bad_date["date"] = "10-11-2026"
        bad_date["slp"] = [[1014.0, 1014.2], [1013.8, 1014.1]]
        with self.assertRaises(ValueError):
            validate_grid_document(bad_date)

    def test_calculate_aps_metrics_ignores_monthly_nc(self):
        """El pipeline debe parsear años con regex estricta de 4 dígitos,
        jamás con int() sobre el nombre de archivo."""
        src = (BASE_DIR / "pipeline" / "calculate_aps_metrics.py").read_text(encoding="utf-8")

        # Patrón ingenuo prohibido: int(...replace("era5_mslp_pacifico_", ""))
        self.assertNotIn('replace("era5_mslp_pacifico_", "")', src)
        self.assertNotIn("replace('era5_mslp_pacifico_', '')", src)

        # Regex estricta de 4 dígitos obligatoria
        self.assertIn(r"era5_mslp_pacifico_(\d{4})\.nc", src)

    def test_frontend_has_no_wrong_plan_or_null_crash(self):
        """El cliente no debe contener restos del plan incorrecto ni accesos a
        nodos inexistentes, y debe proteger el trazado de isóbaras."""
        main = (self.web_js / "main.js").read_text(encoding="utf-8")
        self.assertNotIn("spatial_grids_by_date", main)
        self.assertNotIn("era5_reanalisis", main)
        # El bug real era el ID inexistente, no el nombre de la variable local.
        self.assertNotIn("getElementById('openCitationBtn')", main)
        self.assertIn("getElementById('openCitationModalBtn')", main)

        charts = (self.web_js / "charts.js").read_text(encoding="utf-8")
        self.assertNotIn("selectedModelIds", charts)

        maps = (self.web_js / "maps.js").read_text(encoding="utf-8")
        guard_idx = maps.find("!field")
        contour_idx = maps.find("MarchingSquares.contour")
        self.assertGreaterEqual(guard_idx, 0, "Falta la guardia !field en maps.js")
        self.assertGreaterEqual(
            contour_idx, 0, "Falta la llamada a MarchingSquares.contour en maps.js"
        )
        self.assertLess(
            guard_idx,
            contour_idx,
            "La guardia !field debe aparecer antes de MarchingSquares.contour",
        )

        # Regresión: forecastTag/dateNotice deben vivir en el ámbito de la función,
        # no dentro de if (hasCore), porque el popup del centroide también los usa.
        before_core = maps.split("if (hasCore) {")[0]
        self.assertIn("const dateNotice", before_core)
        self.assertIn("const forecastTag", before_core)

        css = (BASE_DIR / "web" / "styles" / "main.css").read_text(encoding="utf-8")
        self.assertIn(".map-grid-notice[hidden]", css)

    def test_sync_nas_workflow_adds_grids_and_climatology(self):
        """El workflow de sincronización NAS debe commitear rejillas y
        climatología en su paso git add."""
        workflow_path = BASE_DIR / ".github" / "workflows" / "sync-from-nas.yml"
        self.assertTrue(
            workflow_path.exists(), "Falta .github/workflows/sync-from-nas.yml"
        )
        text = workflow_path.read_text(encoding="utf-8")
        add_idx = text.find("git add")
        self.assertGreaterEqual(add_idx, 0, "Falta el paso 'git add' en el workflow")
        add_block = text[add_idx:]
        self.assertIn("web/data/climatology_series.json", add_block)
        self.assertIn("web/data/grids", add_block)


if __name__ == "__main__":
    unittest.main()
