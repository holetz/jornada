from datetime import date

from jornada import db, ledger
from jornada.ledger import Override

SEMANA = [480, 480, 480, 480, 480, 0, 0]
SCHEDULE = [(date(2025, 9, 22), SEMANA)]
SEG, TER, QUA, SAB = date(2025, 10, 6), date(2025, 10, 7), date(2025, 10, 8), date(2025, 10, 11)


def run(dias, measured=None, overrides=None, schedule=SCHEDULE, hoje=date(2030, 1, 1)):
    return ledger.build(dias, measured or {}, overrides or {}, schedule, hoje)


def test_dia_util_usa_a_jornada_e_o_medido():
    (d,) = run([SEG], {SEG: 500})
    assert (d.worked, d.expected, d.delta, d.balance) == (500, 480, 20, 20)


def test_fim_de_semana_nao_tem_previsto():
    (d,) = run([SAB], {SAB: 60})
    assert (d.expected, d.delta) == (0, 60)


def test_override_de_realizado_vale_mais_que_o_medido():
    (d,) = run([SEG], {SEG: 500}, {SEG: Override(worked=300)})
    assert (d.measured, d.worked, d.delta) == (500, 300, -180)


def test_feriado_e_dayoff_zeram_o_previsto():
    for kind in ("feriado", "dayoff"):
        (d,) = run([SEG], overrides={SEG: Override(kind=kind)})
        assert (d.expected, d.delta) == (0, 0)


def test_ausencia_e_ajuste_mantem_o_previsto():
    (d,) = run([SEG], overrides={SEG: Override(kind="ausencia")})
    assert d.expected == 480


def test_override_de_previsto_vence_o_feriado():
    (d,) = run([SEG], overrides={SEG: Override(kind="feriado", expected=240)})
    assert d.expected == 240


def test_saldo_acumula_e_converte_em_dias():
    dias = run([SEG, TER, QUA], {SEG: 600, TER: 480, QUA: 360})
    assert [d.balance for d in dias] == [120, 120, 0]
    assert dias[0].balance_days == 0.25


def test_troca_de_jornada_vale_da_data_em_diante():
    schedule = [*SCHEDULE, (TER, [420] * 5 + [0, 0])]
    seg, ter = run([SEG, TER], schedule=schedule)
    assert (seg.expected, ter.expected) == (480, 420)


def test_antes_da_primeira_jornada_nao_ha_previsto():
    (d,) = run([date(2025, 9, 1)])
    assert d.expected == 0


def test_dias_futuros_nao_movem_o_saldo():
    _seg, ter = run([SEG, TER], {SEG: 500}, hoje=SEG)
    assert (ter.delta, ter.balance) == (0, 20)


def test_compute_vazio_sem_dias_lancados(tmp_path):
    con = db.connect(tmp_path / "j.db")
    assert ledger.compute(con, hoje=SEG) == []


def test_compute_mistura_override_e_medido(tmp_path):
    con = db.connect(tmp_path / "j.db")
    con.execute("INSERT INTO day (date, worked_override) VALUES ('2025-10-06', 480)")
    con.commit()
    dias = ledger.compute(con, ate=TER, hoje=TER)
    assert [(d.date, d.worked, d.delta, d.balance) for d in dias] == [
        (SEG, 480, 0, 0),
        (TER, 0, -480, -480),
    ]


def test_formatacao():
    assert ledger.format_signed(750) == "+12h30"
    assert ledger.format_signed(-65) == "-1h05"
    assert ledger.balance_line(750) == "Saldo: +12h30 (1,6 dia)"
