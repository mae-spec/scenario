"""Sauvegarde cohérente du dossier de données (base SQLite + fichiers originaux).

Usage : python -m app.backup [dossier_de_destination]
(dans Docker : docker compose exec scenario python -m app.backup /data/sauvegardes)
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from .config import Settings


def backup(data_dir: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"scenario-sauvegarde-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "scenario.db"
        src = sqlite3.connect(data_dir / "scenario.db")
        dst = sqlite3.connect(snap)
        with dst:
            src.backup(dst)  # copie cohérente même si l'application tourne
        src.close()
        dst.close()
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "scenario.db")
            for f in sorted((data_dir / "files").glob("*")):
                if f.is_file() and not f.name.endswith(".tmp"):
                    z.write(f, f"files/{f.name}")
    return target


def main() -> None:  # pragma: no cover
    settings = Settings.from_env()
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else settings.data_dir / "sauvegardes"
    print(backup(settings.data_dir, dest))


if __name__ == "__main__":  # pragma: no cover
    main()
