"""
Utilidades de validación y escritura segura de archivos del pipeline.
"""

from pathlib import Path
import os


def is_nonempty_file(path):
    """
    Indica si una ruta es un archivo existente y con contenido.
    Un archivo vacío se considera inválido o incompleto.
    """
    try:
        p = Path(path)
        return p.is_file() and p.stat().st_size > 0
    except OSError:
        return False


def temp_path_for(target):
    """
    Genera una ruta temporal única junto al archivo de destino.
    """
    target = Path(target)
    return target.with_name(f".{target.name}.{os.getpid()}.part")
