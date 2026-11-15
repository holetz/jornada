"""Regras de detecção por máquina, guardadas como JSON na chave `detection` da tabela `meta`.

A página de depuração e a CLI (`jornada settings`) escrevem; o coletor relê a cada tick, então
uma regra nova vale no tick seguinte, sem reiniciar o serviço. As chaves externas seguem o
camelCase pontuado do `config.toml` (`input.idleSeconds`).
"""

import json
import sqlite3
from dataclasses import dataclass, replace

META_KEY = "detection"


@dataclass(frozen=True)
class Settings:
    idle_seconds: int = 180
    min_streak_seconds: int = 10
    streak_gap_seconds: int = 10
    ignore_apps: tuple[str, ...] = ()
    mic_enabled: bool = True
    mic_min_seconds: int = 0
    camera_enabled: bool = False
    camera_min_seconds: int = 0
    events_verbose: bool = False
    events_retention_days: int = 7

    def ignores(self, app: str | None) -> bool:
        """O app em foco (`wm_class`) está na lista de ignorados, sem diferenciar maiúsculas."""
        if not app:
            return False
        alvo = app.casefold()
        return any(item.casefold() == alvo for item in self.ignore_apps)


# chave externa -> (atributo, tipo, mínimo, máximo); a ordem é a da página e da CLI
FIELDS: dict[str, tuple[str, type, int | None, int | None]] = {
    "input.idleSeconds": ("idle_seconds", int, 30, 3600),
    "input.minStreakSeconds": ("min_streak_seconds", int, 0, 300),
    "input.streakGapSeconds": ("streak_gap_seconds", int, 1, 120),
    "input.ignoreApps": ("ignore_apps", list, None, None),
    "mic.enabled": ("mic_enabled", bool, None, None),
    "mic.minSeconds": ("mic_min_seconds", int, 0, 600),
    "camera.enabled": ("camera_enabled", bool, None, None),
    "camera.minSeconds": ("camera_min_seconds", int, 0, 600),
    "events.verbose": ("events_verbose", bool, None, None),
    "events.retentionDays": ("events_retention_days", int, 1, 90),
}


def to_dict(s: Settings) -> dict:
    saida = {}
    for chave, (atributo, tipo, _, _) in FIELDS.items():
        valor = getattr(s, atributo)
        saida[chave] = list(valor) if tipo is list else valor
    return saida


def diff(antes: dict, depois: dict) -> str:
    """As chaves que mudaram entre dois `to_dict`, em texto para o evento `config`."""
    mudancas = [f"{k}: {antes[k]!r} → {depois[k]!r}" for k in depois if antes.get(k) != depois[k]]
    return "; ".join(mudancas) or "sem mudanças"


def _coerce(chave: str, valor: object) -> object:
    _, tipo, minimo, maximo = FIELDS[chave]
    if tipo is bool:
        if not isinstance(valor, bool):
            raise ValueError(f"{chave} deve ser true ou false")
        return valor
    if tipo is int:
        if isinstance(valor, bool) or not isinstance(valor, int) or not minimo <= valor <= maximo:
            raise ValueError(f"{chave} deve ser inteiro entre {minimo} e {maximo}")
        return valor
    if not isinstance(valor, list) or not all(isinstance(v, str) for v in valor):
        raise ValueError(f"{chave} deve ser uma lista de textos")
    return tuple(v.strip() for v in valor if v.strip())


def validate(dados: dict) -> Settings:
    """As regras a partir dos padrões, com só as chaves presentes; ValueError na inválida."""
    if not isinstance(dados, dict):
        raise ValueError("as regras devem ser um objeto")
    mudancas = {}
    for chave, valor in dados.items():
        if chave not in FIELDS:
            raise ValueError(f"regra desconhecida: {chave}")
        mudancas[FIELDS[chave][0]] = _coerce(chave, valor)
    return replace(Settings(), **mudancas)


def load(con: sqlite3.Connection) -> Settings:
    """As regras gravadas; ausentes valem os padrões. JSON ou regra inválida levanta ValueError."""
    linha = con.execute("SELECT value FROM meta WHERE key = ?", (META_KEY,)).fetchone()
    if linha is None:
        return Settings()
    try:
        dados = json.loads(linha[0])
    except json.JSONDecodeError as e:
        raise ValueError(f"regras gravadas ilegíveis: {e}") from e
    return validate(dados)


def save(con: sqlite3.Connection, s: Settings) -> None:
    with con:
        con.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (META_KEY, json.dumps(to_dict(s), ensure_ascii=False)),
        )


def reset(con: sqlite3.Connection) -> None:
    with con:
        con.execute("DELETE FROM meta WHERE key = ?", (META_KEY,))


def parse_assignment(texto: str) -> tuple[str, object]:
    """`chave=valor` da CLI: valor JSON quando decodifica, senão texto; listas aceitam vírgulas."""
    chave, sep, bruto = texto.partition("=")
    chave = chave.strip()
    if not sep or not chave:
        raise ValueError(f"esperado chave=valor: {texto!r}")
    try:
        valor = json.loads(bruto)
    except json.JSONDecodeError:
        valor = bruto.strip()
    if chave in FIELDS and FIELDS[chave][1] is list and isinstance(valor, str):
        valor = [v.strip() for v in valor.split(",") if v.strip()]
    return chave, valor


def apply_assignments(atual: Settings, pares: list[tuple[str, object]]) -> Settings:
    dados = to_dict(atual)
    dados.update(pares)
    return validate(dados)
