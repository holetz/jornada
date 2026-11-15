"""Experimento da tarefa 8/1.1: o portal Screenshot (não interativo) serve para capturar?

Mede, nesta máquina, a latência e o resultado de `Screenshot(interactive=false)`. Diálogo, som
e flash são observados à mão. Uso: `/usr/bin/python3 scripts/experimento_captura.py [n]`.
"""

import sys
import time
import urllib.parse
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

DEST = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"


def capturar(con: Gio.DBusConnection, timeout: float = 15.0) -> tuple[int, str | None, float]:
    token = f"jornada{int(time.time() * 1000)}"
    sender = con.get_unique_name().lstrip(":").replace(".", "_")
    request = f"{PATH}/request/{sender}/{token}"
    loop = GLib.MainLoop()
    out: dict = {}

    def on_response(_c, _s, _p, _i, _sig, params, *_a):
        out["code"], out["results"] = params.unpack()
        loop.quit()

    sub = con.signal_subscribe(
        DEST, "org.freedesktop.portal.Request", "Response", request, None, 0, on_response
    )
    inicio = time.monotonic()
    con.call_sync(
        DEST,
        PATH,
        "org.freedesktop.portal.Screenshot",
        "Screenshot",
        GLib.Variant(
            "(sa{sv})",
            (
                "",
                {"interactive": GLib.Variant("b", False), "handle_token": GLib.Variant("s", token)},
            ),
        ),
        None,
        0,
        -1,
        None,
    )
    GLib.timeout_add(int(timeout * 1000), loop.quit)
    loop.run()
    con.signal_unsubscribe(sub)
    uri = out.get("results", {}).get("uri")
    return out.get("code", -1), uri, time.monotonic() - inicio


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    con = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    for i in range(n):
        code, uri, dt = capturar(con)
        print(f"{i + 1}: code={code} uri={uri} {dt:.2f}s")
        if uri:
            caminho = Path(urllib.parse.unquote(urllib.parse.urlparse(uri).path))
            print("   ", caminho.stat().st_size, "bytes")
            caminho.unlink()
        time.sleep(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
