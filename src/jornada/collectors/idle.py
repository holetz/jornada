"""Tempo ocioso de teclado/mouse pelo IdleMonitor do Mutter.

Este módulo só lê; a decisão do que conta (sequência contínua, ociosidade, apps ignorados) é de
`jornada.detect.InputDetector`.
"""

from collections.abc import Callable

SOURCE = "input"


def parse_idletime(saida: str) -> float | None:
    """`(uint64 1234,)` → 1.234 s; None se a saída não for reconhecida."""
    try:
        return int(saida.strip().strip("(),").split()[-1]) / 1000
    except (ValueError, IndexError):
        return None


def read(call: Callable[..., str]) -> float | None:
    """Segundos desde a última entrada; `call(dest, path, method)` devolve a saída do gdbus."""
    return parse_idletime(
        call(
            "org.gnome.Mutter.IdleMonitor",
            "/org/gnome/Mutter/IdleMonitor/Core",
            "org.gnome.Mutter.IdleMonitor.GetIdletime",
        )
    )
