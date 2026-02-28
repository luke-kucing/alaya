# zk-mcp Product Requirements Document

**Version:** 1.1
**Date:** 2026-02-27
**Status:** Draft

---

## Table of Contents

1. [PRD Overview](#1-prd-overview)
2. [Architecture Overview](#2-architecture-overview)
3. [Milestone Breakdown](#3-milestone-breakdown)
4. [TDD Strategy](#4-tdd-strategy)
5. [Risk Register](#5-risk-register)
6. [Open Questions](#6-open-questions)
7. [Resolved Decisions Log](#7-resolved-decisions-log)

---

## 1. PRD Overview

### Product Vision

`zk-mcp` makes Claude Code the primary interface for a `zk`-managed personal knowledge vault. Instead of switching between a terminal, a text editor, and a note browser, the user stays inside a single Claude session and converses — creating, searching, linking, synthesizing, and maintaining notes without ever touching a file directly. The server is a thin, composable wrapper over tools that already work (`zk`, `glab`, LanceDB, watchdog), not a reimplementation of any of them. The result is a second brain that is fully AI-addressable while remaining a plain-text, portable Markdown vault.

---

### Problem Statement

Personal knowledge management tools either lock knowledge into proprietary formats (Notion, Roam) or require constant manual attention to stay organized (raw Markdown in a folder). `zk` solves the storage and graph problem elegantly, but it is a CLI tool — it has no natural language interface. The user must know what they are looking for, how to phrase `zk` queries, and when to run maintenance operations.

The gap being filled: a user with 500 notes and a weekly review habit should be able to say "what did I know about zero trust networking when I talked to Sarah last month?" and get a synthesized, sourced answer — without leaving the terminal window they are already working in.

Today, answering that question requires: `zk list`, `grep`, `zk list --linked-by`, reading several files, and mentally synthesizing the result. With `zk-mcp`, it is a single natural language question.

---

### Success Criteria

v1 is done and working when all of the following are true:

| Criteria | Verification Method |
|---|---|
| Claude can read, create, append to, and search notes without errors | Milestone 1 integration tests pass against a real temp vault |
| Inbox capture round-trips correctly: capture, read, clear | `capture_to_inbox` -> `get_inbox` -> `clear_inbox_item` test passes |
| Move and rename keep wikilinks consistent across the vault | Wikilink consistency test suite passes (see M2 tests) |
| `search_notes` returns semantically relevant results for natural language queries | Hybrid search returns top-3 relevant notes for 10 benchmark queries against a 100+ note vault |
| A full vault reindex completes in under 60 seconds for 500 notes | Timed integration test |
| Dropping a PDF into `raw/` triggers automatic ingestion within 5 seconds | File watcher integration test |
| Claude can create, list, and close GitLab issues via `glab` | GitLab tool tests pass against a live test project |
| All destructive operations follow the confirmation flow | Confirmation flow unit tests pass |
| The server starts without LanceDB and falls back gracefully | Server startup test with no `.zk/vectors/` directory |
| `/zk daily`, `/zk capture`, `/zk find`, `/zk review`, `/zk weekly`, `/zk tasks`, `/zk health` all execute without errors in a live session | Manual acceptance test checklist |

---

### Constraints

| Constraint | Detail |
|---|---|
| Local only | No cloud services except `glab` CLI hitting a GitLab instance. No OpenAI, no Anthropic API calls from the server. |
| Package manager | `uv` exclusively. No `pip install` or `poetry`. |
| Python version | 3.12 or higher. |
| MCP framework | FastMCP. No raw `mcp` protocol implementation. |
| Embeddings | `sentence-transformers` with `nomic-embed-text-v1.5`, running locally on CPU. nomic-embed-text-v1.5 supports 8192 token context window, purpose-built for RAG and long document retrieval. Used via sentence-transformers ONNX backend (sentence-transformers[onnx]) to avoid PyTorch dependency. |
| No cloud vector store | LanceDB only, stored at `.zk/vectors/` inside the vault root. |
| GitLab integration | `glab` CLI only. No direct GitLab API calls. |
| Note format | Plain Markdown with minimal YAML frontmatter (title + date only) and inline `#tags` in note body. |
| Link format | Wikilinks (`[[title]]`) as used by `zk`. |
| Vault root | Configured via `ZK_NOTEBOOK_DIR` environment variable. Server never reads outside this directory. |

---

## 2. Architecture Overview

### Component Diagram

```
+------------------------------------------------------------------+
|                        Claude Code Session                        |
|                                                                    |
|   User input --> Claude LLM --> Skill logic (/zk commands)       |
|                                     |                              |
|                              MCP tool calls                        |
+-------------------------------------|-----------------------------+
                                       |
                          FastMCP (stdio transport)
                                       |
+-------------------------------------|-----------------------------+
|                         zk-mcp Server                             |
|                                                                    |
|  +----------------+  +------------------+  +------------------+  |
|  |  Tool Layer    |  |  Index Layer     |  |  Watcher Layer   |  |
|  |                |  |                  |  |                  |  |
|  | search_notes   |  | LanceDB          |  | watchdog         |  |
|  | get_note       |  | nomic-embed-     |  | file events      |  |
|  | create_note    |  | text-v1.5        |  | 2s debounce      |  |
|  | append_to_note |  | .zk/vectors/     |  | raw/ trigger     |  |
|  | move_note      |  +------------------+  +------------------+  |
|  | rename_note    |           |                      |            |
|  | replace_section|  +--------+---------+            |            |
|  | extract_section|  |  Ingestion Layer |            |            |
|  | get_todos      |  |                  |            |            |
|  | complete_todo  |  | pymupdf4llm      |<-----------+            |
|  | create_issue   |  | trafilatura      |  (raw/ drop)           |
|  | get_issues     |  | chunk + embed    |                        |
|  | close_issue    |  +------------------+                        |
|  | issue_to_note  |                                               |
|  | ingest         |                                               |
|  | reindex_vault  |                                               |
|  +----------------+                                               |
|          |                                                         |
+----------|--------------------------------------------------------+
           |
     +-----+-------------------------------+
     |                                     |
+----+-----+                     +---------+-------+
|  zk CLI  |                     |   glab CLI      |
|          |                     |                 |
| list     |                     | issue create    |
| new      |                     | issue list      |
| --match  |                     | issue close     |
| --linked-|                     | issue view      |
| --link-to|                     +---------+-------+
+----+-----+                               |
     |                             GitLab instance
+----+-----+
|  Vault   |
| ~/notes/ |
|          |
| daily/   |
| inbox.md |
| projects/|
| areas/   |
| people/  |
| ideas/   |
| learning/|
| resources|
| raw/     |
| archives/|
| .zk/     |
|  vectors/|
+----------+
```

---

### Data Flow

This describes how a request moves from a user statement to a response, using `/zk prep Sarah` as the example.

```
1. User types: /zk prep Sarah

2. Claude Code loads the /zk skill definition from .claude/commands/zk.md
   - Skill instructs Claude to search people/ for the name, then gather context

3. Claude calls MCP tool: search_notes(query="Sarah", directory="people")
   - FastMCP receives the tool call over stdio
   - Tool handler checks if LanceDB index exists at .zk/vectors/
   - If yes: encodes "Sarah" with nomic-embed-text-v1.5, runs hybrid query in LanceDB
   - If no: runs `zk list --match "Sarah" --directory people` as fallback
   - Returns: [{path, title, date, tags, excerpt, relevance_score}, ...]

4. Claude calls: get_note(path="people/sarah-chen.md")
   - Tool handler reads the file directly from disk
   - Parses inline #tags, extracts body
   - Returns: {path, title, date, tags, body}

5. Claude calls: get_backlinks(path="people/sarah-chen.md")
   - Tool handler runs: `zk list --linked-by people/sarah-chen.md`
   - Returns: [{path, title, excerpt}, ...]

6. Claude calls: search_notes(query="Sarah", since="30 days ago")
   - Finds daily notes and project notes that mention Sarah
   - Returns: [{path, title, date, tags, excerpt, relevance_score}, ...]

7. Claude reads the top backlinked and search-result notes via get_note() calls

8. Claude synthesizes the prep brief in its context window:
   - Background from the person note
   - Recent history from daily notes and backlinks
   - Open action items from - [ ] tasks found in the notes
   - Related projects

9. Claude displays the brief to the user and offers to save it as a new note
```

For write operations, the flow adds an index update step:

```
create_note / append_to_note / replace_section
    |
    v
Write file to vault (via direct file I/O)
    |
    v
Re-embed affected note in LanceDB (incremental, not full reindex)
    |
    v
Return {path, ...} to Claude
    |
    v
Claude reports what changed to user
```

For destructive operations, a confirmation step is inserted before the tool call:

```
Claude proposes action in natural language
    |
    v
User confirms (or pre-confirm flag is set)
    |
    v
Claude calls the tool
    |
    v
Tool executes
    |
    v
Claude reports result
```

---

### Key Design Principles

**Thin wrapper, not reimplementation.** The server delegates to `zk` for all note graph operations (search, backlinks, forward links, tag listing). It delegates to `glab` for all GitLab operations. It never maintains its own graph index or issue cache. The MCP layer handles orchestration, parameter validation, error translation, and LanceDB index management.

**Append-only safety.** `append_to_note` is always safe and requires no confirmation. `replace_section` is the only operation that overwrites existing content, and it returns the previous content so the user can audit the change. `create_note` fails loudly if a file already exists. Nothing is silently overwritten.

**zk as the authoritative engine.** The `zk` CLI maintains the note graph index. The MCP server does not maintain a parallel index of note titles, paths, or links. When wikilinks need updating after a move or rename, the server uses `zk list --linked-by` to find references, then updates them via direct file I/O. This keeps the vault portable: a user can remove the MCP server and continue using `zk` directly with no data loss.

**LanceDB for hybrid retrieval, not replacement.** LanceDB adds semantic search on top of `zk`'s keyword search. It is strictly additive. If the index is missing or corrupt, the server falls back to `zk list --match` without failing. The index is at `.zk/vectors/` and can be deleted and rebuilt without affecting any note content.

**Watchdog for resilience.** The file watcher ensures the LanceDB index stays current even when the user edits notes outside the MCP server (in their editor, via `zk new`, etc.). The 2-second debounce prevents thrashing during editor autosave. This means `/zk reindex` is a recovery tool, not a routine operation.

**Confirmation is Claude's responsibility.** The MCP server executes what it is called with. Confirmation logic lives in Claude's skill instructions, not in the server. This keeps the server stateless and simple. Session pre-confirm state is maintained by Claude, not persisted anywhere.

---

### Project File Structure

```
zk-mcp/
├── pyproject.toml              # uv project config, dependencies
├── uv.lock
├── README.md
├── .env.example                # ZK_NOTEBOOK_DIR, GITLAB_PROJECT, etc.
│
├── src/
│   └── zk_mcp/
│       ├── __init__.py
│       ├── server.py           # FastMCP server definition, tool registration
│       ├── config.py           # env var loading, vault root resolution
│       │
│       ├── tools/              # one file per logical tool group
│       │   ├── __init__.py
│       │   ├── read.py         # get_note, list_notes, get_tags, get_backlinks, get_links
│       │   ├── write.py        # create_note, append_to_note, update_tags
│       │   ├── inbox.py        # capture_to_inbox, get_inbox, clear_inbox_item
│       │   ├── search.py       # search_notes (zk fallback + LanceDB hybrid)
│       │   ├── structure.py    # move_note, rename_note, delete_note, find_references
│       │   ├── edit.py         # replace_section, extract_section
│       │   ├── tasks.py        # get_todos, complete_todo
│       │   ├── gitlab.py       # create_issue, get_issues, close_issue, issue_to_note
│       │   └── ingest.py       # ingest (PDF, URL, text)
│       │
│       ├── index/              # LanceDB vector index management
│       │   ├── __init__.py
│       │   ├── embedder.py     # sentence-transformers wrapper, chunking logic
│       │   ├── store.py        # LanceDB read/write operations
│       │   └── reindex.py      # full reindex, incremental update logic
│       │
│       ├── watcher.py          # watchdog file watcher, debounce, raw/ trigger
│       │
│       └── zk.py               # zk CLI subprocess wrapper (all `zk` calls go here)
│
├── tests/
│   ├── conftest.py             # shared fixtures: temp vault, mock zk, mock glab
│   ├── unit/
│   │   ├── tools/
│   │   │   ├── test_read.py
│   │   │   ├── test_write.py
│   │   │   ├── test_inbox.py
│   │   │   ├── test_search.py
│   │   │   ├── test_structure.py
│   │   │   ├── test_edit.py
│   │   │   ├── test_tasks.py
│   │   │   ├── test_gitlab.py
│   │   │   └── test_ingest.py
│   │   └── index/
│   │       ├── test_embedder.py
│   │       ├── test_store.py
│   │       └── test_reindex.py
│   │
│   └── integration/
│       ├── test_vault_navigation.py    # M1: read, write, search, inbox
│       ├── test_structure_ops.py       # M2: move, rename, delete, wikilink consistency
│       ├── test_hybrid_search.py       # M3: LanceDB search against real vault
│       ├── test_file_watcher.py        # M4: watchdog triggers, raw/ ingestion
│       └── test_gitlab_integration.py  # M5: glab CLI round-trips
│
└── vault_fixture/              # static test vault (100+ notes) for integration tests
    ├── daily/
    ├── projects/
    ├── people/
    ├── ideas/
    ├── resources/
    ├── raw/
    └── .zk/
        └── config.toml
```

---

## 3. Milestone Breakdown

### Overview

| Milestone | Theme | Key Deliverable |
|---|---|---|
| M1 | Core Foundation | Vault is fully readable and writable from Claude |
| M2 | Safety Operations | Structural changes are safe and wikilinks stay consistent |
| M3 | Hybrid Search and RAG | Natural language queries find relevant notes |
| M4 | File Watching and Ingestion | Vault stays in sync; external content enters the vault |
| M5 | GitLab Integration | Issues and vault todos are unified |

Each milestone produces a working, testable system. Later milestones enhance the system without breaking earlier behavior.

---

### Milestone 1: Core Foundation — Read, Write, Navigate

**Goal:** Claude can read any note, create notes in any folder, append to notes, capture to inbox, and search by keyword. The vault is fully navigable from a Claude session.

**Tools Delivered:**

| Tool | Notes |
|---|---|
| `search_notes` | Keyword-only via `zk list --match`. No LanceDB yet. Returns `relevance_score: null` in M1. |
| `get_note` | By path or title. Ambiguous title returns error with candidates. |
| `create_note` | With scaffold and template support. No `suggested_links` yet (requires LanceDB in M3). |
| `append_to_note` | Append-only, with optional dated header or section header. |
| `list_notes` | All filter parameters. Returns list without body content. |
| `get_backlinks` | Delegates to `zk list --linked-by`. |
| `get_links` | Delegates to `zk list --link-to`. |
| `get_tags` | Delegates to `zk tag list` or equivalent. |
| `capture_to_inbox` | Timestamped append to `inbox.md`. |
| `get_inbox` | Parse and return inbox items as structured list. |
| `update_tags` | Inline #tag edit without touching other content. |

**Skills Delivered:**

| Skill | Behavior |
|---|---|
| `/zk daily` | Open or create today's daily note. |
| `/zk capture [text]` | Zero-friction inbox append. |
| `/zk find [query]` | Keyword search with conversational result display. |
| `/zk person [name]` | Open or create a person note. |
| `/zk project [name]` | Open or create a project note. |

**Key Technical Tasks:**

1. Initialize `uv` project with FastMCP, pydantic, zk subprocess wrapper.
2. Implement `config.py`: read `ZK_NOTEBOOK_DIR`, validate vault root exists and contains `.zk/`.
3. Implement `zk.py`: `run_zk(args: list[str]) -> str` — subprocess wrapper with timeout, stderr capture, and `ZK_ERROR` exception.
4. Implement `tools/read.py`: `get_note`, `list_notes`, `get_backlinks`, `get_links`, `get_tags`.
5. Implement `tools/write.py`: `create_note`, `append_to_note`, `update_tags`. File I/O only — no index calls yet.
6. Implement `tools/inbox.py`: `capture_to_inbox`, `get_inbox`. Parse `inbox.md` as a flat timestamped list.
7. Implement `tools/search.py`: `search_notes` calling `zk list --match`. Include `relevance_score: null` in output schema so M3 upgrade is backward-compatible.
8. Implement `server.py`: register all M1 tools with FastMCP, wire up stdio transport.
9. Create `.claude/commands/zk.md` skill file covering M1 skills.
10. Write all M1 unit and integration tests (see test cases below).
11. Create `vault_fixture/` with 20+ notes covering all vault directories for integration tests.

**Done When:**

- [ ] All M1 unit tests pass with mocked `zk` CLI
- [ ] All M1 integration tests pass against `vault_fixture/` with a real `zk` binary
- [ ] `get_note` returns correct content for a note retrieved by title and by path
- [ ] `create_note` returns `ALREADY_EXISTS` when a file already exists at the target path
- [ ] `append_to_note` does not modify existing content — only appends
- [ ] `capture_to_inbox` appends a correctly timestamped item; `get_inbox` returns it at the right index
- [ ] `search_notes` returns results for a keyword that exists in vault notes
- [ ] `list_notes` with `since`, `directory`, and `tag` filters returns correct subsets
- [ ] FastMCP server starts, registers all tools, and responds to a `tools/list` call
- [ ] `/zk daily`, `/zk capture`, `/zk find`, `/zk person`, `/zk project` skills execute without errors in a live Claude session

**Test Cases:**

```
# Read
test_get_note_by_path_returns_correct_content
test_get_note_by_title_returns_correct_content
test_get_note_by_ambiguous_title_returns_error_with_candidates
test_get_note_missing_returns_not_found

# Write
test_create_note_creates_file_with_correct_frontmatter
test_create_note_scaffold_mode_has_no_body_content
test_create_note_duplicate_returns_already_exists
test_append_to_note_does_not_modify_existing_content
test_append_to_note_with_dated_header_inserts_date
test_update_tags_adds_tags_without_touching_body
test_update_tags_removes_tags_without_touching_body
test_update_tags_returns_before_and_after_state

# Inbox
test_capture_to_inbox_appends_with_iso_timestamp
test_capture_format_is_plain_list_item_not_checkbox
test_get_inbox_returns_structured_list_with_index
test_get_inbox_empty_returns_empty_list

# Search and Navigation
test_search_notes_keyword_returns_matching_notes
test_search_notes_directory_filter_limits_results
test_search_notes_tag_filter_limits_results
test_search_notes_since_filter_limits_results
test_list_notes_no_filter_returns_all_sorted_by_modified
test_list_notes_recent_returns_n_most_recent
test_get_backlinks_returns_linking_notes
test_get_links_returns_linked_notes
test_get_tags_returns_all_tags_with_counts

# Server
test_server_starts_and_registers_all_tools
test_server_tools_list_includes_all_m1_tools
test_tool_error_returns_structured_error_with_code_and_message
```

---

### Milestone 2: Safety Operations — Move, Rename, Delete, Tasks, Gardening

**Goal:** All structural operations work with the confirmation flow. Wikilinks stay consistent after move and rename. Tasks can be found and completed. Vault health check runs cleanly.

**Tools Delivered:**

| Tool | Notes |
|---|---|
| `move_note` | Move to new directory, update all wikilinks referencing old title/path, return `updated_references`. |
| `rename_note` | Update title, rename file to new slug, update all wikilinks vault-wide. |
| `delete_note` | Soft-delete: move to `archives/`. Optional `reason` written to note before move. Cannot archive an already-archived note. |
| `find_references` | Find all wikilinks and optional text mentions of a note title. Used internally by move/rename. |
| `clear_inbox_item` | Remove inbox item by index. Validates index before removing — stale index returns error. |
| `replace_section` | Replace content of a named `##` section. Returns `SECTION_NOT_FOUND` if header missing. |
| `extract_section` | Extract a section into a new note, leave wikilink in original. |
| `get_todos` | Scan specified directories for `- [ ]` tasks. Returns path, line number, task text. |
| `complete_todo` | Change `- [ ]` to `- [x]`. Validates line, fuzzy fallback ±5 lines on stale line number. |

**Skills Delivered:**

| Skill | Behavior |
|---|---|
| `/zk review` | Inbox review with per-item propose+confirm. Pre-confirm mode supported. |
| `/zk rename [old] to [new]` | Propose rename + wikilink count, confirm, execute. |
| `/zk archive [query]` | Find note, propose archive, confirm, call `delete_note`. |
| `/zk tasks` | Vault todos only (no GitLab yet — that is M5). |
| `/zk refactor [note]` | Read note, propose restructure, use `replace_section` and `extract_section`. |
| `/zk health` | Dead links, orphaned notes, stale notes. Offer to fix each. |

**Key Technical Tasks:**

1. Implement `tools/structure.py`: `move_note`, `rename_note`, `delete_note`, `find_references`.
   - Shared wikilink-update utility: `find_and_replace_wikilinks(old_title, new_title, vault_root) -> list[path]`.
   - `find_references` uses `zk list --linked-by` for wikilinks; plain text search for `include_text_mentions=true`.
2. Implement `tools/inbox.py` additions: `clear_inbox_item`. Validate index against current file state before removing. Re-parse file after removal to verify.
3. Implement `tools/edit.py`: `replace_section`, `extract_section`.
   - Section parsing: split on `##` headers, identify target section by exact header text match, replace content between target header and next `##` header (or EOF).
   - `extract_section` composes `create_note` + `replace_section` internally.
4. Implement `tools/tasks.py`: `get_todos`, `complete_todo`.
   - `get_todos`: scan files directly with regex `- \[ \]`. Group by source file.
   - `complete_todo`: validate line, apply fuzzy ±5 fallback using `task_text` substring match, replace `- [ ]` with `- [x]`.
5. Update `server.py` to register all M2 tools.
6. Update skill file with M2 skills.
7. Write all M2 unit and integration tests.

**Done When:**

- [ ] All M2 unit tests pass
- [ ] All M2 integration tests pass against `vault_fixture/`
- [ ] `move_note` updates all wikilinks in the vault that reference the moved note's title
- [ ] `rename_note` updates all wikilinks referencing the old title across all vault files
- [ ] `delete_note` moves note to `archives/` and fails gracefully if already archived
- [ ] `delete_note` with `reason` writes `archived_reason` before moving
- [ ] `clear_inbox_item` with a stale index returns an error, not a silent wrong removal
- [ ] `replace_section` returns `SECTION_NOT_FOUND` when the header does not exist
- [ ] `replace_section` returns previous content alongside new content
- [ ] `extract_section` leaves a wikilink in the source note and creates a valid new note
- [ ] `get_todos` returns results grouped by source note with correct line numbers
- [ ] `complete_todo` changes `- [ ]` to `- [x]` and returns `TASK_NOT_FOUND` if line is gone and fuzzy match fails
- [ ] `/zk review` processes inbox items with per-item confirmation and pre-confirm mode
- [ ] `/zk health` surfaces dead links, orphans, and stale notes

**Test Cases:**

```
# Move and Rename (Wikilink Consistency)
test_move_note_updates_wikilinks_in_other_notes
test_move_note_returns_updated_references_list
test_move_note_to_nonexistent_directory_returns_error
test_rename_note_updates_file_slug
test_rename_note_updates_all_wikilinks_vault_wide
test_rename_note_returns_old_and_new_path
test_rename_note_to_conflicting_slug_returns_rename_conflict

# Delete
test_delete_note_moves_to_archives
test_delete_note_already_archived_returns_error
test_delete_note_with_reason_writes_archived_reason_to_frontmatter

# Find References
test_find_references_returns_wikilinks_only_by_default
test_find_references_include_text_mentions_returns_both
test_find_references_no_matches_returns_empty_list

# Inbox
test_clear_inbox_item_removes_correct_item
test_clear_inbox_item_stale_index_returns_error
test_clear_inbox_item_empty_inbox_returns_error

# Section Editing
test_replace_section_replaces_only_target_section
test_replace_section_does_not_modify_other_sections
test_replace_section_missing_header_returns_section_not_found
test_replace_section_returns_previous_and_new_content
test_extract_section_creates_new_note_with_section_content
test_extract_section_replaces_source_section_with_wikilink

# Tasks
test_get_todos_finds_all_open_tasks_in_specified_dirs
test_get_todos_since_filter_limits_to_recent_notes
test_complete_todo_changes_checkbox_to_x
test_complete_todo_stale_line_number_uses_fuzzy_match
test_complete_todo_no_match_returns_task_not_found
test_complete_todo_never_completes_wrong_task

# Confirmation Flow
test_confirmation_required_tools_list_matches_spec
test_preconfirm_flag_skips_pause_but_still_announces
```

---

### Milestone 3: Hybrid Search and RAG

**Goal:** `search_notes` uses LanceDB hybrid search. Synthesis features use semantic retrieval. A vault of 100+ notes returns semantically relevant results for natural language queries.

**Tools Delivered:**

| Tool | Change |
|---|---|
| `search_notes` | Upgraded: uses LanceDB hybrid search (vector + keyword) when index is available. Falls back to M1 keyword search. Metadata filters applied at LanceDB query level. `relevance_score` field now populated (0.0–1.0). |
| `reindex_vault` | New: full rebuild of LanceDB index. Requires `confirm=true`. Returns `{notes_indexed, chunks_created, duration_seconds}`. |

**Skills Delivered:**

| Skill | Behavior |
|---|---|
| `/zk synthesize [topic]` | Semantic `search_notes` + multi-note synthesis. |
| `/zk prep [name]` | Now uses semantic search to find all related notes, not just keyword match. |
| `/zk stale` | Lists ideas/ and projects/ untouched 30+ days. |
| `/zk weekly` | Full version: daily notes + project notes + stale check + health. |
| `/zk reindex` | Warn, confirm, call `reindex_vault`, report result. |

**Key Technical Tasks:**

1. Implement `index/embedder.py`:
   - Load `nomic-embed-text-v1.5` on first use (lazy load to avoid slow startup). nomic-embed-text-v1.5 supports 8192 token context window, purpose-built for RAG and long document retrieval. Used via sentence-transformers ONNX backend (sentence-transformers[onnx]) to avoid PyTorch dependency.
   - `chunk_note(path, content) -> list[Chunk]`: split on `##` headers, each chunk gets `{path, title, tags, directory, modified_date, chunk_index, text}`.
   - `embed_chunks(chunks) -> list[np.ndarray]`: batch encode with sentence-transformers.
2. Implement `index/store.py`:
   - `upsert_note(path, chunks, embeddings)`: replace all existing chunks for this path, insert new ones. Atomic per-note — no partial states.
   - `delete_note(path)`: remove all chunks for this path.
   - `hybrid_search(query, directory, tags, since, limit) -> list[SearchResult]`: vector ANN search + keyword re-rank, apply metadata pre-filter.
   - `update_metadata(path, new_path, new_title, new_tags)`: update metadata fields without re-embedding.
3. Implement `index/reindex.py`:
   - `reindex_all(vault_root) -> ReindexResult`: enumerate all `.md` files, chunk and embed in batches, write to LanceDB atomically (write to temp table, then rename). Track duration.
4. Update `tools/write.py`: after each write, call `store.upsert_note` for the affected note. Move/rename calls `store.update_metadata`.
5. Update `tools/search.py`: `search_notes` checks for index, routes to `store.hybrid_search` or `zk list --match` fallback.
6. Implement `tools/read.py` addition: `reindex_vault` tool.
7. Create `vault_fixture/` expansion: grow to 100+ notes across all directories for semantic search integration tests.
8. Write benchmark: 10 natural language queries with expected top-3 results, assert all expected notes appear in top 5 actual results.

**Done When:**

- [ ] All M3 unit tests pass
- [ ] Hybrid search integration tests pass: 10 benchmark queries return expected notes in top 5 results
- [ ] `search_notes` returns `relevance_score` as a float 0.0–1.0
- [ ] `search_notes` falls back to `zk list --match` with a warning when no index exists
- [ ] `reindex_vault` without `confirm=true` returns an error, not a silent no-op
- [ ] `reindex_vault` completes in under 60 seconds for the 100-note `vault_fixture/`
- [ ] After `create_note` or `append_to_note`, the new content is findable via `search_notes` semantic query
- [ ] `move_note` and `rename_note` update LanceDB metadata without re-embedding
- [ ] `delete_note` removes the archived note from the LanceDB active index
- [ ] `/zk synthesize` returns a coherent cross-note synthesis from semantic retrieval
- [ ] `/zk weekly` runs end-to-end using semantic search for project and daily note retrieval

**Test Cases:**

```
# Embedder
test_chunk_note_splits_on_double_hash_headers
test_chunk_note_no_headers_returns_single_chunk
test_chunk_note_includes_correct_metadata_fields
test_embed_chunks_returns_correct_dimension_vectors

# Store
test_upsert_note_replaces_existing_chunks_for_path
test_upsert_note_is_atomic_no_partial_states
test_delete_note_removes_all_chunks_for_path
test_hybrid_search_returns_results_with_relevance_score
test_hybrid_search_directory_filter_limits_results
test_hybrid_search_tag_filter_limits_results
test_hybrid_search_since_filter_limits_results
test_update_metadata_does_not_change_embeddings

# Reindex
test_reindex_all_indexes_all_vault_notes
test_reindex_all_is_atomic_old_index_usable_during_reindex
test_reindex_all_returns_correct_note_and_chunk_counts

# Search tool
test_search_notes_uses_lancedb_when_index_exists
test_search_notes_falls_back_to_zk_when_no_index
test_search_notes_returns_relevance_score_float

# Semantic correctness (integration, real vault)
test_semantic_query_kubernetes_finds_k8s_notes
test_semantic_query_zero_trust_finds_related_security_notes
test_semantic_query_returns_expected_notes_in_top_5_for_10_benchmarks

# Index updates on write
test_create_note_triggers_index_upsert
test_append_to_note_triggers_index_upsert
test_replace_section_triggers_index_upsert
test_move_note_updates_lancedb_metadata
test_rename_note_updates_lancedb_metadata
test_delete_note_removes_from_lancedb
```

---

### Milestone 4: File Watching and Ingestion

**Goal:** Dropping a PDF or Markdown file into `raw/` automatically ingests it. Manual vault edits are reflected in LanceDB within 5 seconds. URLs can be ingested via `/zk ingest`.

**Tools Delivered:**

| Tool | Notes |
|---|---|
| `ingest` | Ingest a local file or URL. Extracts content, chunks and embeds into LanceDB. Returns `{ raw_text, title, source, chunks_indexed, suggested_links }`. Idempotent by source. Summary generation is Claude's responsibility at the skill layer. |

**`ingest` tool spec:**

Parameters: `source` (URL or file path), `title` (optional override), `tags` (optional list), `depth` (integer, optional, default 0).

Output: `{ raw_text, title, source, chunks_indexed, suggested_links }`

Notes:
- For PDFs: extracts text via `pymupdf4llm` as clean Markdown (headers, bold, lists preserved), ideal for chunking. If extracted text is empty or very short (scanned PDF), the tool returns a clear error: "This PDF appears to be scanned. OCR is not supported — consider copy-pasting the text manually."
- For URLs: fetches content via `trafilatura` to extract article body, ignores nav/ads. trafilatura handles URL fetch + content extraction. Supports focused crawling (follow relevant links) via trafilatura.spider.focused_crawler. httpx used instead of requests for async compatibility with FastMCP tools.
- For markdown/text: reads directly, chunks by `##` header like regular notes.
- Returns `raw_text` — the full extracted content. Summary generation is Claude's responsibility at the skill layer, not the server's.
- `suggested_links` returns top 5 semantically related existing notes so Claude can offer wikilinks immediately after ingestion.
- Idempotent: if a resource note with the same source already exists, updates it rather than creating a duplicate. Matched by source URL or filename.
- Dropping a file into `raw/` triggers this automatically via the file watcher.
- When `depth=1`, uses trafilatura's focused_crawler to discover and ingest topically related URLs from the seed page. Each discovered URL is ingested as a separate resource note. Returns `{ ingested_sources: list[{url, note_path}] }` in addition to the primary note.

**Infrastructure Delivered:**

- `watcher.py`: watchdog event handler watching vault root.
  - On file created/modified in vault (excluding `.zk/`, `.git/`, binary files in `raw/`): debounce 2s, then call `store.upsert_note`.
  - On file deleted in vault: call `store.delete_note`.
  - On file created in `raw/` (`.pdf`, `.md`, `.txt`): trigger `ingest` automatically.

**Skills Delivered:**

| Skill | Behavior |
|---|---|
| `/zk ingest [source]` | See behavior detail below. |

**`/zk ingest` Behavior:**

1. Calls `ingest` with the source (URL or `raw/` file path).
2. Server returns `raw_text`, `title`, `chunks_indexed`, `suggested_links`.
3. Claude generates a summary from `raw_text` — brief (3-5 bullets) by default, or detailed if the user requested it.
4. Claude calls `create_note` in `resources/` with sections: `## Summary` (Claude-generated), `## Key Points` (Claude-generated), `## Source` (URL or filename), `## Raw Content` (raw_text in a `<details>` block).
5. Reports: "Ingested '[title]' — created `resources/[slug].md`, indexed N chunks."
6. Shows top 3 related notes from `suggested_links` and offers to add wikilinks.
7. Offers to move the source file out of `raw/` to avoid re-triggering ingestion.

**Key Technical Tasks:**

1. Implement `watcher.py`:
   - Use `watchdog` `Observer` + custom `EventHandler`.
   - Debounce: maintain per-path timer, reset on rapid successive events, fire after 2s of quiet.
   - Ignore patterns: `.zk/`, `.git/`, binary file extensions in `raw/` (`.pdf`, `.docx`, etc. are handled by `ingest`, not direct embedding).
   - Start watcher in a background thread when the FastMCP server starts.
2. Implement `tools/ingest.py`:
   - `ingest(source, title, tags, depth=0)`.
   - PDF path: `pymupdf4llm` extracts text as clean Markdown per page/section boundary.
   - URL path: `trafilatura` fetch + extract article body, then chunk by section. httpx used for any additional async HTTP needs.
   - Markdown/text path: read directly, chunk by `##` header.
   - Returns `raw_text` (full extracted text) — Claude generates the summary at the skill layer.
   - Idempotency: scan `resources/` for existing note with matching source URL or filename. If found, update LanceDB chunks for that note. Do not create a duplicate.
   - Embed into LanceDB with `source_type: ingested` metadata.
   - Run `search_notes` to find top 5 semantically related vault notes. Return as `suggested_links`.
   - When `depth=1`, call `trafilatura.spider.focused_crawler` on the seed URL and ingest each discovered URL as a separate resource note.
3. Wire `raw/` drop event: when watcher detects a new file in `raw/`, call `ingest` with that path. If a Claude session is active, the result is surfaced in the session (this is best-effort — the watcher logs the result, Claude reads it on next interaction).
4. Update `server.py` to start the watcher thread on startup.
5. Update skill file with `/zk ingest`.
6. Write M4 unit and integration tests, including timing tests for the 5-second SLA.

**Done When:**

- [ ] All M4 unit tests pass
- [ ] File watcher integration test: create a `.md` file in the vault, assert LanceDB is updated within 5 seconds
- [ ] File watcher integration test: delete a `.md` file, assert LanceDB entry is removed within 5 seconds
- [ ] File watcher debounce test: modify a file 10 times in 1 second, assert only 1 re-embed occurs
- [ ] File watcher ignores `.zk/` directory changes
- [ ] `ingest` with a PDF path creates a `resources/` note with `## Summary`, `## Key Points`, `## Source`, `## Raw Content` sections
- [ ] `ingest` with a URL creates a resource note with extracted article body
- [ ] `ingest` is idempotent: re-ingesting the same source updates the existing note, does not create a duplicate
- [ ] `ingest` returns `suggested_links` with top 5 semantically related notes
- [ ] Dropping a PDF into `raw/` triggers `ingest` automatically (watcher integration test)
- [ ] `/zk ingest [url]` executes successfully and reports the created note

**Test Cases:**

```
# Watcher unit tests
test_watcher_debounce_fires_once_after_quiet_period
test_watcher_debounce_resets_on_rapid_changes
test_watcher_ignores_zk_directory_events
test_watcher_ignores_git_directory_events
test_watcher_triggers_upsert_on_md_file_change
test_watcher_triggers_delete_on_md_file_removal
test_watcher_triggers_ingest_on_raw_file_drop

# Ingest unit tests
test_ingest_pdf_extracts_text_via_pymupdf4llm
test_ingest_url_extracts_article_body_via_trafilatura
test_ingest_markdown_chunks_by_section_header
test_ingest_creates_resource_note_with_correct_sections
test_ingest_idempotent_updates_existing_note_not_duplicate
test_ingest_embeds_into_lancedb_with_ingested_source_type
test_ingest_returns_suggested_links
test_ingest_depth_1_follows_links_via_focused_crawler

# Integration tests
test_watcher_integration_md_file_indexed_within_5_seconds
test_watcher_integration_deleted_file_removed_within_5_seconds
test_raw_drop_integration_pdf_ingested_automatically
test_ingest_integration_url_creates_resource_note
```

---

### Milestone 5: GitLab Integration

**Goal:** Claude can create, list, and close GitLab issues. Meeting notes can be converted to issues. `/zk tasks` shows vault todos and GitLab issues in one view.

**Tools Delivered:**

| Tool | Notes |
|---|---|
| `create_issue` | Create GitLab issue via `glab issue create`. If `note_path` provided, appends issue URL to that note. Requires `GITLAB_PROJECT` env var. |
| `get_issues` | List open issues via `glab issue list`. Live, no caching. |
| `close_issue` | Close issue via `glab issue close`. Requires confirmation. Optional closing comment. |
| `issue_to_note` | Pull issue into vault as a snapshot note in `projects/` (or specified directory). Idempotent by issue URL. |

**Skills Delivered:**

| Skill | Change |
|---|---|
| `/zk tasks` | Updated: now calls `get_todos` AND `get_issues`. Unified view. Offers to create issue from task or mark task complete. |
| `/zk weekly` | Updated: includes GitLab issue count in weekly summary. |

**Key Technical Tasks:**

1. Implement `tools/gitlab.py`:
   - Shared `glab.py` subprocess wrapper: `run_glab(args: list[str]) -> str`. Raises `GitLabError` on non-zero exit.
   - `create_issue`: construct `glab issue create --title ... --description ... --label ...` command. Parse output to extract issue number and URL. If `note_path` given, call `append_to_note` to add the reference line.
   - `get_issues`: run `glab issue list --output json`, parse JSON, return structured list.
   - `close_issue`: run `glab issue close <number>`. If `comment` provided, run `glab issue note <number> --message <comment>` first.
   - `issue_to_note`: fetch issue via `glab issue view <number> --output json`, construct note body, call `create_note` in `projects/`. Check for existing note with matching URL before creating.
2. Add `GITLAB_PROJECT` and `GITLAB_DEFAULT_LABELS` to `config.py`. If `GITLAB_PROJECT` is unset, all GitLab tools return a clear `GITLAB_NOT_CONFIGURED` error rather than crashing.
3. Update `/zk tasks` skill to call both `get_todos` and `get_issues`, merge into unified view.
4. Update `/zk weekly` skill to include GitLab issue count.
5. Write M5 unit tests with mocked `glab` subprocess. Write integration tests against a real GitLab test project (requires `GITLAB_PROJECT` set in test environment).

**Done When:**

- [ ] All M5 unit tests pass with mocked `glab`
- [ ] `create_issue` creates an issue and returns the correct `issue_number` and `url`
- [ ] `create_issue` with `note_path` appends the issue URL reference to the specified note
- [ ] `get_issues` returns a live list of open issues including all required fields
- [ ] `close_issue` requires confirmation; closes the issue; optional comment is posted first
- [ ] `issue_to_note` creates a snapshot note with issue title, URL, description, labels, and status
- [ ] `issue_to_note` does not create a duplicate if the issue URL already exists in a note
- [ ] GitLab tools return `GITLAB_NOT_CONFIGURED` error if `GITLAB_PROJECT` is not set
- [ ] `/zk tasks` shows vault todos and GitLab issues in one unified view
- [ ] `/zk tasks` offers to create a GitLab issue from a vault task
- [ ] M1-M4 tests still pass after M5 additions (no regressions)

**Test Cases:**

```
# GitLab tool unit tests (mocked glab)
test_create_issue_calls_glab_with_correct_args
test_create_issue_parses_issue_number_and_url_from_output
test_create_issue_with_note_path_appends_reference_to_note
test_create_issue_default_labels_from_env_when_none_provided
test_get_issues_parses_glab_json_output
test_get_issues_label_filter_passes_to_glab
test_close_issue_calls_glab_close
test_close_issue_with_comment_posts_note_before_close
test_issue_to_note_creates_note_with_correct_structure
test_issue_to_note_idempotent_no_duplicate_for_same_url
test_gitlab_tools_return_not_configured_when_env_var_missing
test_glab_error_surfaces_as_gitlab_error_with_message

# Integration tests (real glab, real GitLab project)
test_create_list_close_issue_round_trip
test_issue_to_note_creates_readable_note
```

---

## 4. TDD Strategy

### Test Structure

Tests live in `tests/` at the project root. Two top-level directories: `unit/` and `integration/`.

```
tests/
├── conftest.py                    # Shared fixtures
├── unit/
│   ├── tools/                     # One test file per tool module
│   └── index/                     # One test file per index module
└── integration/
    ├── test_vault_navigation.py    # M1 end-to-end
    ├── test_structure_ops.py       # M2 end-to-end
    ├── test_hybrid_search.py       # M3 end-to-end (real LanceDB, real vault)
    ├── test_file_watcher.py        # M4 end-to-end (real watchdog, real files)
    └── test_gitlab_integration.py  # M5 end-to-end (real glab)
```

Tests are run with `uv run pytest`. Integration tests are marked with `@pytest.mark.integration` and excluded from the default run (`pytest -m "not integration"`). CI runs both separately.

---

### What to Mock

**Unit tests mock everything external:**

| External Dependency | Mock Strategy |
|---|---|
| `zk` CLI | Mock `subprocess.run` in `zk.py`. Return canned JSON/text output per test case. |
| `glab` CLI | Mock `subprocess.run` in `glab.py`. Return canned JSON/text output per test case. |
| File system | Use `tmp_path` pytest fixture for real temp directories. Do not mock file I/O — it is fast and writing to temp dirs is reliable. |
| LanceDB | In unit tests for tools that call the index, mock `store.upsert_note`, `store.delete_note`, `store.hybrid_search`. Test the index layer itself separately in `tests/unit/index/`. |
| sentence-transformers | In index unit tests, mock `SentenceTransformer.encode`. Return fixed-dimension random vectors. This avoids loading the model in unit tests (slow). |
| httpx / URL fetch | Mock in `ingest` unit tests. Return canned HTML content. |

**Integration tests use real dependencies:**

| Dependency | Integration Test Approach |
|---|---|
| `zk` CLI | Requires real `zk` binary installed. Tests run against `vault_fixture/` with a real `.zk/` directory initialized. |
| File system | Real temp directory copied from `vault_fixture/` before each test, torn down after. |
| LanceDB | Real LanceDB store in temp directory. Tests build the index from `vault_fixture/` notes. |
| sentence-transformers | Real model loaded once per session (use `session`-scoped fixture). Slow on first run; model is cached by sentence-transformers in `~/.cache`. |
| `glab` CLI | Requires real `glab` binary and `GITLAB_PROJECT` env var. M5 integration tests are skipped if env var is not set. |

---

### Integration Test Approach

Each integration test:

1. Copies `vault_fixture/` to a `tmp_path` temp directory.
2. Sets `ZK_NOTEBOOK_DIR` to the temp directory.
3. Runs `zk init` if needed (or uses the pre-initialized `.zk/` from the fixture copy).
4. Instantiates the tool functions directly (not via FastMCP transport) for speed.
5. Asserts outcomes against the real file system and real LanceDB.

The `vault_fixture/` directory is committed to the repository. It contains at minimum:
- 5 daily notes (last 7 days)
- 5 project notes with wikilinks to each other
- 5 people notes
- 3 idea notes (2 stale, 1 recent)
- 5 resource notes
- A populated `inbox.md` with 8 items
- Notes with `- [ ]` tasks across projects/ and daily/
- Notes with broken wikilinks and orphaned notes (for health check tests)

For M3 and above, `vault_fixture/` is expanded to 100+ notes to test semantic search meaningfully.

---

### Key Test Categories

**Tool unit tests** — fast, fully mocked, cover all parameter combinations and error paths. Every tool function has a corresponding test file. Coverage target: 90%+ on `src/zk_mcp/tools/`.

**Confirmation flow tests** — verify that the list of tools requiring confirmation matches the spec exactly. This is a simple unit test: instantiate each tool, check whether it is in the confirmed-required list. Also verify that `complete_todo`, `append_to_note`, and `capture_to_inbox` are NOT in the confirmed-required list.

**Wikilink consistency tests** — the most critical correctness tests. After `move_note` or `rename_note`, scan every `.md` file in the temp vault and assert no wikilinks reference the old title. Also assert that the `updated_references` list returned by the tool matches the actual files that were changed.

**LanceDB index tests** — verify chunk structure, embedding dimensions, metadata fields, upsert atomicity, and hybrid search correctness. Use real LanceDB in temp directory. Mock the embedding model with fixed-dimension random vectors (correctness of semantic ranking is tested separately in integration tests with the real model).

**Ingestion tests** — verify PDF extraction (use a small test PDF in `tests/fixtures/`), URL extraction (mock httpx), and idempotency. Assert that re-ingesting the same source does not create a duplicate note.

---

## 5. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | **zk CLI version incompatibility** — the server wraps `zk` CLI output and flag behavior. A `zk` version change could break JSON output format, flag names, or exit codes. | Medium | High | Pin the minimum `zk` version in documentation. Add a startup check: run `zk --version` and warn if the version is below the tested minimum. Parse `zk` output defensively — never assume a fixed field count. Integration tests catch breakage immediately. |
| 2 | **LanceDB index drift** — the watchdog debounce, crash recovery, or rapid manual edits could leave LanceDB out of sync with the vault. Users may get stale or missing results without realizing it. | Medium | Medium | The fallback to `zk list --match` means stale index degrades search quality but does not break the system. Expose `/zk reindex` clearly. Consider adding a startup health check: compare note count in vault vs. LanceDB, warn if they diverge by more than 10%. |
| 3 | **sentence-transformers model slow to load** — `nomic-embed-text-v1.5` takes 2–5 seconds to load on first use. If loaded at server startup, this delays the first MCP response. If lazy-loaded, the first `search_notes` call is slow. | High | Low | Lazy-load the model in a background thread 5 seconds after server startup. Cache the loaded model as a module-level singleton. This means the first call after a fresh start may be slow (model loading) but all subsequent calls are fast. Document the cold-start behavior. |
| 4 | **Wikilink update false positives or misses** — the wikilink scan-and-replace logic must correctly match `[[old-title]]` across all notes without matching partial titles or plain text. A bug here could silently corrupt wikilinks across the vault. | Low | High | Use `find_references` as the authoritative source for what to update. Write a comprehensive wikilink consistency test suite that covers: exact title match, title as substring of another wikilink, titles with special characters, titles that appear in code blocks (should not be updated). Require the wikilink consistency tests to pass before M2 is marked done. |
| 5 | **glab CLI not available or not authenticated** — GitLab tools fail silently or with confusing errors if `glab` is not installed or the user is not authenticated. | Medium | Medium | At server startup, if `GITLAB_PROJECT` is set, run `glab auth status` as a health check. Log a clear warning if it fails. All GitLab tools return `GITLAB_NOT_CONFIGURED` or `GITLAB_ERROR` with a clear message. Never allow a `glab` failure to crash the server — catch subprocess errors and return structured error responses. |

---

## 6. Open Questions

These are unresolved decisions that should be made before or during implementation of the relevant milestone.

| # | Question | Status | Resolution |
|---|---|---|---|
| 1 | **Inline #tags vs frontmatter format** | **RESOLVED** | Option A: minimal frontmatter (title + date only), inline `#tags` in note body. All tools read title/date from frontmatter, tags from inline body scan. |
| 2 | **How does `update_tags` find and edit inline tags?** | Open | Recommend: scan for `#word` patterns not inside backticks or code fences. For removal, delete the `#tag` and trailing space. For addition, append to a "Tags:" line near the top of the body or at EOF. Decide and document the convention before M1 implementation. |
| 3 | **LanceDB concurrent reindex safety** | Open | Use LanceDB native table create + rename pattern. Write to `vectors_new`, then overwrite `vectors`. Document behavior for in-flight queries during switchover. Resolve before M3. |
| 4 | **Who generates the ingest summary** | **RESOLVED** | The `ingest` tool (server-side) handles: URL fetch, content extraction via trafilatura, chunking, LanceDB embedding, idempotency check. It returns `{ raw_text, title, chunks_indexed, suggested_links }`. Claude (skill layer) generates the summary from `raw_text` and calls `create_note` with the composed content. The `summary_style` parameter is removed from the `ingest` tool signature — it becomes a prompt instruction in the `/zk ingest` skill. |
| 5 | **Watcher gap: manual edits while server is off** | **RESOLVED** | On server startup, compare each `.md` file mtime against LanceDB `modified_date` metadata. Re-embed any files newer than their LanceDB entry. Cap at 60 seconds; log warning and recommend `/zk reindex` if exceeded. |
| 6 | **Starter templates** | Open | Provide example templates in `vault_fixture/.zk/templates/` for `person`, `project`, `daily`, and `area`. Document that users copy these to their own vault. Do not auto-create templates — vault setup is outside the MCP server's responsibility. |

---

## 7. Resolved Decisions Log

A running record of key decisions made during requirements and planning, for future reference.

| Decision | Resolution | Date |
|---|---|---|
| Note format | Option A: minimal YAML frontmatter (title + date only), inline `#tags` in body. Not full YAML frontmatter, not frontmatter-free. | 2026-02-27 |
| Summary generation for ingest | Server extracts and returns `raw_text`. Claude generates summary at skill layer. `summary_style` is a skill prompt instruction, not a server parameter. | 2026-02-27 |
| Startup index sync | On server startup, compare file mtimes against LanceDB metadata. Re-embed stale notes incrementally. Cap at 60s, then warn. | 2026-02-27 |
| No permanent deletes | `delete_note` always moves to `archives/`. Nothing is ever permanently removed via MCP tools. | 2026-02-27 |
| Confirmation is Claude's responsibility | The MCP server executes what it is called with. Confirmation logic lives in skill instructions. Server is stateless. | 2026-02-27 |
| zk as authoritative graph engine | MCP server never maintains its own note graph. All link/backlink/tag queries delegate to `zk` CLI. | 2026-02-27 |
| LanceDB is additive | If `.zk/vectors/` is missing, server falls back to `zk list --match`. Index is never required for basic operation. | 2026-02-27 |
| GitLab source of truth | Vault never stores issue state. All GitLab reads hit `glab` live. `issue_to_note` creates a snapshot, not a live mirror. | 2026-02-27 |
| wikilink updates on move/rename | In scope for v1. Shared utility used by both `move_note` and `rename_note`. | 2026-02-27 |
| Embedding model | nomic-embed-text-v1.5 via sentence-transformers ONNX backend. 8192 token context, RAG-optimized, no PyTorch runtime required. | 2026-02-27 |
| PDF extraction | pymupdf4llm over pdfplumber. Outputs clean Markdown, faster, better for chunking. Scanned PDFs return a clear error in v1 — no OCR. | 2026-02-27 |
| Web extraction | trafilatura over readability-lxml. Better accuracy, actively maintained, has built-in focused crawler for link following. | 2026-02-27 |
| HTTP client | httpx over requests. Async-safe for FastMCP tool functions. Drop-in replacement API. | 2026-02-27 |
| Ingest depth | `depth` parameter on `ingest` tool. depth=0 (default) = single URL. depth=1 = follow relevant links via trafilatura focused_crawler. | 2026-02-27 |

---

## Dependency Validation

### Recommended `pyproject.toml`

```toml
[project]
requires-python = ">=3.12"
dependencies = [
    "fastmcp>=3.0.2",
    "lancedb>=0.29,<0.31",
    "sentence-transformers[onnx]>=5.2",
    "pymupdf4llm>=0.0.17",
    "trafilatura>=2.0",
    "httpx>=0.28",
    "watchdog>=6.0",
]

[dependency-groups]
dev = [
    "pytest>=9.0",
    "pytest-asyncio>=1.3",
    "pytest-mock>=3.15",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```
