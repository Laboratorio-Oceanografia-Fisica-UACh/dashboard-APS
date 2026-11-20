"""
Utilidades de validación y escritura segura de archivos del pipeline.
"""

from pathlib import Path
import json
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


def _replace_atomically(temp_path, target):
    """
    Reemplaza el destino de forma atómica y limpia el temporal si algo falla.
    """
    try:
        os.replace(temp_path, target)
    except Exception:
        if Path(temp_path).exists():
            Path(temp_path).unlink()
        raise


def atomic_json_dump(obj, target, indent=2, ensure_ascii=False, allow_nan=False):
    """
    Escribe un JSON en dos fases (temporal + os.replace) para evitar
    archivos parciales ante interrupciones.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = temp_path_for(target)
    try:
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(obj, handle, indent=indent, ensure_ascii=ensure_ascii,
                      allow_nan=allow_nan)
        _replace_atomically(temp_path, target)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
    return target


def atomic_csv_dump(df, target, index=False, **to_csv_kwargs):
    """
    Escribe un DataFrame CSV en dos fases (temporal + os.replace) para evitar
    archivos parciales ante interrupciones.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = temp_path_for(target)
    try:
        df.to_csv(temp_path, index=index, **to_csv_kwargs)
        _replace_atomically(temp_path, target)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
    return target
