"""
Pruebas unitarias de resolución y validación de credenciales Copernicus CDS.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile.
"""

import os
import unittest
from unittest.mock import patch
from pathlib import Path

from pipeline.download_era5 import check_cds_credentials


class TestCDSCredentials(unittest.TestCase):
    """Verifica la lógica determinista de validación de credenciales CDS."""

    @patch.dict(os.environ, {}, clear=True)
    @patch.object(Path, "exists", return_value=False)
    def test_missing_credentials_returns_false(self, mock_exists):
        """Sin env vars ni ~/.cdsapirc, check_cds_credentials debe retornar False."""
        self.assertFalse(check_cds_credentials())

    @patch.dict(os.environ, {"CDSAPI_KEY": "dummy-token-uuid-1234"}, clear=True)
    @patch.object(Path, "exists", return_value=False)
    def test_key_in_env_returns_true(self, mock_exists):
        """Con CDSAPI_KEY en variables de entorno, check_cds_credentials debe retornar True."""
        self.assertTrue(check_cds_credentials())

    @patch.dict(os.environ, {}, clear=True)
    def test_rc_file_detected_if_exists(self):
        """Si ~/.cdsapirc existe en disco, debe considerarse válido."""
        rc_path = Path.home() / ".cdsapirc"
        if rc_path.exists():
            self.assertTrue(check_cds_credentials())


if __name__ == "__main__":
    unittest.main()

