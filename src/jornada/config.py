"""Configuração em TOML com defaults; o arquivo ausente vale os defaults."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from jornada import paths


@dataclass(frozen=True)
class Config:
    db_path: Path = field(default_factory=paths.db_file)
    start_paused: bool = False
    web_port: int = 8765
    capture_enabled: bool = False
    capture_interval: int = 60
    capture_width: int = 640
    capture_retention_days: int = 30


def load(arquivo: Path | None = None) -> Config:
    arquivo = arquivo or paths.config_file()
    if not arquivo.exists():
        return Config()
    with arquivo.open("rb") as f:
        dados = tomllib.load(f)
    padrao = Config()
    cap = dados.get("capture", {})
    return Config(
        db_path=Path(dados.get("db_path", padrao.db_path)).expanduser(),
        start_paused=bool(dados.get("start_paused", padrao.start_paused)),
        web_port=int(dados.get("web", {}).get("port", padrao.web_port)),
        capture_enabled=bool(cap.get("enabled", padrao.capture_enabled)),
        capture_interval=int(cap.get("intervalSeconds", padrao.capture_interval)),
        capture_width=int(cap.get("width", padrao.capture_width)),
        capture_retention_days=int(cap.get("retentionDays", padrao.capture_retention_days)),
    )
