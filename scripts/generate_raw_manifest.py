#!/usr/bin/env python3
"""
Genera los inventarios SHA-256 de los NetCDF crudos locales previos a la migración al NAS.
Laboratorio de Oceanografía Física (LOFA) - Universidad Austral de Chile (UACh).
Licencia: GNU AGPLv3.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from pipeline.file_utils import temp_path_for

DATASETS = (
    ("era5", "data/raw/mean_sea_level_pressure", "era5_mslp_pacifico_*.nc", "data/processed/era5_raw_manifest.json"),
    ("ncep", "data/raw/ncep_reanalysis", "slp.*.nc", "data/processed/ncep_raw_manifest.json"),
)


def sha256_file(path, chunk_size=8 * 1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def year_from_name(filename):
    found = re.search(r"(?<!\d)(?:19|20)\d{2}(?!\d)", filename)
    return int(found.group(0)) if found else None


def build_manifest(dataset, source_dir, pattern, output_path, project_root):
    entries = []
    for path in sorted(source_dir.glob(pattern)):
        entries.append({
            "filename": path.name,
            "year": year_from_name(path.name),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "source": path.relative_to(project_root).as_posix(),
        })

    payload = {
        "dataset": dataset,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": source_dir.relative_to(project_root).as_posix(),
        "file_count": len(entries),
        "total_bytes": sum(item["size_bytes"] for item in entries),
        "files": entries,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = temp_path_for(output_path)
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(temporary, output_path)
    return payload


def main():
    parser = argparse.ArgumentParser(description="Genera manifiestos SHA-256 de los NetCDF crudos locales.")
    parser.add_argument("--project-root", default=str(BASE_DIR), help="Raíz del proyecto que contiene data/raw/.")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    for dataset, source_rel, pattern, output_rel in DATASETS:
        payload = build_manifest(
            dataset,
            project_root / source_rel,
            pattern,
            project_root / output_rel,
            project_root,
        )
        print(f"{dataset}: {payload['file_count']} archivos, {payload['total_bytes']} bytes -> {project_root / output_rel}")


if __name__ == "__main__":
    main()
