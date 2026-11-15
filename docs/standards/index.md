# `standards/` — current/active reference, OUR contracts

The current/active **standard/contract** — "how it should be and why", versioned, the
shared source of truth. One standard per file; subfolder names by **subject**. Each
concept doc carries `type: standard` + a derived `resource:` (the repo scope it governs).

**Boundary:** `standards/` = "how **WE** do it (current/active)". Distinct from
[external/](/docs/external/index.md) (external facts we consume). Direction lives in
[vision/](/docs/vision/index.md). An **agreed-but-unproven** rule sits here as
`authority: background` and graduates to `current` once proven — there is no separate decisions
home.

Keep only the subtopics that apply to the repo; within each, break standards **one
concept per file** by considering the candidate sub-standards catalog (a
**consideration** checklist, evidence-gated generation, recorded deferral — not a blind
generate list). The **agent-facing pointer** for this home is [AGENTS.md](AGENTS.md)
(auto-loaded).

## Subtopics

* [agents/](agents/index.md) — how we instruct agents: the language our prose is written in, and the conduct expected of the agent writing it
* [architecture/](architecture/index.md) — system structure + architectural patterns (patterns live here)
* [code/](code/index.md) — code conventions, imports, lint, pins, SYMBOL naming
* [ci-cd/](ci-cd/index.md) — build/deploy, "code defines YAML", manifest generation
* [platform/](platform/index.md) — deploy targets, permissions/governance, external services

## Current docs

<!-- BEGIN GENERATED: rebuilt from disk by `quenching-knowledge-align`/`quenching-knowledge-add` — DO NOT edit by hand.
     Scans standards/**/*.md, reads title/description/generated.at (or legacy timestamp)/type, grouped by subject subfolder.
     Row model per subfolder:
       ### code/
       | Doc | Covers |
       | --- | --- |
       | [imports.md](code/imports.md) | <the doc's description:> |
-->
### agents/

| Doc | Covers |
| --- | --- |
| [communication.md](agents/communication.md) | The two languages a repo declares for what its agents write — the conversation tag on the root harness line, and an artifact language declared by a standard or the artifactLanguage config key — and the conduct contract that holds whether or not either is declared |
| [ephemeral-writes.md](agents/ephemeral-writes.md) | Where an agent puts a file it creates — the three destinations, the one question that sorts them, and the session-start declaration that makes the durable-ignored path present before the first write |
| [autopilot-resumption.md](agents/autopilot-resumption.md) | No autopilot, um orquestrador que volta com needs-human é retomado por SendMessage, não relançado, e toda decisão de dono delegado vai antes para a seção Design do épico |

### ci-cd/

| Doc | Covers |
| --- | --- |

_(other subjects fill in as standards are created — these tables are regenerated deterministically from the real files)_

### code/

| Doc | Covers |
| --- | --- |
| [database-migrations.md](code/database-migrations.md) | O schema SQLite evolui por uma lista ordenada de migrações aplicadas por PRAGMA user_version, e uma migração já publicada nunca é editada |
| [optional-gi-import.md](code/optional-gi-import.md) | O código que usa GTK, AppIndicator ou D-Bus importa o PyGObject (gi) só dentro da função que precisa dele, para que testes e CI rodem sem sessão gráfica e sem gi |
<!-- END GENERATED -->
