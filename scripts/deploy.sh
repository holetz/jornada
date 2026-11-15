#!/usr/bin/env bash
# Instala/atualiza o jornada como serviço systemd de usuário. Idempotente.
#   bash scripts/deploy.sh              instala ou atualiza
#   bash scripts/deploy.sh --uninstall  para e remove unidade e venv (preserva os dados)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/jornada"
VENV="$DATA/venv"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/jornada.service"

if [[ "${1:-}" == "--uninstall" ]]; then
  systemctl --user disable --now jornada.service 2>/dev/null || true
  rm -f "$UNIT"
  systemctl --user daemon-reload
  rm -rf "$VENV"
  echo "jornada removido (dados em $DATA preservados)"
  exit 0
fi

if ! /usr/bin/python3 -c 'import gi; gi.require_version("AyatanaAppIndicator3", "0.1")' 2>/dev/null; then
  echo "erro: faltam gi/AyatanaAppIndicator3 no Python do sistema." >&2
  echo "      sudo apt install python3-gi gir1.2-ayatanaappindicator3-0.1 gir1.2-gtk-3.0" >&2
  exit 1
fi

mkdir -p "$DATA" "$UNIT_DIR"
# --without-pip: não exige o pacote python3-venv/ensurepip; o pip do Python do sistema
# instala dentro do venv por --python.
# Um venv sem --system-site-packages (ou interrompido) não enxerga o gi: recria.
if [[ -e "$VENV" ]] && ! grep -qs '^include-system-site-packages = true' "$VENV/pyvenv.cfg"; then
  rm -rf "$VENV"
fi
[[ -x "$VENV/bin/python" ]] || /usr/bin/python3 -m venv --system-site-packages --without-pip "$VENV"
if ! /usr/bin/python3 -m pip --version >/dev/null 2>&1; then
  echo "erro: pip ausente no Python do sistema (sudo apt install python3-pip)." >&2
  exit 1
fi
/usr/bin/python3 -m pip --python "$VENV/bin/python" install --quiet --upgrade "$REPO"

install -m 0644 "$REPO/scripts/jornada.service" "$UNIT"
systemctl --user daemon-reload
systemctl --user enable --now jornada.service
systemctl --user restart jornada.service

echo "jornada instalado: $(systemctl --user is-active jornada.service)"
echo "logs: journalctl --user -u jornada -n 50"
