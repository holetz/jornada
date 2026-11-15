"""Ícone AppIndicator na barra do GNOME, com rótulo e menu.

A lógica pura (`label`, `icon_name`) não depende de `gi`; o GTK/AppIndicator entra só em
`Tray.start()`.
"""

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

from jornada import db, ledger

BALANCE_SECONDS = 30
ICON_DIR = Path(__file__).parent / "icons"
log = logging.getLogger("jornada.tray")


def label(paused: bool, today: str | None = None) -> str:
    """Texto ao lado do ícone."""
    if paused:
        return "pausado"
    return today or "—"


def today_line(today: str | None, since: str | None = None) -> str:
    """Primeira linha do menu: `Hoje: 5h12 · ativo desde 08:03`."""
    linha = f"Hoje: {today or '—'}"
    return f"{linha} · ativo desde {since}" if since else linha


def balance_text(db_path: Path) -> str:
    """Segunda linha do menu: `Saldo: +12h30 (1,6 dia)`; `Saldo: —` sem dias lançados."""
    if not db_path.exists():
        return "Saldo: —"
    con = db.connect(db_path)
    try:
        dias = ledger.compute(con)
    finally:
        con.close()
    return ledger.balance_line(dias[-1].balance) if dias else "Saldo: —"


def open_url(url: str) -> None:
    subprocess.Popen(["xdg-open", url], start_new_session=True)


def icon_name(paused: bool, active: bool = False) -> str:
    if paused:
        return "jornada-pausado"
    return "jornada-ativo" if active else "jornada-ocioso"


class Tray:
    def __init__(
        self,
        on_quit: Callable[[], None],
        start_paused: bool = False,
        db_path: Path | None = None,
        web_url: Callable[[], str] | None = None,
        capture_enabled: bool = False,
    ) -> None:
        self._on_quit = on_quit
        self._db_path = db_path
        self._web_url = web_url
        self._capture_enabled = capture_enabled
        self.capture_paused = False
        self.capture_status: str | None = None
        self._capture_item = None
        self._balance_item = None
        self._balance_source: int | None = None
        self.paused = start_paused
        self.today: str | None = None
        self.since: str | None = None
        self.active = False
        self._indicator = None
        self._today_item = None

    def start(self) -> None:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppIndicator
        from gi.repository import Gtk

        ind = AppIndicator.Indicator.new_with_path(
            "jornada",
            icon_name(self.paused),
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
            str(ICON_DIR),
        )
        ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)

        menu = Gtk.Menu()
        self._today_item = Gtk.MenuItem(label="Hoje: —")
        self._today_item.set_sensitive(False)
        menu.append(self._today_item)

        pausar = Gtk.CheckMenuItem(label="Pausar rastreio")
        pausar.set_active(self.paused)
        pausar.connect("toggled", lambda item: self.set_paused(item.get_active()))
        menu.append(pausar)

        if self._capture_enabled:
            capturas = Gtk.CheckMenuItem(label="Pausar capturas")
            capturas.connect("toggled", lambda item: self.set_capture_paused(item.get_active()))
            menu.append(capturas)
            self._capture_item = Gtk.MenuItem(label="")
            self._capture_item.set_sensitive(False)
            menu.append(self._capture_item)

        self._balance_item = Gtk.MenuItem(label="Saldo: —")
        self._balance_item.set_sensitive(False)
        menu.append(self._balance_item)

        banco = Gtk.MenuItem(label="Abrir banco de horas")
        banco.set_sensitive(self._web_url is not None)
        if self._web_url is not None:
            banco.connect("activate", lambda _item: open_url(self._web_url()))
        menu.append(banco)

        menu.append(Gtk.SeparatorMenuItem())
        sair = Gtk.MenuItem(label="Sair")
        sair.connect("activate", lambda _item: self._on_quit())
        menu.append(sair)
        menu.show_all()
        if self._capture_item is not None:
            self._capture_item.set_visible(False)

        ind.set_menu(menu)
        self._indicator = ind
        self._refresh()
        if self._db_path is not None:
            from gi.repository import GLib

            self.refresh_balance()
            self._balance_source = GLib.timeout_add_seconds(BALANCE_SECONDS, self._on_balance_timer)

    def _on_balance_timer(self) -> bool:
        self.refresh_balance()
        return True

    def refresh_balance(self) -> None:
        if self._db_path is None or self._balance_item is None:
            return
        try:
            self._balance_item.set_label(balance_text(self._db_path))
        except Exception:
            log.exception("saldo do banco de horas falhou")

    def stop(self) -> None:
        if self._balance_source is not None:
            from gi.repository import GLib

            GLib.source_remove(self._balance_source)
            self._balance_source = None
        if self._indicator is not None:
            from gi.repository import AyatanaAppIndicator3 as AppIndicator

            self._indicator.set_status(AppIndicator.IndicatorStatus.PASSIVE)

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        log.info("rastreio %s", "pausado" if paused else "retomado")
        self._refresh()

    def set_capture_paused(self, paused: bool) -> None:
        self.capture_paused = paused
        log.info("capturas %s", "pausadas" if paused else "retomadas")

    def set_capture_status(self, texto: str | None) -> None:
        """Linha do menu sob "Pausar capturas" (ex.: `Capturas: sem permissão`); None a esconde."""
        self.capture_status = texto
        if self._capture_item is not None:
            self._capture_item.set_label(texto or "")
            self._capture_item.set_visible(bool(texto))

    def set_today(self, texto: str, desde: str | None = None) -> None:
        self.today = texto
        self.since = desde
        self._refresh()

    def _refresh(self) -> None:
        if self._indicator is None:
            return
        self._indicator.set_icon_full(icon_name(self.paused, self.active), "jornada")
        self._indicator.set_label(label(self.paused, self.today), "")
        if self._today_item is not None:
            self._today_item.set_label(today_line(self.today, self.since))
