# AGENTS.md

Language: pt-BR — the contract is /docs/standards/agents/communication.md

This repository uses quenching. The editable automation surface is `.agents/`; the
Claude Code bridge under `.claude/skills/` is generated from it.

- Configuration: [`.agents/quenching.json`](.agents/quenching.json).
- Durable knowledge: [`docs/index.md`](docs/index.md).
- Skills: `.agents/skills/` (source) and `.claude/skills/` (generated bridge).
- Deployed runtime: `.agents/quenching/` (generated; do not edit).
- Upgrade with `cq deploy --write` from a new quenching release; never edit a generated file.

## Operating this repo

Código, docs e mensagens de commit em pt-BR (`specs.artifactLanguage`); Python 3.12.

```bash
uv sync                       # ambiente de desenvolvimento
uv run ruff check && uv run ruff format --check
uv run pytest                 # o mesmo gate do CI (.github/workflows/ci.yml)
uv run pytest -m desktop      # testes que precisam da sessão GNOME real; nunca no CI
```

- `JORNADA_HOME=<pasta>` redireciona dados, config e estado (testes e ambiente sem `gi`).
- Dados do rastreio (banco SQLite, capturas de tela) moram em `~/.local/share/jornada/` e nunca
  entram no git.
- Trabalho nunca na `master`: worktree própria, PR, CI verde.

## Where knowledge lives

Knowledge is **NOT** in this file — it lives in the OKF bundle at [/docs/](docs/index.md).

**Resolving a term.** Palavra, sigla ou codinome desconhecido? Procure primeiro no glossário →
[/docs/glossary.md](docs/glossary.md): `grep -i '<termo>' docs/glossary.md`.

- [/docs/standards/](docs/standards/index.md) — how WE build (current contracts): import
  preguiçoso do `gi`, migrações numeradas do banco, conduta dos agentes.
- [/docs/project/](docs/project/index.md) — o manual deste repositório, incluindo o
  [serviço local](docs/project/local-service.md) (deploy, logs, status).
- [/docs/concepts/](docs/concepts/index.md) — generic understanding we hold; its
  [glossary.md](docs/glossary.md) is the term lookup.
- [/docs/external/](docs/external/index.md) — facts about what we consume (tools, libraries).
- [/docs/decisions/](docs/decisions/index.md) — the history behind a contract.
- [/docs/vision/](docs/vision/index.md) — direction, no deadline.
- [/docs/tutorials/](docs/tutorials/index.md), [/docs/how-to/](docs/how-to/index.md),
  [/docs/documentation/](docs/documentation/index.md) — reader-facing pages.

<!-- HOW TO FIND A TERM: the glossary is the repo's A–Z vocabulary index at
     /docs/glossary.md — a flat, alphabetically sorted bullet list, linked when a concept doc
     exists. A missing term is added with `/quenching-knowledge define`, many at once with
     `/quenching-knowledge glossary-backfill`, or captured with `/quenching-knowledge learn`. -->

To **create / edit / move** knowledge (keeping the listing in sync), use the `quenching`
skills: `/quenching-knowledge add`, `/quenching-knowledge define`, `/quenching-knowledge align`,
and `/quenching-components harness-align` to keep this file thin.

## Agent etiquette

- **Every development request goes through a spec**, and the spec runs the flow as far as the
  request authorizes. A request that names a change — "implement X improvement", "fix Y" — is a
  request to build it: develop, execute, conclude, open the PR, without stopping to ask whether to.
  Only a request that names the artifact — "create a spec for X" — stops at the spec. **Merge and
  deploy are not implied by a change request**: they run only when the human declares autonomy in
  the request itself ("do it autonomously", "PR and merge", "all the way to deploy"). Without that
  word the run ends at the open PR, named for the human to decide. The approval a spec carries
  covers every step inside that scope — no later step asks the human again.
- **A new skill joins its family's router** (`.agents/skills/<family>/SKILL.md`) when the family has
  three or more model-invocable skills — never a loose entry, and never an edit to an agent that
  came from the plugin (`.claude/agents/quenching-*.md`).
- Antes de mudar o schema do banco, leia
  [database-migrations.md](docs/standards/code/database-migrations.md).

<!-- Root harness pointer, auto-loaded by every supported harness on every turn. Keep it a thin pointer:
     repo-wide operations + the /docs/ home map. Knowledge is MOVED into /docs/, never copied here.
     Installed/maintained by the quenching plugin; this file is a harness pointer, not an
     OKF concept. -->
