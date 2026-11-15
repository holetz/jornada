from dataclasses import fields

import pytest

from jornada import db, settings
from jornada.settings import Settings


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "j.db")
    yield c
    c.close()


def test_padroes_sem_regras_gravadas(con):
    assert settings.load(con) == Settings()
    assert settings.to_dict(Settings())["input.idleSeconds"] == 180


def test_salvar_carregar_e_restaurar(con):
    s = Settings(idle_seconds=120, ignore_apps=("Slack",), camera_enabled=True)
    settings.save(con, s)
    assert settings.load(con) == s
    settings.reset(con)
    assert settings.load(con) == Settings()


def test_fields_cobre_todos_os_atributos():
    assert {a for a, *_ in settings.FIELDS.values()} == {f.name for f in fields(Settings)}


def test_to_dict_usa_listas_e_todas_as_chaves():
    dados = settings.to_dict(Settings(ignore_apps=("a",)))
    assert list(dados) == list(settings.FIELDS)
    assert dados["input.ignoreApps"] == ["a"]


def test_validate_parcial_preserva_padroes():
    s = settings.validate({"input.idleSeconds": 120, "input.ignoreApps": [" zoom ", ""]})
    assert s.idle_seconds == 120
    assert s.ignore_apps == ("zoom",)
    assert s.min_streak_seconds == Settings().min_streak_seconds


@pytest.mark.parametrize(
    ("dados", "trecho"),
    [
        ({"input.nada": 1}, "regra desconhecida"),
        ({"input.idleSeconds": 10}, "entre 30 e 3600"),
        ({"input.idleSeconds": True}, "inteiro"),
        ({"input.idleSeconds": 120.5}, "inteiro"),
        ({"mic.enabled": 1}, "true ou false"),
        ({"input.ignoreApps": ["a", 2]}, "lista de textos"),
        ({"input.ignoreApps": "a"}, "lista de textos"),
        ([], "objeto"),
    ],
)
def test_validate_recusa(dados, trecho):
    with pytest.raises(ValueError, match=trecho):
        settings.validate(dados)


def test_load_com_json_corrompido_levanta(con):
    con.execute("INSERT INTO meta VALUES ('detection', '{quebrado')")
    con.commit()
    with pytest.raises(ValueError, match="ilegíveis"):
        settings.load(con)


def test_ignores():
    s = Settings(ignore_apps=("Spotify",))
    assert s.ignores("spotify") is True
    assert s.ignores("code") is False
    assert s.ignores(None) is False


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("input.idleSeconds=120", ("input.idleSeconds", 120)),
        ("camera.enabled=true", ("camera.enabled", True)),
        ('input.ignoreApps=["a", "b"]', ("input.ignoreApps", ["a", "b"])),
        ("input.ignoreApps=slack, zoom", ("input.ignoreApps", ["slack", "zoom"])),
        ("input.ignoreApps=", ("input.ignoreApps", [])),
        ("outra=texto livre", ("outra", "texto livre")),
    ],
)
def test_parse_assignment(texto, esperado):
    assert settings.parse_assignment(texto) == esperado


def test_parse_assignment_sem_igual_levanta():
    with pytest.raises(ValueError, match="chave=valor"):
        settings.parse_assignment("input.idleSeconds")


def test_apply_assignments_compoe_sobre_o_atual():
    atual = Settings(camera_enabled=True)
    novo = settings.apply_assignments(atual, [("input.idleSeconds", 120)])
    assert novo == Settings(camera_enabled=True, idle_seconds=120)
    with pytest.raises(ValueError):
        settings.apply_assignments(atual, [("mic.minSeconds", -1)])
