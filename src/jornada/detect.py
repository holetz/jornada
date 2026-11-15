"""Máquinas de estado dos detectores: decidem o que conta como atividade e gravam spans e eventos.

Puras quanto ao ambiente (sem `gi`, sem subprocess): recebem a leitura já feita pelo coletor, a
conexão e as regras do tick. `InputDetector` exige atividade contínua de teclado/mouse antes de
contar (esbarrões viram eventos `filter`) e para na ociosidade; `Sustained` exige que uma fonte
(microfone, câmera) fique ligada por um tempo mínimo.
"""

import sqlite3
from datetime import datetime

from jornada import events, metrics, spans
from jornada.settings import Settings

# o IdleMonitor responde em ms; abaixo disso a "última entrada" só oscilou com a latência
NOVA_ENTRADA_EPSILON = 0.5


def hora(ts: float) -> str:
    return datetime.fromtimestamp(ts, metrics.local_tz()).strftime("%H:%M:%S")


class InputDetector:
    """Teclado/mouse pelo tempo ocioso do Mutter (`idletime`, lido a cada tick)."""

    SOURCE = "input"

    def __init__(self) -> None:
        self.counting = False
        self.ignored = False
        self.streak_start: float | None = None
        self.last_input: float | None = None

    def _emit(self, con, now, kind, message, data=None) -> None:
        events.emit(con, now, self.SOURCE, kind, message, data)

    def step(
        self,
        con: sqlite3.Connection,
        now: float,
        idletime: float,
        s: Settings,
        app: str | None = None,
    ) -> dict:
        ultima = now - idletime
        anterior = self.last_input
        if anterior is None:
            nova = idletime <= s.streak_gap_seconds
        else:
            nova = ultima > anterior + NOVA_ENTRADA_EPSILON
        self.last_input = ultima
        if s.events_verbose:
            self._emit(con, now, "reading", f"ocioso há {idletime:.1f} s", {"idletime": idletime})

        if s.ignores(app):
            self._ignore(con, now, app)
        elif self.counting:
            self.ignored = False
            self._while_counting(con, now, idletime, ultima, s)
        else:
            self.ignored = False
            self._while_waiting(con, now, idletime, ultima, anterior, nova, s)
        return self.status(now, idletime)

    def _ignore(self, con, now, app) -> None:
        if self.counting:
            spans.cut(con, self.SOURCE, "active", now)
            self._emit(con, now, "filter", f"foco em {app} (app ignorado): a contagem parou")
        elif not self.ignored:
            self._emit(con, now, "filter", f"foco em {app} (app ignorado): teclado/mouse não conta")
        self.counting = False
        self.ignored = True
        self.streak_start = None
        spans.record(con, self.SOURCE, "ignored", now, {"app": app})

    def _while_counting(self, con, now, idletime, ultima, s: Settings) -> None:
        if idletime < s.idle_seconds:
            spans.record(con, self.SOURCE, "active", now)
            return
        spans.cut(con, self.SOURCE, "active", ultima)
        spans.record(con, self.SOURCE, "idle", now, start=ultima)
        self.counting = False
        self._emit(
            con,
            now,
            "state",
            f"ocioso: {idletime:.0f} s sem teclado/mouse (limite {s.idle_seconds} s); "
            f"contagem parou às {hora(ultima)}",
            {"idletime": idletime, "idleSeconds": s.idle_seconds, "stoppedAt": ultima},
        )

    def _while_waiting(self, con, now, idletime, ultima, anterior, nova, s: Settings) -> None:
        if nova and idletime < s.idle_seconds:
            quebrou = anterior is not None and ultima - anterior > s.streak_gap_seconds
            if self.streak_start is not None and quebrou:
                self._bump(con, now, anterior - self.streak_start, s)
            if self.streak_start is None:
                self.streak_start = ultima
            duracao = ultima - self.streak_start
            if duracao >= s.min_streak_seconds:
                self._confirm(con, now, duracao, s)
                return
        elif self.streak_start is not None and now - ultima > s.streak_gap_seconds:
            self._bump(con, now, ultima - self.streak_start, s)
        spans.record(con, self.SOURCE, "idle", now)

    def _bump(self, con, now, duracao, s: Settings) -> None:
        self._emit(
            con,
            now,
            "filter",
            f"esbarrão ignorado: {duracao:.0f} s de teclado/mouse "
            f"(mínimo contínuo {s.min_streak_seconds} s)",
            {"seconds": round(duracao, 1), "minStreakSeconds": s.min_streak_seconds},
        )
        self.streak_start = None

    def _confirm(self, con, now, duracao, s: Settings) -> None:
        inicio = self.streak_start
        spans.cut(con, self.SOURCE, "idle", inicio)
        spans.record(con, self.SOURCE, "active", now, start=inicio)
        self.counting = True
        self.streak_start = None
        self._emit(
            con,
            now,
            "state",
            f"atividade confirmada: teclado/mouse contínuo por {duracao:.0f} s "
            f"(mínimo {s.min_streak_seconds} s); contando desde {hora(inicio)}",
            {"seconds": round(duracao, 1), "since": inicio},
        )

    def status(self, now: float, idletime: float | None = None) -> dict:
        if self.ignored:
            estado = "ignorado"
        elif self.counting:
            estado = "contando"
        elif self.streak_start is not None:
            estado = "confirmando"
        else:
            estado = "ocioso"
        sequencia = (
            round(self.last_input - self.streak_start, 1)
            if self.streak_start is not None and self.last_input is not None
            else None
        )
        return {
            "state": estado,
            "counting": self.counting,
            "idletime": None if idletime is None else round(idletime, 1),
            "lastInput": self.last_input,
            "streakSeconds": sequencia,
        }


