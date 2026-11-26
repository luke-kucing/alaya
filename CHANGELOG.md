# Changelog

All notable changes to `alaya-mcp`. Versions follow [semantic versioning](https://semver.org/); while
the major version is 0, a minor bump may break compatibility.

## Unreleased

### Fixed

- Chunking splits any paragraph over 2048 tokens (by line, then by width), so one huge paragraph
  no longer becomes a single chunk that takes 17 GB+ to embed. (#211)
- Search no longer drops results scoring under 0.2. Hybrid scores run low, so gold hits were cut
  before the limit or token budget applied. LongMemEval recall_all at 4000 tokens: 0.681 → 0.874. (#190)
- `rerank=True` maps cross-encoder logits to 0..1. Raw, mostly negative logits were being filtered
  out, which left about 45% of queries with no results. (#190)

## 0.3.0 — 2026-11-25

### Added

- `GET /memory/context?q=...&k=3` in `--http` mode returns the top-k vault chunks as JSON for
  pre-flight middleware. It requires `ALAYA_HTTP_TOKEN` when that is set. (#146)
- `get_memory_context(query, vault, k=3)` in `alaya.tools.memory` returns the top-k chunks as
  dicts (path, title, score, text). It is the single retrieval path behind `memory_recall`, for
  non-tool surfaces such as #146. (#145)
- Templates can use `{title_yaml}`, a YAML-quoted title, for frontmatter values such as
  `title: {title_yaml}`. `{title}` stays raw for headings and body text. (#192)

### Changed

- Requires `fastmcp>=4,<5` (was `<4`). No changes to alaya's tools or behaviour. (#186)

## 0.2.1 — 2026-11-25

### Fixed

- Indexes built before 0.2.0 are reindexed once, automatically, on first start, so `note_type`
  filtering works without a manual `reindex_vault`. (#189)
- `rename_note` re-indexes the renamed note, so search shows its new title. (#188)
- The one-time reindex marker is written only after the reindex finishes, so a server stopped
  mid-reindex resumes it on the next start. (#202)

## 0.2.0 — 2026-11-25

### Breaking

- **Tools are registered under bare names**: `search_notes`, `get_note`, ... instead of
  `search_notes_tool`, `get_note_tool`. Update any client allowlist or permission rule that
  names tools (for example `mcp__alaya__search_notes_tool` → `mcp__alaya__search_notes`).
  Profiles accept either spelling. (#150)
- **Destructive tools are two-phase server-side**: the first call to `delete_note`, `move_note`,
  `rename_note`, `replace_section`, `clear_inbox_item` or `reindex_vault` returns a preview and a
  token; repeat the call with `confirm_token` to execute. `ALAYA_CONFIRM_MODE=off` restores the
  old behaviour. (#166)

### Added

- **Agent memory**: `memory_recall` (budgeted retrieval that returns chunk text), `memory_checkpoint`,
  `memory_resume` (#164). Recall honours `ttl_days`, `confidence` and `since` (#169).
  `memory_supersede` marks old memory as replaced instead of overwriting it (#171).
  `memory_stale` plus a `gardener` profile for scheduled upkeep (#172).
- **Task ledger**: `create_task`, `ready_tasks`, `claim_task`, `renew_task`, `release_task`.
  Claims are leases with exactly one winner across processes. (#170)
- **Streamable HTTP transport**: `alaya --http HOST:PORT`, with optional bearer auth via
  `ALAYA_HTTP_TOKEN`, so one server can serve many clients. (#157)
- **Tool profiles**: `--profile` / `ALAYA_TOOL_PROFILE` registers only the tools a role needs.
  Built-ins include `readonly`, `orchestrator` and `gardener`, and custom profiles can be defined
  in `alaya.toml`. (#165)
- **Output budgets**: every response carries a `token_count` and is capped at
  `ALAYA_MAX_TOOL_OUTPUT_TOKENS` (default 4000); `get_note` pages long notes. (#167)
- `search_notes` results include a one-line snippet of the matching chunk. (#145)
- `alaya-mcp` console script, so `uvx alaya-mcp` (the README quickstart) works. `alaya` still works.
- LongMemEval retrieval eval harness: `make eval`. (#173)

### Fixed

- Edits, todo completion, inbox capture and wikilink rewrites update the search index immediately
  instead of waiting for the file watcher. (#149)
- Titles containing `:`, `#` or quotes are YAML-quoted in frontmatter and read back correctly. (#151)
- `append_to_note(section_header=...)` matches headers case-insensitively. (#152)
- Failed tool calls, including argument-validation errors, are written to the audit log. (#153)
- Indexing kept `note_type`, so agent memory is excluded from search as intended (#178).
  **Reindex existing vaults** (`reindex_vault` with `force=True`) to apply this to notes indexed
  before the fix (#189).
- `fastmcp` is capped below 4. An unbounded pin let fresh installs pull fastmcp 4. (#194)

### Security

- Locked dependencies upgraded: the lock carried 201 known vulnerabilities in 22 packages because
  the CI audit was scanning the wrong environment. (#194)
- GitHub Actions hardened: actions pinned to SHAs, least-privilege permissions, and publishing only
  from version tags through a reviewer-gated environment. CI audits the real lock and smoke-tests
  the built wheel. (#144)

## 0.1.0

First release on PyPI.
