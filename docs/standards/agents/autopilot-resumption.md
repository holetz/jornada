---
type: standard
title: Retomada do orquestrador no autopilot
description: No autopilot, um orquestrador que volta com needs-human é retomado por SendMessage, não relançado, e toda decisão de dono delegado vai antes para a seção Design do épico
resource: .agents/skills/quenching-specs/**
tags: [agents, autopilot, orquestrador, cache, specs]
generated: { by: process:quenching-align, at: 2026-11-14T00:00:00Z }
audience: agent
authority: background
source: project memory (feedback de 2026-11-03)
maintainer: holetz
---

# Retomada do orquestrador no autopilot

## A regra

- Quando o orquestrador do autopilot volta com `needs-human` e a decisão é rápida, **retome o
  mesmo agente** com SendMessage em vez de lançar um novo.
- Relançar a frio só quando o motivo for `budget:`.
- Toda decisão de dono delegado vai para o `## Design` do épico
  (`cq specs section --write`) **antes** de retomar.

## Por quê

Em 2026-11-03 o dono pediu para evitar a perda de cache de tokens: a spec 5 do jornada gastou 3
orquestradores, 5 runners e 4 verifiers em relançamentos evitáveis.

## Onde se aplica

Em toda execução do fluxo `autopilot` da skill `quenching-specs`. A melhoria correspondente no
próprio quenching está registrada na spec 2163 daquele repositório; enquanto ela não chega, a regra
fica aqui como `authority: background`.
