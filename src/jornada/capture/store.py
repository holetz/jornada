"""Redução, gravação e retenção das capturas: `<raiz>/AAAA-MM-DD/HHMMSS.webp`.

Puro (sem `gi`): recebe os bytes do PNG e o relógio, e só toca o disco sob a raiz dada.
"""

import io
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from PIL import Image

DIR_MODE = 0o700
FILE_MODE = 0o600
WEBP_QUALITY = 50
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_FILE = re.compile(r"\d{6}\.webp")


def valid_day(texto: str) -> bool:
    return bool(_DAY.fullmatch(texto))


def valid_file(nome: str) -> bool:
    return bool(_FILE.fullmatch(nome))


def reduce(png: bytes, width: int, quality: int = WEBP_QUALITY) -> bytes:
    """WebP com `width` px de largura (proporção mantida); nunca amplia."""
    with Image.open(io.BytesIO(png)) as img:
        img = img.convert("RGB")
        if img.width > width:
            img = img.resize((width, max(1, round(img.height * width / img.width))))
        saida = io.BytesIO()
        img.save(saida, "WEBP", quality=quality)
    return saida.getvalue()


def ensure_dir(pasta: Path) -> None:
    pasta.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    pasta.chmod(DIR_MODE)


def save(raiz: Path, png: bytes, now: datetime, width: int) -> Path:
    """Grava a captura de `now` e devolve o caminho."""
    dia = raiz / now.strftime("%Y-%m-%d")
    ensure_dir(raiz)
    ensure_dir(dia)
    destino = dia / now.strftime("%H%M%S.webp")
    destino.write_bytes(reduce(png, width))
    destino.chmod(FILE_MODE)
    return destino


def list_day(raiz: Path, dia: str) -> list[str]:
    """Nomes dos arquivos do dia, em ordem de horário; vazio se o dia não existe."""
    pasta = raiz / dia
    if not valid_day(dia) or not pasta.is_dir():
        return []
    return sorted(p.name for p in pasta.iterdir() if valid_file(p.name))


def purge(raiz: Path, hoje: date, retention_days: int) -> list[str]:
    """Apaga os dias anteriores a `hoje - retention_days`; devolve os dias apagados."""
    if not raiz.is_dir():
        return []
    limite = hoje - timedelta(days=retention_days)
    apagados = []
    for pasta in sorted(raiz.iterdir()):
        if not (pasta.is_dir() and valid_day(pasta.name)):
            continue
        if date.fromisoformat(pasta.name) < limite:
            shutil.rmtree(pasta)
            apagados.append(pasta.name)
    return apagados
