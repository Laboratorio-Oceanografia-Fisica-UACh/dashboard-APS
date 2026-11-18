"""
Utilidades de rutas del pipeline del Anticiclón del Pacífico Sur.
Las rutas relativas se resuelven contra la raíz del proyecto.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APS_DATA_ROOT_ENV = "APS_DATA_ROOT"


def get_aps_data_root():
    """
    Devuelve la raíz externa de datos definida en APS_DATA_ROOT, si existe.
    """
    valor = os.environ.get(APS_DATA_ROOT_ENV)
    if not valor:
        return None
    return Path(valor).expanduser()


def resolve_project_path(value):
    """
    Resuelve rutas relativas contra la raíz del proyecto o contra APS_DATA_ROOT.
    Solo las rutas que empiezan por data/ se redirigen a APS_DATA_ROOT;
    las rutas absolutas y el resto de rutas relativas se respetan tal cual.
    """
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    data_root = get_aps_data_root()
    if data_root is not None and path.parts and path.parts[0] == "data":
        return data_root / path
    return PROJECT_ROOT / path


def ensure_parent_dir(path):
    """
    Crea el directorio padre de un archivo de salida si no existe.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
