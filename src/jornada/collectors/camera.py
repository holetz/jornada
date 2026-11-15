"""Câmera em uso: algum processo do usuário com `/dev/video*` aberto, ou um nó PipeWire
`Video/Source` em `running` (a câmera servida pelo PipeWire a um navegador ou app de reunião).

Só roda com `camera.enabled` nas regras; a duração mínima é de `jornada.detect.Sustained`.
"""

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

SOURCE = "camera"
INTERVAL_SECONDS = 15.0
MAX_GAP = 3 * INTERVAL_SECONDS
PROC = Path("/proc")


def holders(raiz: Path = PROC) -> list[str]:
    """Nomes (`comm`) dos processos legíveis com um `/dev/video*` aberto, sem repetição."""
    nomes: set[str] = set()
    try:
        pids = [p for p in os.scandir(raiz) if p.name.isdigit()]
    except OSError:
        return []
    for pid in pids:
        pasta = Path(pid.path)
        try:
            descritores = os.scandir(pasta / "fd")
        except OSError:
            continue
        with descritores:
            for fd in descritores:
                try:
                    alvo = str(Path(fd.path).readlink())
                except OSError:
                    continue
                if alvo.startswith("/dev/video"):
                    try:
                        nomes.add((pasta / "comm").read_text(encoding="utf-8").strip())
                    except OSError:
                        nomes.add(pid.name)
                    break
    return sorted(nomes)


def running_in_pw_dump(saida: str) -> bool:
    nos = json.loads(saida)
    return any(
        no.get("info", {}).get("props", {}).get("media.class") == "Video/Source"
        and no.get("info", {}).get("state") == "running"
        for no in nos
    )


def read(pw_dump: Callable[[], str] | None = None, raiz: Path = PROC) -> tuple[bool, list[str]]:
    """(em uso, quem segura o dispositivo); o pw-dump que falha só deixa de somar."""
    quem = holders(raiz)
    if quem:
        return True, quem
    if pw_dump is not None:
        try:
            if running_in_pw_dump(pw_dump()):
                return True, ["pipewire"]
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return False, []
