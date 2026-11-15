import pytest

from jornada import db, events


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "j.db")
    yield c
    c.close()


def test_emitir_e_consultar_em_ordem_com_dados_decodificados(con):
    events.emit(con, 20, "input", "state", "ativo", {"z": 1, "ação": "início"})
    events.emit(con, 10, "lock", "reading", "leitura antiga")
    events.emit(con, 20, "lock", "control", "iniciado", {})
    assert events.query(con) == [
        {"id": 3, "ts": 20, "source": "lock", "kind": "control", "message": "iniciado", "data": {}},
        {
            "id": 1,
            "ts": 20,
            "source": "input",
            "kind": "state",
            "message": "ativo",
            "data": {"z": 1, "ação": "início"},
        },
        {
            "id": 2,
            "ts": 10,
            "source": "lock",
            "kind": "reading",
            "message": "leitura antiga",
            "data": None,
        },
    ]
    assert con.execute("SELECT data FROM event WHERE id = 1").fetchone()[0] == (
        '{"ação": "início", "z": 1}'
    )
    assert not con.in_transaction


@pytest.mark.parametrize("kind", events.KINDS)
def test_aceita_todos_os_tipos(con, kind):
    events.emit(con, 1, "input", kind, "evento")
    assert events.query(con)[0]["kind"] == kind


@pytest.mark.parametrize(
    ("filtros", "instantes"),
    [
        ({"source": "input"}, [40, 20, 10]),
        ({"kind": "state"}, [40, 30, 10]),
        ({"before": 30}, [20, 10]),
        ({"since": 20}, [40, 30]),
        ({"before": 0}, []),
        ({"since": 0}, [40, 30, 20, 10]),
        ({"source": "input", "kind": "state", "before": 40, "since": 0}, [10]),
    ],
)
def test_filtros_opcionais_e_combinados(con, filtros, instantes):
    for ts, source, kind in (
        (10, "input", "state"),
        (20, "input", "reading"),
        (30, "lock", "state"),
        (40, "input", "state"),
    ):
        events.emit(con, ts, source, kind, "evento")
    assert [evento["ts"] for evento in events.query(con, **filtros)] == instantes


@pytest.mark.parametrize(
    ("limite", "quantidade"), [(None, 200), (-1, 1), (0, 1), (2, 2), (5000, 5000), (6000, 5000)]
)
def test_limite_padrao_e_extremos(con, limite, quantidade):
    with con:
        con.executemany(
            "INSERT INTO event (ts, source, kind, message) VALUES (?, ?, ?, ?)",
            ((ts, "input", "state", "evento") for ts in range(5001)),
        )
    filtros = {} if limite is None else {"limit": limite}
    resultado = events.query(con, **filtros)
    assert len(resultado) == quantidade
    assert resultado[0]["ts"] == 5000


def test_tipo_invalido_nao_grava(con):
    with pytest.raises(ValueError, match="Tipo de evento inválido"):
        events.emit(con, 1, "input", "invalido", "evento")
    assert events.query(con) == []


def test_purge_apaga_so_antigos_e_retorna_contagem(con):
    agora = 10 * 86400
    corte = agora - 2 * 86400
    for ts in (corte - 2, corte - 1, corte, corte + 1, agora):
        events.emit(con, ts, "input", "state", "evento")
    assert events.purge(con, agora, 2) == 2
    assert [evento["ts"] for evento in events.query(con)] == [agora, corte + 1, corte]
    assert events.purge(con, agora, 2) == 0
    assert not con.in_transaction
