"""Captura de tela pelo xdg-desktop-portal (`Screenshot`, não interativo).

Funciona sem diálogo só quando o processo é "host" para o portal, como a unidade systemd
de usuário do jornada; a partir de um terminal o GNOME exige confirmação e recusa
(`Refused`). O portal grava um PNG em `~/Screenshot.png`; `grab` lê os bytes e apaga o arquivo.
"""

import logging
import time
import urllib.parse
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("jornada.capture")

TIMEOUT_SECONDS = 15.0
RESPONSE_OK = 0

Request = Callable[[], tuple[int, str | None]]


class Refused(Exception):
    """O portal recusou ou não devolveu a imagem (permissão ausente, diálogo exigido)."""


def uri_to_path(uri: str) -> Path:
    return Path(urllib.parse.unquote(urllib.parse.urlparse(uri).path))


def portal_request() -> tuple[int, str | None]:
    """Uma chamada `Screenshot(interactive=false)`; devolve `(código, uri)`. Importa `gi` aqui."""
    from gi.repository import Gio, GLib

    dest = "org.freedesktop.portal.Desktop"
    path = "/org/freedesktop/portal/desktop"
    con = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    token = f"jornada{int(time.time() * 1000)}"
    sender = con.get_unique_name().lstrip(":").replace(".", "_")
    loop = GLib.MainLoop()
    resposta: dict = {}

    def on_response(_con, _sender, _path, _iface, _signal, params, *_args):
        resposta["code"], resposta["results"] = params.unpack()
        loop.quit()

    sub = con.signal_subscribe(
        dest,
        "org.freedesktop.portal.Request",
        "Response",
        f"{path}/request/{sender}/{token}",
        None,
        Gio.DBusSignalFlags.NONE,
        on_response,
    )
    try:
        opcoes = {
            "interactive": GLib.Variant("b", False),
            "handle_token": GLib.Variant("s", token),
        }
        con.call_sync(
            dest,
            path,
            "org.freedesktop.portal.Screenshot",
            "Screenshot",
            GLib.Variant("(sa{sv})", ("", opcoes)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        GLib.timeout_add(int(TIMEOUT_SECONDS * 1000), loop.quit)
        loop.run()
    finally:
        con.signal_unsubscribe(sub)
    return resposta.get("code", -1), resposta.get("results", {}).get("uri")


def grab(request: Request = portal_request) -> bytes:
    """Bytes do PNG capturado; o arquivo temporário do portal é apagado em qualquer desfecho."""
    try:
        code, uri = request()
    except Exception as e:
        raise Refused(f"chamada ao portal falhou: {e}") from e
    if code != RESPONSE_OK or not uri:
        raise Refused(f"portal respondeu código {code}")
    arquivo = uri_to_path(uri)
    try:
        return arquivo.read_bytes()
    except OSError as e:
        raise Refused(f"imagem ilegível: {e}") from e
    finally:
        arquivo.unlink(missing_ok=True)
