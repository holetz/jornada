---
type: project
title: Serviço local
description: Como instalar, atualizar, inspecionar e remover o jornada como serviço systemd de usuário, e onde ficam os dados
resource: scripts/deploy.sh, src/jornada/paths.py
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

- Logs: `journalctl --user -u jornada -n 50`.
- Estado (versão, caminhos, `user_version` do banco): `jornada status`.

## Dados

Banco SQLite e capturas de tela ficam em `~/.local/share/jornada/` e nunca entram no git.
`JORNADA_HOME=<pasta>` redireciona dados, configuração e estado para uma só pasta
(`src/jornada/paths.py:15-16`), o que os testes e os ambientes sem `gi` usam.
