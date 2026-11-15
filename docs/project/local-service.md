---
type: project
title: Serviço local
description: Como instalar, atualizar, inspecionar e remover o jornada como serviço systemd de usuário, e onde ficam os dados
resource: scripts/deploy.sh, src/jornada/paths.py, src/jornada/settings.py, src/jornada/events.py
tags: [systemd, deploy, servico, logs]
generated: { by: process:quenching-align, at: 2026-11-14T00:00:00Z }
audience: both
authority: current
source: AGENTS.md (seção "Serviço local")
maintainer: holetz
---

# Serviço local

O jornada roda como a unidade systemd de usuário `jornada`, a partir de um venv próprio.

## Instalar, atualizar e remover

| Comando | O que faz |
| --- | --- |
| `bash scripts/deploy.sh` | instala ou atualiza (idempotente) o venv em `~/.local/share/jornada/venv` e a unidade `jornada` |
| `bash scripts/deploy.sh --uninstall` | para e remove a unidade e o venv; os dados ficam |

O venv é criado com `--system-site-packages`, porque o `gi` (PyGObject) vem do Python do
sistema (`scripts/deploy.sh:22-26` recusa a instalação quando ele falta); ver
[importação preguiçosa do gi](/docs/standards/code/optional-gi-import.md).

## Inspecionar

- Logs do processo: `journalctl --user -u jornada -n 50`.
- Estado (versão, caminhos, `user_version` do banco): `jornada status`.
- Eventos dos detectores (o que cada um leu e decidiu): `jornada events -n 100`, filtrável por
  `--source` e `--kind`, ou a página "Depuração e regras" do menu da bandeja (`/debug.html`), que
  mostra também o estado ao vivo. Eventos ficam na tabela `event` do banco, por
  `events.retentionDays` dias.

## Configurar a detecção

As regras de detecção (atividade contínua mínima, ociosidade, apps ignorados, microfone, câmera,
eventos detalhados) são desta máquina e ficam no banco, não no `config.toml`:
`jornada settings` mostra, `jornada settings --set chave=valor` altera e a página de depuração
edita. Valem no tick seguinte, sem reiniciar o serviço; a tabela completa está no README.

## Dados

Banco SQLite e capturas de tela ficam em `~/.local/share/jornada/` e nunca entram no git.
`JORNADA_HOME=<pasta>` redireciona dados, configuração e estado para uma só pasta
(`src/jornada/paths.py:15-16`), o que os testes e os ambientes sem `gi` usam.
