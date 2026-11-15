"""Ponto de entrada do comando `jornada`: run, status, today, import, version."""

import argparse
import logging
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from jornada import __version__, config, db, ledger, metrics, paths, sheet
from jornada.tray import today_line

EXTENSAO_APPINDICATOR = "ubuntu-appindicators@ubuntu.com"


def extensao_appindicator_ligada() -> bool | None:
    """None quando não dá para saber (sem `gnome-extensions`)."""
    exe = shutil.which("gnome-extensions")
    if exe is None:
        return None
    r = subprocess.run([exe, "list", "--enabled"], capture_output=True, text=True, check=False)
    return EXTENSAO_APPINDICATOR in r.stdout.split()


def status_text() -> str:
    cfg = config.load()
    linhas = [
        f"jornada {__version__}",
        f"config: {paths.config_file()}",
        f"dados:  {paths.data_dir()}",
        f"banco:  {cfg.db_path}",
    ]
    if cfg.db_path.exists():
        con = db.connect(cfg.db_path)
        linhas.append(f"user_version: {db.user_version(con)}")
        con.close()
    else:
        linhas.append("user_version: (banco ainda não criado)")
    if extensao_appindicator_ligada() is False:
        linhas.append(
            f"AVISO: extensão {EXTENSAO_APPINDICATOR} desligada; o ícone não aparece "
            f"(gnome-extensions enable {EXTENSAO_APPINDICATOR})"
        )
    return "\n".join(linhas)


def today_text() -> str:
    cfg = config.load()
    if not cfg.db_path.exists():
        return "Hoje: — (banco ainda não criado)"
    con = db.connect(cfg.db_path)
    try:
        segundos, desde = metrics.today(con)
    finally:
        con.close()
    return today_line(metrics.format_hm(segundos), desde.strftime("%H:%M") if desde else None)


def ledger_text(ultimos: int = 7) -> str:
    cfg = config.load()
    if not cfg.db_path.exists():
        return "Saldo: — (banco ainda não criado)"
    con = db.connect(cfg.db_path)
    try:
        dias = ledger.compute(con)
    finally:
        con.close()
    if not dias:
        return "Saldo: — (nenhum dia lançado; use `jornada sheet import`)"
    linhas = [ledger.balance_line(dias[-1].balance), "", "data        real  prev  saldo do dia"]
    for d in dias[-ultimos:]:
        linhas.append(
            f"{d.date:%Y-%m-%d}  {metrics.format_hm(d.worked * 60):>5} "
            f"{metrics.format_hm(d.expected * 60):>5}  {ledger.format_signed(d.delta)}"
        )
    return "\n".join(linhas)


def sheet_text(args: argparse.Namespace) -> str:
    cfg = config.load()
    con = db.connect(cfg.db_path)
    try:
        if args.sheet_cmd == "import":
            return f"importados {sheet.import_sheet(con, args.arquivo)} dias de {args.arquivo}"
        n = sheet.export_sheet(con, args.arquivo, args.de, args.ate)
        return f"exportados {n} dias para {args.arquivo}"
    finally:
        con.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jornada")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="sobe o serviço (ícone na bandeja + loop do GLib)")
    sub.add_parser("status", help="mostra versão, caminhos e user_version do banco")
    sub.add_parser("today", help="mostra o tempo ativo de hoje")
    plan = sub.add_parser("sheet", help="importa ou exporta o banco de horas em .xlsx")
    plan_sub = plan.add_subparsers(dest="sheet_cmd", required=True)
    p_imp = plan_sub.add_parser("import", help="lê a planilha resumo.xlsx")
    p_imp.add_argument("arquivo", type=Path)
    p_exp = plan_sub.add_parser("export", help="escreve o banco de horas no layout da planilha")
    p_exp.add_argument("arquivo", type=Path)
    p_exp.add_argument("--de", type=date.fromisoformat, help="primeiro dia (AAAA-MM-DD)")
    p_exp.add_argument("--ate", type=date.fromisoformat, help="último dia (AAAA-MM-DD)")
    sub.add_parser("ledger", help="mostra o saldo do banco de horas e os últimos dias")
    sub.add_parser("version", help="mostra a versão")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "version":
        print(f"jornada {__version__}")
        return 0
    if args.cmd == "today":
        print(today_text())
        return 0
    if args.cmd == "ledger":
        print(ledger_text())
        return 0
    if args.cmd == "sheet":
        try:
            print(sheet_text(args))
        except (OSError, KeyError, ValueError) as e:
            print(f"erro: {e}", file=sys.stderr)
            return 1
        return 0
    if args.cmd == "status":
        print(status_text())
        return 0
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from jornada import app

    return app.run()


if __name__ == "__main__":
    sys.exit(main())
