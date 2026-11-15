"""O loop do GLib, os sinais de término e o registro dos componentes.

Os componentes (bandeja, coletores, ...) seguem o protocolo `start()`/`stop()` e se
registram aqui, sem mexer no loop. `gi` só é importado dentro de `run()`.
"""

import logging
from collections.abc import Callable
from typing import Protocol

log = logging.getLogger("jornada")


class Component(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class App:
    def __init__(self) -> None:
        self._components: list[Component] = []
        self._started: list[Component] = []

    def register(self, componente: Component) -> None:
        self._components.append(componente)

    def start(self) -> None:
        for c in self._components:
            c.start()
            self._started.append(c)

    def stop(self) -> None:
        """Para na ordem inversa; o erro de um componente não impede os demais."""
        while self._started:
            c = self._started.pop()
            try:
                c.stop()
            except Exception:
                log.exception("falha ao parar %r", c)


def run(factories: list[Callable[["App"], Component]] | None = None) -> int:
    from gi.repository import GLib

    from jornada import capture, collectors, config, db, paths, tray
    from jornada.web.server import WebServer

    cfg = config.load()
    db.connect(cfg.db_path).close()

    loop = GLib.MainLoop()
    app = App()
    # o servidor lê o estado ao vivo do coletor, criado depois (a bandeja precisa da URL)
    web = WebServer(cfg.db_path, cfg.web_port, live=lambda: coletor.live)
    bandeja = tray.Tray(
        on_quit=loop.quit,
        start_paused=cfg.start_paused,
        db_path=cfg.db_path,
        web_url=lambda: web.url,
        capture_enabled=cfg.capture_enabled,
        debug_url=lambda: web.debug_url,
    )
    coletor = collectors.Collector(cfg.db_path, bandeja)
    app.register(bandeja)
    app.register(coletor)
    if not cfg.capture_enabled:
        app.register(capture.Retention(paths.captures_dir(), cfg.capture_retention_days))
    else:
        app.register(
            capture.Capture(
                paths.captures_dir(),
                cfg.db_path,
                bandeja,
                interval=cfg.capture_interval,
                width=cfg.capture_width,
                retention_days=cfg.capture_retention_days,
            )
        )
    app.register(web)
    for fabrica in factories or []:
        app.register(fabrica(app))

    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 15, loop.quit)  # SIGTERM
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 2, loop.quit)  # SIGINT

    app.start()
    log.info("jornada no ar")
    try:
        loop.run()
    finally:
        app.stop()
        log.info("jornada encerrado")
    return 0
