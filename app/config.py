"""Configuration par variables d'environnement."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "oui", "on")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str
    port: int
    user: str
    password: str
    max_upload_mb: int
    trust_forwarded: bool

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_dir=Path(os.environ.get("SCENARIO_DATA_DIR", "./data")).resolve(),
            host=os.environ.get("SCENARIO_HOST", "0.0.0.0"),
            port=int(os.environ.get("SCENARIO_PORT", "8080")),
            user=os.environ.get("SCENARIO_USER", "scenario"),
            password=os.environ.get("SCENARIO_PASSWORD", ""),
            max_upload_mb=int(os.environ.get("SCENARIO_MAX_UPLOAD_MB", "50")),
            trust_forwarded=_bool(os.environ.get("SCENARIO_TRUST_FORWARDED")),
        )
