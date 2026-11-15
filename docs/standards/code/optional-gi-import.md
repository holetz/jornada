---
type: standard
title: Importação preguiçosa do gi
description: O código que usa GTK, AppIndicator ou D-Bus importa o PyGObject (gi) só dentro da função que precisa dele, para que testes e CI rodem sem sessão gráfica e sem gi
resource: src/jornada/**, .github/workflows/ci.yml
tags: [python, gi, pygobject, gtk, ci, testes]
generated: { by: process:quenching-align, at: 2026-11-14T00:00:00Z }
audience: both
authority: current
source: AGENTS.md (seção "Operar o repo")
maintainer: holetz
---

# Importação preguiçosa do `gi`

O jornada usa o PyGObject do sistema (`gi`) para a bandeja (GTK 3 + AyatanaAppIndicator3), o
loop GLib e o D-Bus. O CI e o ambiente de testes não têm sessão gráfica nem `gi`
(`.github/workflows/ci.yml:14-17` roda `uv sync` e `uv run pytest` num runner sem GNOME).

## A regra

- **Nenhum `import gi` no nível do módulo.** O import fica dentro da função que precisa dele:
  `run()` em `src/jornada/app.py:44` (`from gi.repository import GLib`) e a montagem da bandeja
  em `src/jornada/tray.py:80-85`.
- **A lógica pura fica fora do GTK.** Funções como `label` e `icon_name`
  (`src/jornada/tray.py:3`) não dependem de `gi` e são testadas direto.
- O docstring do módulo diz onde o `gi` entra (`src/jornada/app.py:4`), para quem ler saber
  que o import tardio é proposital.

## Por quê

Um `import gi` no topo derruba a coleta do pytest no CI. Com o import preguiçoso, a suíte padrão
roda em qualquer máquina, e só os testes marcados `-m desktop` precisam da sessão GNOME real.

## Ambiente do serviço

O venv do serviço é criado com `--system-site-packages` para enxergar o `gi` do sistema; ver
[serviço local](/docs/project/local-service.md).
