from datetime import date, datetime
from zoneinfo import ZoneInfo

from jornada import db, metrics, spans

SP = ZoneInfo("America/Sao_Paulo")
DIA = date(2026, 11, 3)


def ts(h, m=0, dia=DIA):
    return datetime(dia.year, dia.month, dia.day, h, m, tzinfo=SP).timestamp()


def test_merge_une_sobrepostos_e_adjacentes_e_descarta_vazios():
    assert metrics.merge([(5, 8), (1, 3), (2, 4), (9, 9)]) == [(1, 4), (5, 8)]
    assert metrics.merge([(1, 2), (2, 3)]) == [(1, 3)]


def test_subtract():
    assert metrics.subtract([(0, 10)], [(2, 3), (5, 7)]) == [(0, 2), (3, 5), (7, 10)]
    assert metrics.subtract([(0, 10)], [(-5, 20)]) == []
    assert metrics.subtract([(0, 4), (6, 10)], [(3, 7)]) == [(0, 3), (7, 10)]


def test_entrada_ativa_menos_bloqueio():
    sp = [
        ("input", "active", ts(9), ts(12)),
        ("lock", "locked", ts(10), ts(10, 30)),
    ]
    assert metrics.active_seconds(sp, DIA, SP) == 2.5 * 3600


def test_microfone_soma_sem_entrada_e_mesmo_bloqueado():
    sp = [
        ("input", "active", ts(9), ts(10)),
        ("mic", "active", ts(9, 30), ts(11)),
        ("lock", "locked", ts(10), ts(11)),
    ]
    # entrada 9h-10h unida ao mic 9h30-11h (o mic vale também com a tela bloqueada)
    assert metrics.active_seconds(sp, DIA, SP) == 2 * 3600


def test_pausa_desconta_de_tudo():
    sp = [
        ("input", "active", ts(9), ts(11)),
        ("mic", "active", ts(10), ts(12)),
        ("pause", "paused", ts(10, 30), ts(11, 30)),
    ]
    assert metrics.active_seconds(sp, DIA, SP) == 2 * 3600


def test_estados_inativos_nao_contam():
    sp = [("input", "idle", ts(9), ts(10)), ("mic", "inactive", ts(9), ts(10))]
    assert metrics.active_seconds(sp, DIA, SP) == 0


def test_recorte_na_virada_do_dia_local():
    # 23:00 de ontem a 01:00 de hoje no fuso de SP (UTC-3): só 1 h é de hoje
    sp = [("input", "active", ts(23, dia=date(2026, 11, 2)), ts(1))]
    assert metrics.active_seconds(sp, DIA, SP) == 3600
    assert metrics.active_seconds(sp, date(2026, 11, 2), SP) == 3600


def test_dia_local_nao_e_dia_utc():
    # 22:00 local = 01:00 UTC do dia seguinte; ainda é hoje em São Paulo
    sp = [("input", "active", ts(22), ts(23))]
    assert metrics.active_seconds(sp, DIA, SP) == 3600
    assert metrics.active_seconds(sp, date(2026, 11, 4), SP) == 0


def test_day_bounds_dia_de_23_horas():
    # 2018-11-04: São Paulo iniciou o horário de verão (00:00 → 01:00)
    ini, fim = metrics.day_bounds(date(2018, 11, 4), SP)
    assert fim - ini == 23 * 3600


def test_format_hm():
    assert metrics.format_hm(0) == "0h00"
    assert metrics.format_hm(5 * 3600 + 12 * 60 + 59) == "5h12"
    assert metrics.format_hm(9 * 60) == "0h09"


def test_today_le_do_banco_e_acha_o_inicio(tmp_path):
    con = db.connect(tmp_path / "j.db")
    for t in range(0, 3600 + 1, 5):
        spans.record(con, "input", "active", ts(8, 3) + t)
    spans.record(con, "input", "active", ts(1, dia=date(2026, 11, 2)))  # ontem, fora
    segundos, desde = metrics.today(con, agora=ts(15), tz=SP)
    assert segundos == 3600
    assert desde == datetime(2026, 11, 3, 8, 3, tzinfo=SP)
    assert metrics.today(con, agora=ts(15, dia=date(2026, 11, 5)), tz=SP) == (0, None)
