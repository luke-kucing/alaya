# zk-mcp Requirements Document

**Version:** 1.4
**Date:** 2026-02-27
**Status:** Draft - Final

---

## Table of Contents

1. [Overview](#1-overview)
2. [User Stories](#2-user-stories)
3. [Functional Requirements](#3-functional-requirements)
4. [MCP Tools Specification](#4-mcp-tools-specification)
5. [Claude Code Skill Specification](#5-claude-code-skill-specification)
6. [Non-Functional Requirements](#6-non-functional-requirements)
7. [Out of Scope for v1](#7-out-of-scope-for-v1)

---

## 1. Overview

### What This Is

`zk-mcp` is a FastMCP server that exposes a `zk`-managed note vault to Claude Code as a set of structured tools. It turns Claude into the primary interface for a personal second brain — capable of reading, writing, searching, linking, and synthesizing notes across the full vault.

This is not a query layer. It is full read/write access, designed so that the user rarely needs to open a text editor or run `zk` commands manually.

### Philosophy

**The AI is the interface.** Instead of switching between terminal, editor, and note browser, the user stays in one place — a Claude Code session — and converses. Claude reads the vault, writes to it, and reasons across it.

**Frictionless capture, deliberate structure.** The inbox is the entry point for anything the user doesn't want to think about. The MCP makes capture a single sentence. Processing (linking, filing, tagging) is a separate, structured act that Claude facilitates.

**Propose, then act.** Destructive or structural changes (moving, deleting, bulk editing) follow a confirm flow. Claude proposes what it intends to do and waits. The user can pre-confirm ("just do it") for trusted sessions.

**zk is the engine.** All note storage and wikilink/tag graph operations delegate to the `zk` CLI. The MCP server does not reimplement zk — it wraps it. This keeps the vault portable and the implementation simple.

**Semantic retrieval over keyword search.** A LanceDB vector index enables hybrid search — semantic similarity plus keyword matching in a single query. This means "what do I know about container orchestration?" finds notes that mention "k8s" and "pods" even without those exact words in the query. The index lives at `.zk/vectors/` inside the vault and is updated automatically on every write operation.

**GitLab is the source of truth for issues.** The vault is a window into GitLab — not a replacement. Issues are created, updated, and closed via the MCP tools which delegate to `glab` CLI. Notes can reference issues; issues can be pulled into notes. The vault never duplicates GitLab state, it enriches it with context.

### Vault Structure

```
~/notes/
├── daily/       # daily notes, connective tissue
├── inbox.md     # frictionless capture, process weekly
├── projects/    # active work with a finish line
├── areas/       # ongoing responsibilities
├── people/      # 1:1s, context, relationships
├── ideas/       # not ready to be a project yet
├── learning/    # active study
├── resources/   # settled reference, distilled knowledge
├── raw/         # dump zone: PDFs, URLs, raw docs for ingestion
└── archives/    # completed/dead things
```

### Stack

| Component | Choice |
|---|---|
| Language | Python 3.12+ |
| Package manager | uv |
| MCP framework | FastMCP |
| Note engine | zk CLI |
| Note format | Markdown with minimal YAML frontmatter (title + date) and inline #tags |
| Link format | Wikilinks (`[[title]]`) |
| Vector store | LanceDB (local, Apache Arrow format) |
| Embeddings | sentence-transformers `nomic-embed-text-v1.5` (local, no API) |
| Search mode | Hybrid (vector + keyword via LanceDB) |
| GitLab integration | glab CLI |
| File watching | watchdog (Python) |
| HTTP client | httpx |
| PDF extraction | pymupdf4llm |
| Web extraction | trafilatura (with focused crawler) |

---

## 2. User Stories

### Daily Notes

**US-01:** As a user, I want Claude to create or open today's daily note so that I have a consistent place to capture the day's context without thinking about file naming.

**US-02:** As a user, I want Claude to draft a daily note based on my current projects and recent notes so that I start each day with relevant context already populated.

**US-03:** As a user, I want to append quick thoughts to today's daily note conversationally so that I don't have to open an editor mid-session.

### Inbox Capture

**US-04:** As a user, I want to say "capture: [thought]" and have it appended to inbox.md immediately so that capture is zero friction.

**US-05:** As a user, I want inbox entries to be timestamped so that I know when I captured something.

**US-06:** As a user, I want Claude to confirm what it wrote to the inbox after capture so that I know it was recorded correctly.

### Inbox Processing

**US-07:** As a user, I want Claude to walk me through my inbox items one by one during a weekly review, proposing a destination (link, file, tag, or discard) for each, so that I process it systematically.

**US-08:** As a user, I want to pre-confirm the review flow ("just do it") so that Claude processes the inbox without pausing at each step when I trust it.

**US-09:** As a user, I want Claude to create new notes for inbox items that deserve their own entry, and link them appropriately, so that the inbox stays clean.

### Creating Notes

**US-10:** As a user, I want to create a note in any folder by describing it conversationally so that I don't have to specify paths or templates manually.

**US-11:** As a user, I want to choose between a scaffold (frontmatter + section headers only) and a full draft (AI-written content) so that I can decide how much Claude writes versus what I write.

**US-12:** As a user, I want new notes to have consistent frontmatter (title, date, tags) so that the graph stays queryable.

### People Notes

**US-13:** As a user, I want to open or create a person note by name so that I have a persistent place for context on that person.

**US-14:** As a user, I want to append a dated 1:1 entry to a person note conversationally so that I capture meeting notes without creating a new file each time.

**US-15:** As a user, I want to ask "what did I discuss with [name] last month?" and get a summary drawn from their note so that I can quickly recall context before a meeting.

### Searching and Retrieving Notes

**US-16:** As a user, I want to search notes by keyword, tag, folder, or date so that I can find what I need without knowing the exact filename.

**US-17:** As a user, I want to ask cross-cutting questions ("what projects am I working on?", "what ideas haven't moved in 3 months?") and get synthesized answers so that I can reason across my vault without manually reviewing files.

**US-18:** As a user, I want to retrieve the full content of a note by title or path so that Claude can read and reason about it.

### Navigation

**US-19:** As a user, I want to see what notes link to a given note (backlinks) so that I can understand the context and connections around a topic.

**US-20:** As a user, I want to see what notes a given note links to so that I can navigate forward through the graph.

**US-21:** As a user, I want to list all notes with a given tag so that I can gather everything related to a topic.

### Weekly Review and Synthesis

**US-22:** As a user, I want Claude to generate a weekly review summary across recent daily notes and project notes so that I can reflect on the week without reading every file.

**US-23:** As a user, I want Claude to surface notes that haven't been touched in a long time so that I can decide whether to archive, develop, or delete them.

**US-24:** As a user, I want the weekly review to end with proposed actions (inbox items to process, notes to archive, links to make) so that the review is actionable.

### Tagging and Linking

**US-25:** As a user, I want to add or change tags on an existing note so that I can improve the graph without rewriting the note.

**US-26:** As a user, I want Claude to suggest relevant wikilinks to insert into a note based on what exists in my vault so that the graph stays connected.

**US-27:** As a user, I want to insert a wikilink into the current note by asking Claude so that I don't have to look up exact titles.

### Moving and Archiving

**US-28:** As a user, I want to move a note from one folder to another (e.g., ideas/ to projects/) with confirmation so that promoting or demoting notes is safe.

**US-29:** As a user, I want to "delete" a note by moving it to archives/ rather than permanently removing it so that nothing is ever silently destroyed.

### NotebookLM-Style Synthesis

**US-30:** As a user, I want Claude to synthesize a briefing document from multiple related notes (person note + linked projects + recent daily mentions) before a meeting so that I walk in fully prepared.

**US-31:** As a user, I want Claude to generate an FAQ from a research or learning note so that I can quickly review key concepts in Q&A format.

**US-32:** As a user, I want Claude to perform a gap analysis on a topic ("what am I missing in my understanding of kubernetes?") by reading my notes and identifying what's absent so that I know what to learn next.

**US-33:** As a user, I want Claude to generate a narrative summary across multiple notes on a topic — similar to NotebookLM's podcast summary — so that I can absorb a topic without reading every note.

**US-34:** As a user, I want Claude to generate study questions from a learning note so that I can test my own understanding.

**US-35:** As a user, I want to ask "what's the common thread across these notes?" and get a synthesized answer so that I can surface patterns I haven't consciously noticed.

### Meeting Preparation

**US-36:** As a user, I want to run `/zk prep [person or project]` and get a bundled context brief — relevant notes, open action items, recent history — so that I can prepare for any meeting in seconds.

### Stale Note Management

**US-37:** As a user, I want Claude to surface notes in ideas/ and projects/ that haven't been touched in more than 30 days so that I can decide whether to develop, promote, or archive them.

**US-38:** As a user, I want to be notified during a weekly review if any project notes are stale so that nothing falls through the cracks.

### Cross-Note Search

**US-39:** As a user, I want to search across people/ notes for a topic (e.g., "which team members have I discussed kubernetes with?") so that I can find distributed context quickly.

### Semantic Search and RAG

**US-40:** As a user, I want to ask natural language questions like "what do I know about zero trust networking?" and get semantically relevant notes back even if they don't contain those exact words, so that retrieval is intelligent not literal.

**US-41:** As a user, I want synthesis features (briefings, gap analysis, weekly review) to use semantic retrieval so that Claude finds all relevant notes, not just ones matching exact keywords.

**US-42:** As a user, I want the vector index to update automatically when I create or append to a note so that new content is immediately searchable.

**US-43:** As a user, I want to rebuild the full vector index on demand so that I can recover from index corruption or resync after manual vault edits.

### GitLab Integration

**US-44:** As a user, I want to create a GitLab issue from a task or action item in my notes so that actionable work lands in the backlog without leaving my terminal.

**US-45:** As a user, I want to pull a GitLab issue into my vault as a note or task reference so that I have context alongside the issue.

**US-46:** As a user, I want to close or update a GitLab issue from my terminal while working in my notes so that GitLab stays current as I work.

**US-47:** As a user, I want Claude to extract action items from a 1:1 or meeting note and offer to create GitLab issues for each so that nothing from a meeting falls through the cracks.

**US-48:** As a user, I want to see my open GitLab issues alongside vault todos in `/zk tasks` so that I have one unified view of what I need to do.

### Task Management

**US-49:** As a user, I want Claude to find all open tasks (`- [ ]`) across my active projects and daily notes so that I have a consolidated view of open work.

**US-50:** As a user, I want to mark a task complete from my Claude session so that my notes stay current without opening a file.

### Note Gardening

**US-51:** As a user, I want to extract a large section of an existing note into its own new note and have a wikilink left in its place so that my notes stay atomic and focused.

**US-52:** As a user, I want to replace a specific section of a note with new content so that I can refine and reorganize notes over time without appending endlessly.

**US-53:** As a user, I want to rename a note and have all wikilinks across the vault updated automatically so that I can evolve note titles without breaking the graph.

### Vault Health

**US-54:** As a user, I want to find orphaned notes (no incoming or outgoing links) and dead wikilinks so that the graph stays healthy.

**US-55:** As a user, I want to run a vault health check during weekly review so that graph hygiene is a regular habit not a special operation.

---

## 3. Functional Requirements

### 3.1 Read Operations

| ID | Requirement |
|---|---|
| R-RD-01 | The server must read any note by absolute path or by title search. |
| R-RD-02 | The server must return note content plus parsed frontmatter (title, date, tags) as structured data. |
| R-RD-03 | The server must list notes in a given directory, optionally filtered by tag, date range, or recency. |
| R-RD-04 | The server must return a list of all tags in the vault with counts. |
| R-RD-05 | The server must support reading the inbox.md file as a special case. |

### 3.2 Write Operations

| ID | Requirement |
|---|---|
| R-WR-01 | The server must create a new note with specified directory, title, tags, and body content. |
| R-WR-02 | The server must scaffold a note (frontmatter + section headers) without generating body content. |
| R-WR-03 | The server must append content to an existing note with an optional section header. |
| R-WR-04 | The server must update frontmatter fields (e.g., tags) on an existing note without altering body content. |
| R-WR-05 | The server must append a timestamped entry to the inbox. |
| R-WR-06 | All write operations must return the resulting note path and a diff-like summary of what changed. |
| R-WR-07 | Write operations that modify existing content must not silently overwrite — append is always safe; overwrite requires explicit intent. |

### 3.3 Search and Query

| ID | Requirement |
|---|---|
| R-SQ-01 | The server must support full-text search via `zk list --match`. |
| R-SQ-02 | The server must support filtering by tag, directory, and date range in list/search operations. |
| R-SQ-03 | The server must return search results as structured list (path, title, date, tags, excerpt). |
| R-SQ-04 | The server must support querying for recently modified notes (last N days). |
| R-SQ-05 | Search must delegate to `zk` for index consistency — not custom grep — so that the zk note graph stays authoritative. |

### 3.4 Navigation

| ID | Requirement |
|---|---|
| R-NV-01 | The server must return all backlinks (notes that link to a given note) via `zk list --linked-by`. |
| R-NV-02 | The server must return all forward links (notes that a given note links to) via `zk list --link-to`. |
| R-NV-03 | The server must list all notes sharing a given tag. |
| R-NV-04 | Link and backlink results must include note title, path, and excerpt. |

### 3.5 Inbox Management

| ID | Requirement |
|---|---|
| R-IN-01 | The server must append a captured item to inbox.md with an ISO timestamp. Format: `- YYYY-MM-DD HH:MM thought here` (plain timestamped list item, no checkbox). |
| R-IN-02 | The server must read and return all current inbox items as a structured list (index, timestamp, text). |
| R-IN-03 | The server must support removing a specific inbox item by index after it has been processed. |
| R-IN-04 | The server must support clearing the entire inbox after a confirmed review. |

### 3.6 Synthesis and Summarization (AI Layer)

These are not server-side functions — they are Claude's responsibility, using data returned by MCP tools.

| ID | Requirement |
|---|---|
| R-SY-01 | Claude must be able to synthesize a weekly review by reading recent daily notes and project notes via multiple tool calls. |
| R-SY-02 | Claude must be able to answer cross-cutting questions ("what am I working on?") by querying list_notes across relevant folders and summarizing. |
| R-SY-03 | Claude must be able to suggest links for a note by comparing its content against vault search results. |
| R-SY-04 | The MCP server does not perform AI synthesis — it returns raw note data for Claude to reason over. |

### 3.7 Confirmation Flow

| ID | Requirement |
|---|---|
| R-CF-01 | Any operation that moves, renames, deletes (archives), replaces section content, extracts sections, or closes a GitLab issue must be preceded by a Claude-generated proposal describing the intended actions. Tools requiring confirmation: `move_note`, `rename_note`, `delete_note`, `replace_section`, `extract_section`, `clear_inbox_item`, `close_issue`. |
| R-CF-02 | Claude must wait for explicit user confirmation before executing proposed destructive or structural operations. |
| R-CF-03 | The user may pre-confirm a session by saying "just do it" or "pre-confirm all" — Claude must honor this for the remainder of the session. |
| R-CF-04 | Non-destructive writes (append, capture) do not require confirmation. |
| R-CF-05 | Confirmation state is session-scoped and not persisted. |
| R-CF-06 | `reindex_vault` requires explicit confirmation via the `confirm=true` parameter. |

### 3.8 NotebookLM-Style Synthesis (AI Layer)

| ID | Requirement |
|---|---|
| R-NB-01 | Claude must support multi-note briefing by using `search_notes` with semantic retrieval to find all notes related to a given person or project, then reading them via `get_note`. |
| R-NB-02 | Claude must support FAQ generation from a single note on request. |
| R-NB-03 | Claude must support gap analysis by using `search_notes` to retrieve all notes on a topic semantically, reading them, and reasoning about what concepts are absent. |
| R-NB-04 | Claude must support narrative synthesis across up to 20 notes retrieved via semantic `search_notes` + `get_note`. |
| R-NB-05 | Claude must support study question generation from learning/ notes. |
| R-NB-06 | All synthesis operations are Claude-layer — they require no new MCP tools beyond `get_note`, `list_notes`, `search_notes`, and `get_backlinks`. |

### 3.9 Wikilink Consistency

| ID | Requirement |
|---|---|
| R-WL-01 | When a note is moved via `move_note`, all wikilinks in other notes that reference the old path or title must be updated to reflect the new location. |
| R-WL-02 | The server must expose a `find_references` tool (or `move_note` must internally handle this) to locate all notes containing a wikilink to the moved note. |
| R-WL-03 | Wikilink updates on move are part of the `move_note` operation — they are not optional and do not require separate confirmation beyond the move confirmation itself. |
| R-WL-04 | After a move, the server must return a list of notes that were updated as part of the move operation. |

### 3.10 Vector Index and Hybrid Search

| ID | Requirement |
|---|---|
| R-VS-01 | The server must maintain a LanceDB vector index at `.zk/vectors/` within the vault root. |
| R-VS-02 | Notes are chunked by section (split on `##` headers) before embedding — each chunk stored with metadata: `path`, `title`, `tags`, `directory`, `modified_date`, `chunk_index`. |
| R-VS-03 | Embeddings are generated using `sentence-transformers` with model `nomic-embed-text-v1.5`, running locally with no external API dependency. nomic-embed-text-v1.5 supports 8192 token context window, purpose-built for RAG and long document retrieval. Used via sentence-transformers ONNX backend (sentence-transformers[onnx]) to avoid PyTorch dependency. |
| R-VS-04 | The vector index must be updated incrementally on every write operation: `create_note` and `append_to_note` re-embed the affected note; `move_note` and `rename_note` update path/title metadata without re-embedding; `update_tags` updates tag metadata without re-embedding; `delete_note` removes the note from the active index (archived notes are excluded from search by default); `replace_section` re-embeds the affected note; `ingest` chunks and embeds the ingested document content alongside regular notes, tagged with `source_type: ingested` metadata for filtering. |
| R-VS-05 | A full reindex operation must be available via the `reindex_vault` tool and the `/zk reindex` skill. |
| R-VS-06 | `search_notes` must use LanceDB hybrid search (vector + keyword) as its primary retrieval mechanism, replacing the zk `--match` keyword-only approach. |
| R-VS-07 | `search_notes` must support metadata filtering (directory, tags, date range) applied at the LanceDB query level before vector search for efficiency. |
| R-VS-08 | Search results must include a relevance score so Claude can decide how many results are actually useful vs just returned. |
| R-VS-09 | The vector index must not be required for the server to start — if `.zk/vectors/` does not exist, read/write operations work normally and search falls back to zk keyword search with a warning. |

### 3.11 Task Management

| ID | Requirement |
|---|---|
| R-TM-01 | The server must support scanning specified directories for unchecked markdown task items (`- [ ]`). |
| R-TM-02 | Task results must include the source note path, line number, and task text. |
| R-TM-03 | The server must support marking a specific task as complete by path and line number, changing `- [ ]` to `- [x]`. |
| R-TM-04 | Task scanning must support filtering by directory (e.g., only `projects/` and `daily/`). |

### 3.12 Note Editing and Gardening

| ID | Requirement |
|---|---|
| R-ED-01 | The server must support replacing the content of a named section (identified by its `##` header) in an existing note without touching any other sections. |
| R-ED-02 | `replace_section` must return the previous section content and new section content for confirmation display. |
| R-ED-03 | If the target section header does not exist in the note, `replace_section` returns a `SECTION_NOT_FOUND` error — it does not append. |
| R-ED-04 | The server must support renaming a note: updating its title, renaming the file to the new slug, and updating all wikilinks across the vault that reference the old title. |
| R-ED-05 | `rename_note` must return `{ old_path, new_path, updated_references }` — same pattern as `move_note`. |
| R-ED-06 | The server must support extracting a named section from a note into a new note: the section content becomes the new note's body, and the original section is replaced with a wikilink to the new note. |
| R-ED-07 | `replace_section` requires an exact `##` header match. If the target section uses `###` headers or the note has no headers, the tool returns `SECTION_NOT_FOUND`. Claude's expected handling: offer to use `append_to_note` to add the appropriate header first, then retry `replace_section`. |

### 3.13 GitLab Integration

| ID | Requirement |
|---|---|
| R-GL-01 | The server must support creating a GitLab issue via `glab` CLI from a title and description. |
| R-GL-02 | The server must support listing open GitLab issues for a given project, optionally filtered by label or assignee. |
| R-GL-03 | The server must support closing a GitLab issue by issue number. |
| R-GL-04 | The server must support pulling a GitLab issue into the vault as a structured note reference (title, URL, description, labels, status). |
| R-GL-05 | GitLab is the source of truth — the MCP server never stores issue state locally. All reads hit `glab` at call time. |
| R-GL-06 | GitLab project context (project path, default labels) is configured via environment variable `GITLAB_PROJECT` and optional `GITLAB_DEFAULT_LABELS`. |

### 3.14 File Watching and Resilience

| ID | Requirement |
|---|---|
| R-FW-01 | The server must run a `watchdog` file watcher on the vault root that detects file creation, modification, and deletion events. |
| R-FW-02 | On file creation or modification detected by the watcher, the affected note must be incrementally re-embedded in LanceDB within 5 seconds. |
| R-FW-03 | On file deletion detected by the watcher, the corresponding LanceDB entry must be removed. |
| R-FW-04 | The file watcher covers all vault directories including `raw/` for ingestion triggers. |
| R-FW-05 | The watcher must debounce rapid successive changes to the same file (e.g., from an editor saving frequently) — wait 2 seconds of inactivity before re-indexing. |
| R-FW-06 | Manual vault edits (files added, edited, or deleted outside the MCP server) are handled automatically by the watcher — `/zk reindex` remains available for full recovery. |
| R-FW-07 | The watcher must ignore `.zk/`, `.git/`, and `raw/` subdirectory binary files to avoid unnecessary re-indexing. |

### 3.15 Document and URL Ingestion

| ID | Requirement |
|---|---|
| R-IN2-01 | The server must support ingesting a local file (PDF, markdown, plain text) from the `raw/` directory into the knowledge base. |
| R-IN2-02 | The server must support ingesting a URL by fetching and extracting its readable content. |
| R-IN2-03 | Ingestion creates a new note in `resources/` with: the source title (or URL), a Claude-generated summary, key points, and the raw extracted text in a collapsed section. |
| R-IN2-04 | Ingested content is chunked and embedded into LanceDB, making it fully searchable alongside regular notes. |
| R-IN2-05 | PDF text extraction uses `pymupdf4llm`. URL content extraction uses `trafilatura` to strip navigation/ads and extract article body. trafilatura handles URL fetch + content extraction. Supports focused crawling (follow relevant links) via trafilatura.spider.focused_crawler. |
| R-IN2-06 | The `raw/` directory is watched by the file watcher — dropping a PDF into `raw/` triggers automatic ingestion. |
| R-IN2-07 | Ingestion is idempotent — re-ingesting the same source (matched by filename or URL) updates the existing resource note rather than creating a duplicate. |
| R-IN2-08 | After ingestion, Claude surfaces the created note and offers to link it to related existing notes via semantic search. |

---

## 4. MCP Tools Specification

All tools are exposed via FastMCP. The server runs locally and is configured in the Claude Code MCP settings pointing to the vault at `~/notes`.

### Tool Index

| Tool | Purpose |
|---|---|
| `search_notes` | Full-text and filtered search |
| `get_note` | Read a single note by path or title |
| `create_note` | Create a new note |
| `append_to_note` | Append content to an existing note |
| `update_tags` | Add or remove inline #tags on a note |
| `list_notes` | List notes by folder, tag, or recency |
| `get_backlinks` | Notes that link to a given note |
| `get_links` | Notes that a given note links to |
| `get_tags` | All tags in vault with counts |
| `capture_to_inbox` | Append an item to inbox.md |
| `get_inbox` | Read all current inbox items |
| `clear_inbox_item` | Remove a processed inbox item by index |
| `move_note` | Move note to a different folder |
| `delete_note` | Soft-delete: move to archives/ |
| `find_references` | Find all notes referencing a given title |
| `reindex_vault` | Rebuild the full LanceDB vector index from scratch |
| `rename_note` | Rename a note and update all wikilinks vault-wide |
| `replace_section` | Replace a named section in an existing note |
| `extract_section` | Extract a section into a new note, leaving a wikilink |
| `get_todos` | Find all open `- [ ]` tasks across specified directories |
| `complete_todo` | Mark a specific task as complete by path and line number |
| `create_issue` | Create a GitLab issue via glab CLI |
| `get_issues` | List open GitLab issues for the configured project |
| `close_issue` | Close a GitLab issue by number |
| `issue_to_note` | Pull a GitLab issue into the vault as a note reference |
| `ingest` | Ingest a file or URL into the knowledge base as a resource note |

---

### `search_notes`

**Description:** Full-text search across the vault using zk's index. Returns matching notes with excerpts.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes | Full-text search string |
| `directory` | string | no | Limit search to this subdirectory (e.g., `projects`) |
| `tags` | list[string] | no | Filter to notes with all listed tags |
| `since` | string | no | ISO date — only notes modified on or after this date |
| `limit` | integer | no | Max results to return. Default: 20 |

**Output:** List of objects: `{ path, title, date, tags, excerpt, relevance_score }`

**Notes:**
- Uses LanceDB hybrid search (vector + keyword) when the index is available. Falls back to `zk list --match` if index is not built.
- Metadata filters (directory, tags, since) are applied at the LanceDB query level before vector search — efficient even on large vaults.
- Results include a `relevance_score` (0.0–1.0) field in addition to path, title, date, tags, excerpt.
- A single `search_notes` call replaces the need for separate keyword and semantic search tools.

---

### `get_note`

**Description:** Read the full content and frontmatter of a single note.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | string | no | Absolute or vault-relative path to the note |
| `title` | string | no | Title to search for if path is not known |

**Output:** `{ path, title, date, tags, body, raw_frontmatter }`

**Notes:**
- Exactly one of `path` or `title` must be provided.
- If `title` matches multiple notes, returns an error listing the candidates — caller must specify by path.
- `body` is the full markdown content below the frontmatter block.

---

### `create_note`

**Description:** Create a new note in the vault. Supports both full draft and scaffold modes.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `title` | string | yes | Note title (used for filename and frontmatter) |
| `directory` | string | yes | Target subdirectory (e.g., `projects`, `people`, `ideas`) |
| `tags` | list[string] | no | Initial tags for frontmatter |
| `content` | string | no | Body content. If omitted, note is scaffolded with section headers only. |
| `template` | string | no | Named template to use (e.g., `person`, `project`, `daily`). Overrides default scaffold. |

**Output:** `{ path, title, created_at, suggested_links }`

**Notes:**
- Filename is derived from title using zk's slug logic (lowercase, hyphenated).
- If a note with the same path already exists, returns `ALREADY_EXISTS`. Claude's standard handling: read the existing note via `get_note` and offer to `append_to_note` instead.
- Frontmatter always includes `title`, `date` (today), and `tags`.
- When `content` is omitted and no `template` is specified, the scaffold is a minimal structure: frontmatter + `## Notes` section.
- When `content` is omitted and `template` is specified, delegates to `zk new` CLI to handle template variable hydration (e.g., `{{title}}`, `{{date}}`). This ensures template variables are always resolved by zk's native hydration, not reimplemented in the MCP server.
- After creating a note, the server automatically calls `search_notes` to find semantically related existing notes and returns them as `suggested_links: list[{path, title, relevance_score}]` — Claude should offer to insert wikilinks to the most relevant ones before the user starts editing.

---

### `append_to_note`

**Description:** Append content to an existing note, optionally under a new dated section header.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | string | yes | Vault-relative or absolute path to the target note |
| `content` | string | yes | Markdown content to append |
| `section_header` | string | no | If provided, inserts this as a `###` header before the content |
| `dated` | boolean | no | If true, prepends today's date as a `###` header. Default: false |

**Output:** `{ path, appended_lines, new_line_count }`

**Notes:**
- Append-only. Never modifies existing content.
- `dated` and `section_header` are mutually exclusive — if both provided, `dated` wins.
- Used for 1:1 entries, daily note additions, and inbox capture.

---

### `update_tags`

**Description:** Add or remove inline #tags from an existing note without altering any other content.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | string | yes | Path to the note |
| `add_tags` | list[string] | no | Tags to add (without # prefix) |
| `remove_tags` | list[string] | no | Tags to remove (without # prefix) |

**Output:** `{ path, previous_tags, new_tags }`

**Notes:**
- Tags are stored inline in the note body as #hashtags, not in YAML frontmatter.
- The server finds existing tags by scanning for #word patterns and edits them in place.
- At least one of `add_tags` or `remove_tags` must be provided.
- Returns the before/after tag state for confirmation display.

---

### `list_notes`

**Description:** List notes in the vault with optional filters. Does not return full content — use `get_note` for that.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `directory` | string | no | Filter to this subdirectory |
| `tags` | list[string] | no | Filter to notes with all of these tags |
| `since` | string | no | ISO date — modified on or after |
| `until` | string | no | ISO date — modified on or before |
| `recent` | integer | no | Return N most recently modified notes |
| `sort` | string | no | `modified` (default), `created`, `title` |
| `limit` | integer | no | Max results. Default: 50 |

**Output:** List of `{ path, title, date, modified, tags }`

**Notes:**
- With no filters, returns all notes sorted by modified date.
- `recent` is a convenience shorthand for `since` = N days ago with `sort=modified`.
- Does not return body content — keeps response size manageable for large vaults.

---

### `get_backlinks`

**Description:** Find all notes in the vault that contain a wikilink pointing to the given note.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | string | yes | Path to the target note |

**Output:** List of `{ path, title, excerpt }`

**Notes:**
- Delegates to `zk list --linked-by <path>`.
- Excerpt is the surrounding sentence containing the link.
- Returns empty list if no backlinks exist.

---

### `get_links`

**Description:** Find all notes that the given note links to via wikilinks.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | string | yes | Path to the source note |

**Output:** List of `{ path, title }`

**Notes:**
- Delegates to `zk list --link-to <path>`.
- Returns empty list if note has no outgoing links.
- Does not validate that linked notes exist — dead links are surfaced as-is.

---

### `get_tags`

**Description:** Return all tags used in the vault with their note counts.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `filter` | string | no | Prefix filter (e.g., `proj` returns `project`, `projects`, etc.) |

**Output:** List of `{ tag, count }` sorted by count descending.

**Notes:**
- Useful for Claude to suggest appropriate tags when creating or updating notes.
- No parameters required — can be called with no arguments to get the full tag list.

---

### `capture_to_inbox`

**Description:** Append a single item to inbox.md with an ISO timestamp.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `text` | string | yes | The content to capture |

**Output:** `{ appended_line, inbox_item_count }`

**Notes:**
- Format: `- YYYY-MM-DD HH:MM <text>` appended as a list item.
- This is the only write operation that does not require confirmation — it is always safe.
- Returns the current inbox item count so Claude can surface it ("you have 12 items in your inbox").

---

### `get_inbox`

**Description:** Read all current inbox items as a structured list.

| Parameter | Type | Required | Description |
|---|---|---|---|
| _(none)_ | — | — | No parameters |

**Output:** List of `{ index, timestamp, text }`, plus `{ total_count }`

**Notes:**
- Index is 0-based and matches position in the file.
- Used at the start of a weekly review to enumerate items for processing.

---

### `clear_inbox_item`

**Description:** Remove a specific item from inbox.md by index after it has been processed.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `index` | integer | yes | 0-based index of the item to remove |

**Output:** `{ removed_text, remaining_count }`

**Notes:**
- This is a destructive operation on inbox content and requires session-level confirmation unless pre-confirmed.
- Index is validated against current inbox state — stale indexes return an error, not a silent wrong removal.
- Use `get_inbox` before `clear_inbox_item` to get current indexes.

---

### `move_note`

**Description:** Move a note from its current location to a different directory.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | string | yes | Current path of the note |
| `destination_directory` | string | yes | Target directory (e.g., `projects`, `archives`) |

**Output:** `{ old_path, new_path, updated_references }`

**Notes:**
- Requires confirmation unless pre-confirmed.
- Does not rename the file — only moves it to the new directory.
- When a note is moved, the server automatically scans the vault for all wikilinks referencing the old title or path and updates them to the new title. The response includes `updated_references: list[path]` — all notes that had links updated.
- `updated_references` — list of note paths where wikilinks were updated.
- Returns an error if destination directory does not exist.

---

### `delete_note`

**Description:** Soft-delete a note by moving it to archives/. Nothing is permanently removed.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | string | yes | Path to the note to archive |
| `reason` | string | no | Optional annotation appended to the note's frontmatter before archiving |

**Output:** `{ old_path, archive_path }`

**Notes:**
- Requires confirmation unless pre-confirmed. Claude must state what it is archiving before calling this tool.
- Equivalent to `move_note` with `destination_directory=archives`.
- If `reason` is provided, it is written to frontmatter as `archived_reason` before the move.
- A note already in archives/ cannot be deleted again — returns an error.

---

### `find_references`

**Description:** Find all notes in the vault that contain a wikilink or text reference to a given note title.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `title` | string | yes | The note title to search for |
| `include_text_mentions` | boolean | no | If true, also returns notes that mention the title as plain text (not just wikilinks). Default: false |

**Output:** List of `{ path, title, link_type, excerpt }` where `link_type` is `wikilink` or `text_mention`.

**Notes:**
- Used internally by `move_note` to find links to update.
- Also useful standalone: "what notes mention bradley?" returns both `[[bradley]]` wikilinks and plain text mentions if `include_text_mentions=true`.

---

### `reindex_vault`

**Description:** Rebuild the full LanceDB vector index by re-embedding all notes in the vault. Use after manual vault edits or index corruption.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `confirm` | boolean | yes | Must be explicitly true — prevents accidental reindex on large vaults |

**Output:** `{ notes_indexed, chunks_created, duration_seconds }`

**Notes:**
- Reindexing is synchronous and may take 10–60 seconds depending on vault size.
- Existing index is replaced atomically — the old index remains usable until the new one is ready.
- Embeddings use `nomic-embed-text-v1.5` locally — no API calls, no cost.
- Called automatically on first run if no index exists.

---

### `rename_note`

**Description:** Rename a note — updates the title, renames the file to the new slug, and updates all wikilinks across the vault.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | string | yes | Current path of the note |
| `new_title` | string | yes | New title for the note |

**Output:** `{ old_path, new_path, old_title, new_title, updated_references }`

**Notes:**
- Requires confirmation unless pre-confirmed.
- New filename is derived from `new_title` using zk slug logic.
- Uses the shared wikilink-update utility (same as `move_note`) to scan and rewrite all references.
- Returns error if a note with the new slug already exists.

---

### `replace_section`

**Description:** Replace the content of a named section in an existing note. Does not touch any other section.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | string | yes | Path to the note |
| `section_header` | string | yes | Exact text of the `##` header identifying the target section (without `##`) |
| `new_content` | string | yes | New markdown content to replace the section body |

**Output:** `{ path, section_header, previous_content, new_content }`

**Notes:**
- Replaces content between the target `##` header and the next `##` header (or end of file).
- Returns `SECTION_NOT_FOUND` if the header does not exist — does not append.
- Returns both previous and new content so Claude can show the user what changed.
- Re-embeds the note in LanceDB after replacement.

---

### `extract_section`

**Description:** Extract a named section from an existing note into a new standalone note, leaving a wikilink in its place.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | string | yes | Path to the source note |
| `section_header` | string | yes | Header of the section to extract |
| `new_title` | string | yes | Title for the new note |
| `destination_directory` | string | yes | Directory for the new note |

**Output:** `{ source_path, new_note_path, new_note_title, replaced_with_link }`

**Notes:**
- Requires confirmation unless pre-confirmed.
- The section content (minus the header) becomes the body of the new note.
- The original section in the source note is replaced with: `See [[new_title]]`
- Calls `create_note` internally, then `replace_section`.
- Both source and new note are re-indexed in LanceDB.

---

### `get_todos`

**Description:** Find all open markdown tasks (`- [ ]`) across specified directories.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `directories` | list[string] | no | Directories to scan. Default: `["projects", "daily", "areas"]` |
| `since` | string | no | Only scan notes modified since this ISO date |

**Output:** List of `{ path, title, line_number, task_text }`, plus `{ total_count }`

**Notes:**
- Does not use LanceDB — scans files directly for `- [ ]` pattern.
- Results are grouped by source note in the output.
- Used by `/zk tasks` to build a unified task view.

---

### `complete_todo`

**Description:** Mark a specific open task as complete by changing `- [ ]` to `- [x]`.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | string | yes | Path to the note containing the task |
| `line_number` | integer | yes | Line number of the task (from `get_todos` output) |
| `task_text` | string | yes | Substring of the task text for validation and fuzzy fallback |

**Output:** `{ path, line_number, task_text, status: "completed" }`

**Notes:**
- Validates that the specified line still contains `- [ ]` before modifying.
- If the line number is stale (note was edited between `get_todos` and `complete_todo`), the tool searches ±5 lines for a task matching `task_text` as a substring and uses that line instead.
- If neither the line number nor a nearby text match is found, returns `TASK_NOT_FOUND` — never silently completes the wrong task.
- Does not require confirmation — completing a task is always safe.
- `task_text` is required (not optional) to enable resilient matching.

---

### `create_issue`

**Description:** Create a new GitLab issue via `glab` CLI.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `title` | string | yes | Issue title |
| `description` | string | no | Issue body / description |
| `labels` | list[string] | no | Labels to apply. Falls back to `GITLAB_DEFAULT_LABELS` if set. |
| `assignee` | string | no | GitLab username to assign |
| `note_path` | string | no | If provided, appends the issue URL as a reference to this note |

**Output:** `{ issue_number, url, title, labels }`

**Notes:**
- Delegates entirely to `glab issue create`. GitLab is source of truth.
- If `note_path` is provided, the issue URL is appended to that note as `- GitLab: [#N title](url)`.
- Requires `GITLAB_PROJECT` env var to be set.

---

### `get_issues`

**Description:** List open GitLab issues for the configured project.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `labels` | list[string] | no | Filter by labels |
| `assignee` | string | no | Filter by assignee username |
| `limit` | integer | no | Max results. Default: 20 |

**Output:** List of `{ issue_number, title, url, labels, assignee, created_at }`

**Notes:**
- Delegates to `glab issue list`. Results are live from GitLab — not cached.
- Used by `/zk tasks` to surface GitLab issues alongside vault todos.

---

### `close_issue`

**Description:** Close a GitLab issue by number.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `issue_number` | integer | yes | GitLab issue number |
| `comment` | string | no | Optional closing comment |

**Output:** `{ issue_number, url, status: "closed" }`

**Notes:**
- Requires confirmation unless pre-confirmed.
- Delegates to `glab issue close`.

---

### `issue_to_note`

**Description:** Pull a GitLab issue into the vault as a structured note reference.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `issue_number` | integer | yes | GitLab issue number to pull |
| `destination_directory` | string | no | Where to create the note. Default: `projects` |

**Output:** `{ note_path, issue_number, title }`

**Notes:**
- Creates a new note with the issue title, URL, description, labels, and status as the body.
- Note is a snapshot — it is not kept in sync with GitLab. Use `get_issues` for live state.
- Does not duplicate issues that already have a note (checks for existing note with matching issue URL).

---

### `ingest`

**Description:** Ingest a local file (PDF, markdown, text) or URL into the vault knowledge base. Creates a structured resource note and embeds the content into LanceDB.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `source` | string | yes | File path (relative to vault root, typically `raw/filename.pdf`) or full URL |
| `title` | string | no | Override title for the resource note. If omitted, derived from document title or URL. |
| `tags` | list[string] | no | Tags to apply to the created resource note |
| `summary_style` | string | no | `brief` (3-5 bullets) or `detailed` (full summary with key points). Default: `brief` |
| `depth` | integer | no | Link following depth. 0 = this URL only (default). 1 = follow relevant links one level deep via trafilatura focused crawler. Only applies to URL sources. |

**Output:** `{ note_path, title, source, chunks_indexed, suggested_links }`

**Notes:**
- For PDFs: extracts text via `pymupdf4llm` as clean Markdown (headers, bold, lists preserved), ideal for chunking. If extracted text is empty or very short (scanned PDF), the tool returns a clear error: "This PDF appears to be scanned. OCR is not supported — consider copy-pasting the text manually."
- For URLs: fetches content via `trafilatura`, extracts article body, ignores nav/ads. trafilatura handles URL fetch + content extraction. Supports focused crawling (follow relevant links) via trafilatura.spider.focused_crawler.
- For markdown/text: reads directly, chunks by `##` header like regular notes.
- Creates note in `resources/` with sections: `## Summary`, `## Key Points`, `## Source`, `## Raw Content` (collapsed with `<details>` tag).
- `suggested_links` returns top 5 semantically related existing notes so Claude can offer wikilinks immediately after ingestion.
- Idempotent: if a resource note with the same source already exists, updates it rather than creating a duplicate.
- Dropping a file into `raw/` triggers this automatically via the file watcher — Claude announces the ingestion result in the active session if one exists.
- When `depth=1`, uses trafilatura's focused_crawler to discover and ingest topically related URLs from the seed page. Each discovered URL is ingested as a separate resource note. Returns `{ ingested_sources: list[{url, note_path}] }` in addition to the primary note.

---

## 5. Claude Code Skill Specification

The `/zk` skill is a Claude Code slash command that provides structured shortcuts over the MCP tools. It is defined as a `.claude/commands/zk.md` skill file in the vault or user config.

The skill is invoked as `/zk [subcommand] [args]` from any Claude Code session with the MCP configured.

---

### `/zk daily`

**Purpose:** Open or create today's daily note.

**Behavior:**
1. Calls `list_notes` filtering `daily/` for today's date.
2. If found, calls `get_note` and displays the content.
3. If not found, calls `create_note` with `directory=daily`, title as `YYYY-MM-DD`, and the `daily` template.
4. Displays the note and offers to draft or append.

**No additional arguments.**

---

### `/zk capture [text]`

**Purpose:** Instantly append a thought to inbox.md.

**Behavior:**
1. If `[text]` is provided inline, calls `capture_to_inbox` immediately.
2. If no text is provided, prompts: "What do you want to capture?"
3. Confirms: "Captured: [text]. Inbox now has N items."

**No confirmation required.**

---

### `/zk person [name]`

**Purpose:** Open or create a person note.

**Behavior:**
1. Calls `search_notes` with `query=[name]`, `directory=people`.
2. If a match is found with high confidence, calls `get_note` and displays it.
3. If ambiguous, lists candidates and asks the user to choose.
4. If no match, offers to create a new person note using the `person` template.

**Args:** `[name]` — full or partial name.

---

### `/zk review`

**Purpose:** Weekly inbox review — walk through inbox items with propose+confirm flow.

**Behavior:**
0. If pre-confirm mode is requested by user saying 'just do it' or 'pre-confirm all', Claude sets session pre-confirm flag and proceeds without per-item pauses.
1. Calls `get_inbox` and announces the count.
2. For each item, Claude proposes an action: create a note, link to an existing note, tag it and file it, or discard.
3. Waits for user confirmation per item (or proceeds without if pre-confirmed).
4. Executes the action: calls `create_note`, `append_to_note`, or `clear_inbox_item` as appropriate.
5. At the end, summarizes what was done: N items processed, N notes created, N discarded.

**Pre-confirm mode:** User says "pre-confirm" before or at start — Claude processes all items without per-item pause.

**Note:** The skill works ad-hoc at any time, not only weekly. The name reflects the most common use case.

---

### `/zk find [query]`

**Purpose:** Search notes and display results conversationally.

**Behavior:**
1. Calls `search_notes` with `query=[query]`.
2. Displays results as a numbered list with title, folder, date, and excerpt.
3. Offers: "Want me to open any of these?"
4. If user selects one, calls `get_note` and displays it.

**Args:** `[query]` — free-text search string. May include `tag:[tag]` or `in:[folder]` prefixes (Claude parses these and passes structured params to `search_notes`).

---

### `/zk link [query]`

**Purpose:** Find a note to link to and insert a wikilink.

**Behavior:**
1. Calls `search_notes` with the query.
2. Presents top matches with titles.
3. User selects one — Claude outputs the wikilink: `[[title]]`.
4. Claude pastes or suggests where to insert it in the current context.

**Args:** `[query]` — what the user is trying to link to.

---

### `/zk project [name]`

**Purpose:** Open or create a project note.

**Behavior:** Same pattern as `/zk person` but searches `projects/` and uses the `project` template for new notes.

---

### `/zk area [name]`

**Purpose:** Open or create an area note.

**Behavior:** Same pattern as `/zk person` but searches `areas/` and uses the `area` template.

---

### `/zk idea [title]`

**Purpose:** Quickly capture an idea as a note in ideas/.

**Behavior:**
1. If `[title]` is provided, creates a note immediately in `ideas/` with scaffold mode.
2. Offers to add more content or tags.
3. Offers to link it to related notes.

---

### `/zk archive [query]`

**Purpose:** Find a note and soft-delete it to archives/.

**Behavior:**
1. Searches for the note.
2. Proposes the archive action with what will be moved.
3. Waits for confirmation.
4. Calls `delete_note`.

---

### `/zk weekly`

**Purpose:** Generate a weekly review summary across the past 7 days.

**Behavior:**
1. Calls `list_notes` on `daily/` with `since=7 days ago`.
2. Calls `get_note` for each daily note.
3. Calls `list_notes` on `projects/` for recently modified notes.
4. Claude synthesizes a narrative summary: what happened, what's in motion, what's stale.
5. Proposes follow-up actions (items to process, notes to promote, things to archive).
6. Calls `/zk health` as the final step and appends any critical findings to the weekly summary.

---

### `/zk prep [name]`

**Purpose:** Generate a meeting prep brief for a person or project.

**Behavior:**
1. Searches `people/` or `projects/` for the name.
2. Calls `get_note` on the matched note.
3. Calls `get_backlinks` to find all notes that reference it.
4. Calls `list_notes` filtering for recent daily notes that mention the name via `search_notes`.
5. Claude synthesizes a structured brief: background, recent history, open action items, relevant projects or people linked.
6. Displays the brief and offers to save it as a new note.

**Args:** `[name]` — person name or project title.

---

### `/zk synthesize [topic]`

**Purpose:** Generate a NotebookLM-style narrative synthesis across all notes related to a topic.

**Behavior:**
1. Calls `search_notes` with the topic query, no directory filter.
2. Calls `get_note` for top N results (up to 10).
3. Claude synthesizes a narrative: what the notes collectively say, key themes, contradictions, open questions.
4. Offers to save the synthesis as a new note in `resources/`.

**Args:** `[topic]` — free-text topic to synthesize.

---

### `/zk stale`

**Purpose:** Surface notes that haven't been updated in 30+ days.

**Behavior:**
1. Calls `list_notes` on `ideas/` and `projects/` filtering for notes not modified in 30+ days.
2. Presents the list grouped by folder.
3. For each, offers: develop (open and append), promote (move to a different folder), or archive.
4. Follows normal confirm flow.

---

### `/zk reindex`

**Purpose:** Rebuild the vector search index.

**Behavior:**
1. Warns that this may take up to a minute.
2. Asks for confirmation.
3. Calls `reindex_vault` with `confirm=true`.
4. Reports: "Indexed N notes, M chunks created in X seconds."

**Args:** None.

---

### `/zk tasks`

**Purpose:** Unified view of all open work — vault todos + GitLab issues.

**Behavior:**
1. Calls `get_todos` across `projects/`, `daily/`, `areas/`.
2. Calls `get_issues` for the configured GitLab project.
3. Claude presents a unified list grouped by source (vault note or GitLab).
4. Offers: mark a task complete (`complete_todo`), create an issue from a task (`create_issue`), or open a note.
5. If the user asks to associate an existing GitLab issue with a note, Claude calls `get_issues` to confirm the issue exists, then uses `append_to_note` to add `- GitLab: [#N title](url)` to the note. No new tool required.

---

### `/zk rename [old] to [new]`

**Purpose:** Safely rename a note and update all wikilinks.

**Behavior:**
1. Searches for the note by title.
2. Proposes: "Rename '[old]' to '[new]' and update N wikilinks across the vault."
3. Waits for confirmation.
4. Calls `rename_note`.
5. Reports updated references.

---

### `/zk refactor [note]`

**Purpose:** Reorganize a messy or append-heavy note into a clean structure.

**Behavior:**
1. Calls `get_note` on the target note.
2. Claude reads it and proposes a reorganized structure with section headers.
3. User reviews and approves the proposed structure.
4. Claude uses `replace_section` for each section to apply the reorganization.
5. Offers to extract any sections that deserve their own note via `extract_section`.

---

### `/zk health`

**Purpose:** Vault health check — dead links, orphaned notes, stale content.

**Behavior:**
1. Calls `zk list --link-broken` via search to find dead wikilinks.
2. Calls `list_notes` and `get_backlinks` to find orphaned notes (no incoming links).
3. Calls `list_notes` on `ideas/` and `projects/` to find notes untouched for 30+ days.
4. Claude presents a health report: dead links, orphans, stale notes.
5. Offers to fix each issue: remove dead links, archive orphans, prompt on stale notes.
6. Integrated into `/zk weekly` as the final step.

---

### `/zk ingest [source]`

**Purpose:** Ingest a file or URL into the knowledge base.

**Behavior:**
1. If `[source]` is a URL, calls `ingest` with the URL directly.
2. If `[source]` is a filename, assumes it is in `raw/` and calls `ingest` with the full path.
3. Reports: "Ingested '[title]' — created `resources/[slug].md`, indexed N chunks."
4. Shows top 3 related notes from `suggested_links` and offers to add wikilinks.
5. Offers to move the source file out of `raw/` to avoid re-triggering ingestion.

**Args:** `[source]` — a URL or filename in `raw/`.

---

## 6. Non-Functional Requirements

### Performance

| ID | Requirement |
|---|---|
| NF-P-01 | Tool responses for read operations must return in under 2 seconds for vaults up to 5,000 notes. |
| NF-P-02 | The server must not load the entire vault into memory on startup. All reads are on-demand. |
| NF-P-03 | Search delegates to zk's pre-built index — no custom indexing in the MCP server. |

### Safety

| ID | Requirement |
|---|---|
| NF-S-01 | No operation permanently deletes a file. `delete_note` moves to archives/. |
| NF-S-02 | All write operations return a summary of what changed. Claude must surface this to the user. |
| NF-S-03 | Overwriting existing note content is not supported via `append_to_note`. Section-level replacement via `replace_section` is the only supported form of content modification on existing notes, and it returns the previous content for auditability. |
| NF-S-04 | `create_note` fails if a note with the same path already exists — no silent overwrite. |
| NF-S-05 | The server operates only within the configured vault root. No path traversal outside `~/notes`. |
| NF-S-06 | All file paths are validated and canonicalized before use. |

### Error Handling

| ID | Requirement |
|---|---|
| NF-E-01 | All tools return structured errors with a `code` and `message`. Never silently succeed when something went wrong. |
| NF-E-02 | Common error codes: `NOT_FOUND`, `ALREADY_EXISTS`, `AMBIGUOUS_TITLE`, `INVALID_PATH`, `ZK_ERROR`, `OUTSIDE_VAULT`, `SECTION_NOT_FOUND`, `TASK_NOT_FOUND`, `GITLAB_ERROR`, `RENAME_CONFLICT`. |
| NF-E-03 | When `zk` CLI is unavailable or returns a non-zero exit code, the server surfaces the zk error message directly. |
| NF-E-04 | Claude must translate tool errors into human-readable explanations rather than surfacing raw JSON. |

### Confirmation Flow

| ID | Requirement |
|---|---|
| NF-C-01 | Tools that require confirmation are: `move_note`, `rename_note`, `delete_note`, `replace_section`, `extract_section`, `clear_inbox_item`, `close_issue`. |
| NF-C-02 | Confirmation is enforced by Claude (not by the server). The server executes what it is called with. |
| NF-C-03 | Claude must maintain a session variable for pre-confirm state and check it before every structural operation. |
| NF-C-04 | When pre-confirmed, Claude still announces each action as it executes it — it just doesn't pause. |

### Configuration

| ID | Requirement |
|---|---|
| NF-CF-01 | Vault root is configured via an environment variable `ZK_NOTEBOOK_DIR` (same as the zk CLI). |
| NF-CF-02 | The server must respect `.zk/config.toml` for any zk-level settings (e.g., default language, date format). |
| NF-CF-03 | Templates are loaded from `.zk/templates/` within the vault. |

---

## 7. Out of Scope for v1

The following are explicitly deferred. Everything else described in this document is in scope.

| Feature | Rationale |
|---|---|
| Web UI or non-Claude interface | Purpose-built for Claude Code terminal workflow. |
| Multi-vault support | Single vault only. Adds complexity without current need. |
| Note encryption or access control | Single-user local vault. Not a concern. |
| Conflict resolution for concurrent edits | Single-user, single-session assumption. |
| AI-generated dynamic templates | Templates are static `.zk/templates/` files in v1. |
| Bidirectional GitLab sync / webhooks | GitLab is source of truth, pulled on demand. Real-time sync requires a webhook server — out of scope for a local CLI tool. |
| Cross-vault or remote note sync | Local only. |
