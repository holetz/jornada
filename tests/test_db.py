import sqlite3

from jornada import db


def test_cria_e_migra(tmp_path):
    con = db.connect(tmp_path / "sub" / "j.db")
    assert db.user_version(con) == len(db.MIGRATIONS)
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    con.execute("INSERT INTO meta VALUES ('k','v')")


def test_migrar_de_novo_e_idempotente(tmp_path):
    caminho = tmp_path / "j.db"
    db.connect(caminho).close()
    con = db.connect(caminho)
    assert db.user_version(con) == len(db.MIGRATIONS)


def test_so_aplica_as_pendentes(tmp_path, monkeypatch):
    con = sqlite3.connect(tmp_path / "j.db")
    chamadas = []
    monkeypatch.setattr(
        db, "MIGRATIONS", [lambda c: chamadas.append(1), lambda c: chamadas.append(2)]
    )
    con.execute("PRAGMA user_version = 1")
    assert db.migrate(con) == 2
    assert chamadas == [2]


def test_migracao_3_preserva_spans_da_versao_2_como_jornada(tmp_path):
    con = sqlite3.connect(tmp_path / "j.db")
    for passo in db.MIGRATIONS[:2]:
        passo(con)
    con.execute("PRAGMA user_version = 2")
    con.execute("INSERT INTO span (source, state, start, end) VALUES ('input', 'active', 1, 2)")
    con.commit()
    assert db.migrate(con) == len(db.MIGRATIONS)
    assert con.execute("SELECT origin FROM span").fetchall() == [("jornada",)]
    indices = {r[1] for r in con.execute("PRAGMA index_list(span)")}
    assert "span_origin_start" in indices


def test_migracao_4_cria_banco_de_horas_com_a_jornada_inicial(tmp_path):
    con = db.connect(tmp_path / "j.db")
    assert db.user_version(con) >= 4
    assert con.execute("SELECT start_date, minutes FROM schedule").fetchall() == [
        ("2025-09-22", "[480, 480, 480, 480, 480, 0, 0]")
    ]
    con.execute("INSERT INTO day (date, worked_override, kind) VALUES ('2025-10-01', 60, 'ajuste')")
    colunas = [r[1] for r in con.execute("PRAGMA table_info(day)")]
    assert colunas == ["date", "worked_override", "expected_override", "kind", "note"]


def test_migracao_5_cria_tabela_de_eventos(tmp_path):
    con = db.connect(tmp_path / "j.db")
    assert db.user_version(con) >= 5
    colunas = con.execute("PRAGMA table_info(event)").fetchall()
    assert [(r[1], r[2], r[3], r[5]) for r in colunas] == [
        ("id", "INTEGER", 0, 1),
        ("ts", "REAL", 1, 0),
        ("source", "TEXT", 1, 0),
        ("kind", "TEXT", 1, 0),
        ("message", "TEXT", 1, 0),
        ("data", "TEXT", 0, 0),
    ]
    indices = {r[1] for r in con.execute("PRAGMA index_list(event)")}
    assert "event_ts" in indices
    assert [r[2] for r in con.execute("PRAGMA index_info(event_ts)")] == ["ts"]
    con.close()