class Sustained:
    """Fonte ligada/desligada (microfone, câmera) que só conta depois de `min_seconds` ligada."""

    def __init__(self, source: str, rotulo: str) -> None:
        self.source = source
        self.rotulo = rotulo
        self.counting = False
        self.since: float | None = None
        self.on = False

    def _emit(self, con, now, kind, message, data=None) -> None:
        events.emit(con, now, self.source, kind, message, data)

    def step(
        self,
        con: sqlite3.Connection,
        now: float,
        on: bool,
        min_seconds: int,
        max_gap: float,
        verbose: bool = False,
    ) -> dict:
        self.on = on
        if verbose:
            self._emit(con, now, "reading", f"{self.rotulo}: {'em uso' if on else 'livre'}")
        if not on:
            self._release(con, now, min_seconds)
            spans.record(con, self.source, "inactive", now, max_gap=max_gap)
            return self.status()
        if self.since is None:
            self.since = now
        if self.counting:
            spans.record(con, self.source, "active", now, max_gap=max_gap)
        elif now - self.since >= min_seconds:
            spans.cut(con, self.source, "inactive", self.since)
            spans.record(con, self.source, "active", now, max_gap=max_gap, start=self.since)
            self.counting = True
            self._emit(
                con,
                now,
                "state",
                f"{self.rotulo} em uso desde {hora(self.since)}",
                {"since": self.since},
            )
        else:
            spans.record(con, self.source, "inactive", now, max_gap=max_gap)
        return self.status()

    def _release(self, con, now, min_seconds) -> None:
        if self.counting:
            minutos = (now - self.since) / 60
            self._emit(con, now, "state", f"{self.rotulo} livre após {minutos:.0f} min de uso")
        elif self.since is not None:
            self._emit(
                con,
                now,
                "filter",
                f"uso curto de {self.rotulo} ignorado: {now - self.since:.0f} s "
                f"(mínimo {min_seconds} s)",
                {"seconds": round(now - self.since, 1), "minSeconds": min_seconds},
            )
        self.counting = False
        self.since = None

    def disable(self, con: sqlite3.Connection, now: float) -> None:
        """A fonte foi desligada nas regras: encerra a contagem em curso, com evento."""
        if self.counting or self.since is not None:
            self._emit(con, now, "config", f"{self.rotulo} desligado nas regras")
        self.counting = False
        self.since = None
        self.on = False

    def status(self) -> dict:
        return {"on": self.on, "counting": self.counting, "since": self.since}
