# `external/` — EXTERNAL reference material

**Factual material about what WE CONSUME** — tool docs, library docs, regulatory
standards. External to what we produce; background, **never** our contract. Each doc
carries `type: external`.

**Boundary** (the subtlest one): `external/` = "facts about what **WE CONSUME**
(external)" — distinct from [standards/](/docs/standards/index.md) ("how **WE** do it"). Example: the
documentation of the GNOME screenshot portal lives in [tools/](tools/index.md); **our
interface** to it (how we use it) lives in [standards/platform/](/docs/standards/platform/index.md).

## Subfolders

* [tools/](tools/index.md) — docs for tools we use
* [libraries/](libraries/index.md) — docs for libraries / dependencies

External binaries (PDFs) are consumed through a **sidecar** (`type: sidecar`) — the LLM
reads the extract, never the binary.
