from pathlib import Path

from jornada import config, paths


def test_defaults_sem_arquivo(tmp_path, monkeypatch):
    monkeypatch.setenv("JORNADA_HOME", str(tmp_path))
    monkeypatch.delenv("JORNADA_CONFIG", raising=False)
    cfg = config.load()
    assert cfg.db_path == tmp_path / "data" / "jornada.db"
    assert cfg.start_paused is False


def test_home_redireciona_diretorios(tmp_path, monkeypatch):
    monkeypatch.setenv("JORNADA_HOME", str(tmp_path))
    assert paths.data_dir() == tmp_path / "data"
    assert paths.config_dir() == tmp_path / "config"
    assert paths.state_dir() == tmp_path / "state"


def test_xdg_sem_home(tmp_path, monkeypatch):
    monkeypatch.delenv("JORNADA_HOME", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert paths.data_dir() == tmp_path / "jornada"


def test_arquivo_toml_sobrescreve(tmp_path, monkeypatch):
    arq = tmp_path / "c.toml"
    arq.write_text('db_path = "/dados/x.db"\nstart_paused = true\n')
    monkeypatch.setenv("JORNADA_CONFIG", str(arq))
    cfg = config.load()
    assert cfg.db_path == Path("/dados/x.db")
    assert cfg.start_paused is True
