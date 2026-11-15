---
type: standard
title: Migrações numeradas do banco
description: O schema SQLite evolui por uma lista ordenada de migrações aplicadas por PRAGMA user_version, e uma migração já publicada nunca é editada
resource: src/jornada/db.py
tags: [sqlite, migracoes, schema, banco]
generated: { by: process:quenching-align, at: 2026-11-14T00:00:00Z }
audience: both
authority: current
source: AGENTS.md (seção "Serviço local")
maintainer: holetz
---

# Migrações numeradas do banco

O banco do jornada é um SQLite em WAL cujo schema evolui por migrações numeradas
(`src/jornada/db.py:1`).

## Como funciona

- `MIGRATIONS` (`src/jornada/db.py:41`) é uma lista ordenada de funções; a posição na lista,
  a partir de 1, é o número da migração.
- A versão aplicada fica em `PRAGMA user_version` (`src/jornada/db.py:50`).
- Na abertura, cada migração com número maior que a versão atual roda e grava o novo
  `user_version` (`src/jornada/db.py:55-60`).

## A regra

- **Nunca edite uma migração já publicada** (já mergeada na `master`). Bancos existentes já
  passaram por ela e não vão rodá-la de novo; a correção é uma migração nova no fim da lista.
- Nunca reordene nem remova itens de `MIGRATIONS`: o número é a posição.
- `jornada status` mostra o `user_version` do banco em uso.
