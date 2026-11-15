"""Microfone em uso: nó Stream/Input/Audio `running` no pw-dump (fallback /proc/asound).

Portado do antigo work-tracking. O `pw-dump` é pesado: o componente chama este coletor a cada 15 s.
"""

import json
import logging
import sqlite3
import subprocess
from collections.abc import Callable
from pathlib import Path

from jornada import spans

log = logging.getLogger("jornada.mic")
SOURCE = "mic"
INTERVAL_SECONDS = 15.0
MAX_GAP = 3 * INTERVAL_SECONDS


def running_in_pw_dump(saida: str) -> bool:
    nos = json.loads(saida)
    return any(
        no.get("info", {}).get("props", {}).get("media.class") == "Stream/Input/Audio"
        and no.get("info", {}).get("state") == "running"
        for no in nos
    )


def running_in_proc(raiz: Path = Path("/proc/asound")) -> bool:
    for arq in raiz.glob("card*/pcm*c/sub*/status"):
        try:
            if "RUNNING" in arq.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


def run_pw_dump() -> str:
    r = subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=5, check=False)
    if r.returncode != 0:
        raise OSError(f"pw-dump saiu com {r.returncode}")
    return r.stdout


def is_active(pw_dump: Callable[[], str] = run_pw_dump, proc: Callable[[], bool] = running_in_proc):
    try:
        return running_in_pw_dump(pw_dump())
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        log.warning("pw-dump falhou (%s); usando /proc/asound", e)
        return proc()


def make(pw_dump: Callable[[], str] = run_pw_dump, proc: Callable[[], bool] = running_in_proc):
    def poll(con: sqlite3.Connection, now: float) -> None:
        ativo = is_active(pw_dump, proc)
        spans.record(con, SOURCE, "active" if ativo else "inactive", now, max_gap=MAX_GAP)

    return poll
