"""Diretórios XDG de dados, config e estado do jornada."""

import os
from pathlib import Path

_APP = "jornada"


def _xdg(var: str, default: str) -> Path:
    base = os.environ.get(var)
    return Path(base) if base else Path.home() / default


def home_override() -> Path | None:
    """`JORNADA_HOME` redireciona dados, config e estado para uma só pasta (testes)."""
    valor = os.environ.get("JORNADA_HOME")
    return Path(valor) if valor else None


def data_dir() -> Path:
    raiz = home_override()
    return raiz / "data" if raiz else _xdg("XDG_DATA_HOME", ".local/share") / _APP


def config_dir() -> Path:
    raiz = home_override()
    return raiz / "config" if raiz else _xdg("XDG_CONFIG_HOME", ".config") / _APP


def state_dir() -> Path:
    raiz = home_override()
    return raiz / "state" if raiz else _xdg("XDG_STATE_HOME", ".local/state") / _APP


def config_file() -> Path:
    """`JORNADA_CONFIG` aponta direto para o arquivo de configuração."""
    valor = os.environ.get("JORNADA_CONFIG")
    return Path(valor) if valor else config_dir() / "config.toml"


def db_file() -> Path:
    return data_dir() / "jornada.db"


def captures_dir() -> Path:
    return data_dir() / "capturas"
