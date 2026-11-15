import configparser
import subprocess
from pathlib import Path

RAIZ = Path(__file__).parent.parent


def test_sintaxe_do_script():
    subprocess.run(["bash", "-n", str(RAIZ / "scripts/deploy.sh")], check=True)


def test_unidade_systemd():
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str  # type: ignore[assignment]
    cp.read(RAIZ / "scripts/jornada.service")
    assert cp["Service"]["ExecStart"].endswith("/venv/bin/jornada run")
    assert cp["Service"]["Restart"] == "on-failure"
    assert cp["Install"]["WantedBy"] == "graphical-session.target"
    assert cp["Unit"]["After"] == "graphical-session.target"
    assert cp["Unit"]["PartOf"] == "graphical-session.target"
