"""Banco de horas: realizado, previsto e saldo acumulado por dia (minutos inteiros).

As regras (`expected`, `build`) são puras; `compute` só junta o banco, o tempo medido e elas.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta, tzinfo

from jornada import metrics

DIA_MINUTOS = 480
SEM_EXPEDIENTE = ("feriado", "dayoff")
Schedule = list[tuple[date, list[int]]]  # (vale desde, minutos seg..dom), ordenada


@dataclass(frozen=True)
class Override:
    worked: int | None = None
    expected: int | None = None
    kind: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class Day:
    date: date
    measured: int
    worked: int
    expected: int
    delta: int
    balance: int
    override: Override

    @property
    def balance_days(self) -> float:
        return self.balance / DIA_MINUTOS


def expected(dia: date, schedule: Schedule, override: Override | None = None) -> int:
    """Minutos previstos: o override do dia, senão 0 em feriado/dayoff, senão a jornada vigente."""
    if override is not None:
        if override.expected is not None:
            return override.expected
        if override.kind in SEM_EXPEDIENTE:
            return 0
    vigente = [minutos for inicio, minutos in schedule if inicio <= dia]
    return vigente[-1][dia.weekday()] if vigente else 0


def build(
    dias: list[date],
    measured: dict[date, int],
    overrides: dict[date, Override],
    schedule: Schedule,
    hoje: date,
    saldo_inicial: int = 0,
) -> list[Day]:
    """Um `Day` por data de `dias` (em ordem); dias depois de `hoje` não movem o saldo."""
    saldo = saldo_inicial
    saida: list[Day] = []
    for dia in dias:
        ov = overrides.get(dia, Override())
        medido = measured.get(dia, 0)
        realizado = ov.worked if ov.worked is not None else medido
        previsto = expected(dia, schedule, ov)
        delta = realizado - previsto if dia <= hoje else 0
        saldo += delta
        saida.append(Day(dia, medido, realizado, previsto, delta, saldo, ov))
    return saida


def load_schedule(con: sqlite3.Connection) -> Schedule:
    linhas = con.execute("SELECT start_date, minutes FROM schedule ORDER BY start_date")
    return [(date.fromisoformat(d), json.loads(m)) for d, m in linhas]


def load_overrides(con: sqlite3.Connection) -> dict[date, Override]:
    linhas = con.execute("SELECT date, worked_override, expected_override, kind, note FROM day")
    return {date.fromisoformat(d): Override(w, e, k, n) for d, w, e, k, n in linhas}


def measured_minutes(con: sqlite3.Connection, dia: date, tz: tzinfo | None = None) -> int:
    return int(metrics.active_seconds(metrics.load_spans(con, dia, tz), dia, tz) // 60)


def compute(
    con: sqlite3.Connection,
    ate: date | None = None,
    hoje: date | None = None,
    tz: tzinfo | None = None,
) -> list[Day]:
    """Do primeiro dia com ajuste até `ate` (padrão: hoje); vazio sem nenhum dia lançado."""
    hoje = hoje or date.today()  # noqa: DTZ011 - dia local
    overrides = load_overrides(con)
    if not overrides:
        return []
    primeiro = min(overrides)
    ultimo = max(ate or hoje, primeiro)
    dias = [primeiro + timedelta(n) for n in range((ultimo - primeiro).days + 1)]
    medidos = {
        d: measured_minutes(con, d, tz)
        for d in dias
        if d <= hoje and overrides.get(d, Override()).worked is None
    }
    return build(dias, medidos, overrides, load_schedule(con), hoje)


def format_signed(minutos: int) -> str:
    """`+12h30` / `-1h05`."""
    sinal = "-" if minutos < 0 else "+"
    m = abs(minutos)
    return f"{sinal}{m // 60}h{m % 60:02d}"


def balance_line(minutos: int) -> str:
    """`Saldo: +12h30 (1,6 dia)`."""
    dias = f"{minutos / DIA_MINUTOS:.1f}".replace(".", ",")
    return f"Saldo: {format_signed(minutos)} ({dias} dia)"
