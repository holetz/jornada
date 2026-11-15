"""Tempo ativo por dia local, como união de intervalos (puro; o SQL só seleciona os spans).

Ativo = (entrada ativa menos tela bloqueada) unido ao microfone e à câmera em uso, recortado no
dia local e descontada a pausa.
"""

import sqlite3
from datetime import UTC, date, datetime, time, timedelta, tzinfo

Interval = tuple[float, float]
Span = tuple[str, str, float, float]  # (source, state, start, end)


def merge(intervalos: list[Interval]) -> list[Interval]:
    """União: ordenada, sem sobreposição; intervalos vazios caem."""
    saida: list[Interval] = []
    for ini, fim in sorted(i for i in intervalos if i[1] > i[0]):
        if saida and ini <= saida[-1][1]:
            saida[-1] = (saida[-1][0], max(saida[-1][1], fim))
        else:
            saida.append((ini, fim))
    return saida


def subtract(base: list[Interval], tirar: list[Interval]) -> list[Interval]:
    """`base` menos `tirar`, ambos já unidos (`merge`)."""
    saida: list[Interval] = []
    for ini, fim in base:
        atual = ini
        for t_ini, t_fim in tirar:
            if t_fim <= atual or t_ini >= fim:
                continue
            if t_ini > atual:
                saida.append((atual, t_ini))
            atual = max(atual, t_fim)
        if atual < fim:
            saida.append((atual, fim))
    return saida


def clip(intervalos: list[Interval], ini: float, fim: float) -> list[Interval]:
    return [(max(a, ini), min(b, fim)) for a, b in intervalos if min(b, fim) > max(a, ini)]


def local_tz() -> tzinfo:
    return datetime.now().astimezone().tzinfo or UTC


def day_bounds(dia: date, tz: tzinfo | None = None) -> Interval:
    """[00:00, 24:00) do dia local em epoch UTC; o dia de uma virada de horário tem 23 ou 25 h."""
    tz = tz or local_tz()
    ini = datetime.combine(dia, time.min, tzinfo=tz)
    fim = datetime.combine(dia + timedelta(days=1), time.min, tzinfo=tz)
    return ini.timestamp(), fim.timestamp()


def active_intervals(spans: list[Span], dia: date, tz: tzinfo | None = None) -> list[Interval]:
    """Os intervalos ativos do dia local, já unidos."""

    def de(source: str, state: str) -> list[Interval]:
        return merge([(a, b) for s, st, a, b in spans if s == source and st == state])

    base = subtract(de("input", "active"), de("lock", "locked"))
    ativo = merge(base + de("mic", "active") + de("camera", "active"))
    ativo = subtract(ativo, de("pause", "paused"))
    return clip(ativo, *day_bounds(dia, tz))


def active_seconds(spans: list[Span], dia: date, tz: tzinfo | None = None) -> float:
    return sum(b - a for a, b in active_intervals(spans, dia, tz))


def format_hm(segundos: float) -> str:
    """`5h12`: horas e minutos (truncados), minutos com dois dígitos."""
    minutos = int(segundos // 60)
    return f"{minutos // 60}h{minutos % 60:02d}"


def load_spans(con: sqlite3.Connection, dia: date, tz: tzinfo | None = None) -> list[Span]:
    """Só os spans que tocam o dia local."""
    ini, fim = day_bounds(dia, tz)
    return con.execute(
        "SELECT source, state, start, end FROM span WHERE end > ? AND start < ?", (ini, fim)
    ).fetchall()


def today(
    con: sqlite3.Connection, agora: float | None = None, tz: tzinfo | None = None
) -> tuple[float, datetime | None]:
    """Segundos ativos hoje e o início da primeira atividade do dia (hora local)."""
    tz = tz or local_tz()
    instante = datetime.fromtimestamp(agora, tz) if agora is not None else datetime.now(tz)
    dia = instante.date()
    intervalos = active_intervals(load_spans(con, dia, tz), dia, tz)
    desde = datetime.fromtimestamp(intervalos[0][0], tz) if intervalos else None
    return sum(b - a for a, b in intervalos), desde
