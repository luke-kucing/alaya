# alaya

> **ālaya** (ālayavijñāna) — storehouse consciousness. The layer of mind that holds all impressions, memories, and seeds of knowledge.

A FastMCP server that makes Claude Code the primary interface for a `zk`-managed personal knowledge vault. Full read/write/search/synthesis access — the AI is the interface, the vault is the source of truth.

## Quickstart

```bash
# 1. Install prerequisites
brew install zk uv

# 2. Clone and install
git clone git@github.com:luke-kucing/alaya.git
cd alaya
uv sync

# 3. Initialize your vault (skip if you already have one)
mkdir -p ~/notes && cd ~/notes && zk init && cd -

# 4. Register with Claude Code
claude mcp add alaya \
  -e ZK_NOTEBOOK_DIR=$HOME/notes \
  -- uv run --directory $(pwd) python -m alaya.server

# 5. Start Claude Code — alaya connects automatically
claude
```

That's it. Ask Claude to "search my notes for X" or "create a note about Y" and it works.

### Running the server standalone

```bash
# Via make
make serve

# Or directly with env var
ZK_NOTEBOOK_DIR=~/notes uv run python -m alaya.server

# Or with .env file loaded
export $(cat .env | xargs) && uv run python -m alaya.server
```

The server communicates over stdio (MCP protocol) — it's designed to be launched by Claude Code, not run in a browser.

### Running tests

```bash
make test                # unit tests (464 tests, no external deps)
make test-integration    # integration tests (requires zk binary)
make lint                # ruff check
```

## Philosophy

- **The AI is the interface.** Stay in one place — a Claude Code session — and converse. Claude reads, writes, searches, and reasons across the vault.
- **Frictionless capture, deliberate structure.** Inbox capture is a single sentence. Processing, linking, and filing are separate structured acts.
- **Propose, then act.** Destructive or structural changes follow a confirmation flow. Appends and captures are always safe.
- **zk is the engine.** All note storage and graph operations delegate to the `zk` CLI. The vault stays portable.
- **Semantic retrieval over keyword search.** LanceDB hybrid search finds notes by meaning, not just exact words.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Claude Code                        │
│              (MCP client / AI layer)                 │
│     Synthesis, weekly review, gap analysis,          │
│     confirmation flow — all Claude's responsibility  │
└───────────────────────┬──────────────────────────────┘
                        │ MCP protocol (stdio)
┌───────────────────────▼──────────────────────────────┐
│                  alaya (FastMCP server)               │
│                                                       │
│  ┌─────────────┐ ┌─────────────┐ ┌────────────────┐  │
│  │ tools/      │ │ tools/      │ │ tools/         │  │
│  │  read.py    │ │  write.py   │ │  search.py     │  │
│  │  inbox.py   │ │  edit.py    │ │  structure.py  │  │
│  │  tasks.py   │ │  ingest.py  │ │  external.py   │  │
│  │  capture.py │ │  stats.py   │ │  graph.py      │  │
│  └──────┬──────┘ └──────┬──────┘ └───────┬────────┘  │
│         │               │                │            │
│  ┌──────▼───────────────▼────────────────▼─────────┐  │
│  │                 Shared layer                     │  │
│  │  vault.py (path safety)    zk.py (CLI wrapper)  │  │
│  │  config.py (env vars)      watcher.py (watchdog)│  │
│  │  events.py (pub/sub)       audit.py (JSONL log) │  │
│  └──────────────────┬──────────────────────────────┘  │
│                     │                                 │
│  ┌──────────────────▼──────────────────────────────┐  │
│  │              index/          providers/          │  │
│  │  embedder.py (nomic ONNX)    gitlab.py (glab)   │  │
│  │  store.py    (LanceDB)       github.py (gh)     │  │
│  │  router.py   (query class.)                     │  │
│  │  corrective.py (retry RAG)                      │  │
│  │  graph_rag.py  (link expand)                    │  │
│  │  hyde.py     (HyDE embed)                       │  │
│  │  contextual.py (chunk ctx)                      │  │
│  │  reindex.py  (rebuild)                          │  │
│  └──────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────┘
         │                              │
    ┌────▼─────┐    ┌──────────────────▼──────────────┐
    │  zk CLI  │    │  External providers              │
    │ (notes,  │    │  glab CLI · gh CLI · Outline API │
    │  links,  │    │  (pull issues in, push ideas out)│
    │  tags)   │    └──────────────────────────────────┘
    └────┬─────┘
         │
    ┌────▼──────────────────────┐
    │  ~/notes (vault)          │
    │  ├── daily/               │
    │  ├── inbox.md             │
    │  ├── projects/            │
    │  ├── areas/               │
    │  ├── people/              │
    │  ├── ideas/               │
    │  ├── learning/            │
    │  ├── resources/           │
    │  ├── raw/                 │
    │  ├── archives/            │
    │  └── .zk/                 │
    │      ├── vectors/ (lance) │
    │      └── audit.jsonl      │
    └───────────────────────────┘
```

## Search Pipeline

Alaya's search is a multi-stage RAG pipeline, not a simple keyword lookup:

```
Query ──▶ Router ──▶ Retrieval ──▶ Correction ──▶ Expansion ──▶ Results
          │          │              │               │
          │          │              │               └─ Graph RAG (opt-in)
          │          │              │                  wikilink traversal
          │          │              │
          │          │              └─ Corrective RAG
          │          │                 score check → reformulate → retry
          │          │
          │          └─ Hybrid Search (vector + BM25 + RRF)
          │             or Keyword-only / Semantic-only
          │
          └─ Adaptive Router
             KEYWORD | SEMANTIC | TEMPORAL | HYBRID
```

### Search features

| Feature | Description | Flag |
|---------|-------------|------|
| **Adaptive routing** | Classifies queries — short terms use BM25, questions use vectors, time refs auto-extract dates | Always on |
| **Hybrid search** | LanceDB native vector + FTS with Reciprocal Rank Fusion | Default |
| **Corrective RAG** | Retries with reformulated queries when results score below threshold | Always on |
| **Cross-encoder reranking** | Second-stage reranking with `ms-marco-MiniLM-L-6-v2` for higher precision | `rerank=True` |
| **Graph RAG** | Expands results via 1-hop wikilink traversal (outlinks + backlinks) | `graph_expand=True` |
| **HyDE** | Embeds a hypothetical answer document instead of the raw query | `hyde=True` |
| **Contextual retrieval** | Prepends metadata context (title, directory, tags, section) to chunks at index time | Always on |

### Design decisions

**Plain functions, not classes.** Tools are `async def get_note(path, vault) -> str` — no inheritance, no base classes. State is passed explicitly. A `Chunk` dataclass is the only data container.

**zk CLI as the seam.** All shell calls go through `run_zk()`. Unit tests mock at this boundary. Integration tests use the real binary.

**LanceDB is additive.** Core tools work without any index. Search falls back to `zk list --match`. The vector index is an optimization layer, not a requirement.

**Tools return Markdown strings.** Claude reads Markdown; it doesn't parse JSON. Tables, bullet lists, and metadata headers are formatted for Claude consumption.

**Confirmation lives in Claude, not the server.** The server executes; Claude proposes and waits for user approval on destructive ops.

**External systems are bridges, not mirrors.** The vault doesn't replicate GitLab/GitHub/Outline — it pulls context in and pushes ideas out.

## Tools

### Read & navigate

| Tool | Purpose |
|---|---|
| `get_note` | Read a note by path |
| `list_notes` | List notes filtered by directory, tag |
| `get_backlinks` | Notes that link to a given note |
| `get_links` | Outgoing links from a note |
| `get_tags` | All tags with counts |
| `vault_stats` | Vault overview: note counts, directories, top tags |
| `vault_graph` | Wikilink graph: orphans, hubs, topology |
| `vault_health` | Index health, embedding model status, migration progress |

### Write & capture

| Tool | Purpose |
|---|---|
| `create_note` | Create a new note with frontmatter and tags |
| `append_to_note` | Append text to an existing note (with optional section targeting) |
| `update_tags` | Add or remove inline #tags |
| `smart_capture` | Auto-route thoughts to the right note (person/daily/topic/inbox) |
| `capture_to_inbox` | Timestamped quick capture to inbox.md |
| `get_inbox` | Read inbox contents |
| `clear_inbox_item` | Remove a processed inbox item |

### Search

| Tool | Purpose |
|---|---|
| `search_notes` | Hybrid semantic + keyword search with adaptive routing, corrective RAG, and optional reranking/graph expansion/HyDE |

### Edit & structure

| Tool | Purpose |
|---|---|
| `replace_section` | Replace content of a named `##` section |
| `extract_section` | Extract a section into a new note, leave wikilink |
| `move_note` | Move note to a different directory |
| `rename_note` | Rename note, update all wikilinks vault-wide |
| `delete_note` | Soft-delete to archives/ |
| `find_references` | Find wikilinks and text mentions of a title |
| `get_todos` | Find all `- [ ]` tasks across the vault |
| `complete_todo` | Mark a task complete (fuzzy line fallback) |

### Ingest & external

| Tool | Purpose |
|---|---|
| `ingest` | Ingest a URL, PDF, or markdown file into the vault + index |
| `batch_ingest` | Batch ingest multiple URLs/files |
| `reindex_vault` | Full LanceDB rebuild (requires confirm) |
| `pull_external` | Pull issues/docs from GitLab, GitHub, or Outline |
| `push_external` | Push a vault note to an external provider |

External issue CRUD (list, close, update) is handled by Claude Code natively via `glab`/`gh` CLI — the MCP server only bridges the vault to external systems.

## Index Pipeline

### Chunking strategies

| Strategy | Trigger | How it works |
|----------|---------|-------------|
| `DailyNoteChunker` | Notes in `daily/` | Splits on `###` sub-headers |
| `SectionChunker` | Notes with `##` headers | Splits on `##`, sub-splits long sections on paragraphs |
| `SemanticChunker` | Default for flat notes | Paragraph-aware splitting with code block preservation |
| `SlidingWindowChunker` | Legacy fallback | Fixed token window with overlap |

### Embedding

- **Model:** nomic-embed-text-v1.5 via fastembed (ONNX, no PyTorch required)
- **Dimensions:** 768
- **Prefixes:** `search_query:` for queries, `search_document:` for chunks
- **Quantized variant:** `nomic-v1.5-q4` available via `ALAYA_EMBEDDING_MODEL` env var
- **Hot-swap:** Changing the model triggers automatic background re-embedding

### Write-through indexing

All write operations (create, append, edit, move, rename, delete) emit events that trigger immediate index updates. The file watcher catches external edits with 2-second debounce. Double-indexing is prevented via coordination between the event system and watcher.

### Audit logging

Every tool call is logged to `.zk/audit.jsonl` with timestamp, tool name, arguments, status, duration, and result summary. The TUI dashboard tails this file for real-time activity monitoring.

## Vault structure

```
~/notes/
├── daily/       # daily notes — connective tissue
├── inbox.md     # frictionless capture, process weekly
├── projects/    # active work with a finish line
├── areas/       # ongoing responsibilities
├── people/      # 1:1s, context, relationships
├── ideas/       # not ready to be a project yet
├── learning/    # active study
├── resources/   # settled reference, distilled knowledge
├── raw/         # drop zone for PDFs and URLs (auto-ingested)
└── archives/    # completed or dead things (soft-delete target)
```

Notes use minimal YAML frontmatter (`title` + `date`) and inline `#tags`. Links are wikilinks (`[[title]]`).

## Stack

| Component | Choice |
|---|---|
| Language | Python 3.12+ |
| Package manager | uv |
| MCP framework | FastMCP |
| Note engine | zk CLI |
| Vector store | LanceDB (local, Apache Arrow) |
| Embeddings | nomic-embed-text-v1.5 (ONNX, no PyTorch) |
| Search | Hybrid vector + BM25 via LanceDB with RRF reranking |
| Reranking | cross-encoder/ms-marco-MiniLM-L-6-v2 (optional) |
| PDF extraction | pymupdf4llm |
| Web extraction | trafilatura |
| File watching | watchdog |
| HTTP client | httpx |
| External bridge | glab CLI (GitLab) / gh CLI (GitHub) / Outline API |

## Configuration

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — `brew install uv`
- [zk](https://github.com/zk-org/zk) — `brew install zk`
- [glab](https://gitlab.com/gitlab-org/cli) — `brew install glab` (optional, for GitLab bridge)
- [gh](https://cli.github.com/) — `brew install gh` (optional, for GitHub bridge)

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `ZK_NOTEBOOK_DIR` | Yes | Path to your zk vault (e.g. `~/notes`) |
| `ALAYA_EMBEDDING_MODEL` | No | Embedding model variant (`nomic-v1.5` or `nomic-v1.5-q4`, default: `nomic-v1.5`) |
| `GITLAB_PROJECT` | No | GitLab project path — enables GitLab provider |
| `GITLAB_DEFAULT_LABELS` | No | Comma-separated default labels for new issues |
| `GITHUB_REPO` | No | GitHub repo (e.g. `owner/repo`) — enables GitHub provider |
| `GITHUB_DEFAULT_LABELS` | No | Comma-separated default labels for new issues |
| `OUTLINE_URL` | No | Outline instance URL — enables Outline provider |
| `OUTLINE_API_KEY` | No | Outline API key |

### Optional dependencies

```bash
# Install cross-encoder reranking support
uv sync --extra rerank
```

Pass additional env vars when registering with Claude Code using `-e`:

```bash
claude mcp add alaya \
  -e ZK_NOTEBOOK_DIR=$HOME/notes \
  -e GITHUB_REPO=owner/repo \
  -- uv run --directory /path/to/alaya python -m alaya.server
```

Configure any combination of providers. `pull_external` and `push_external` auto-detect the provider from URLs or use the configured defaults.

## Development

```bash
make install          # install dependencies
make test             # run unit tests (464 tests)
make test-unit        # run unit tests verbose
make test-integration # run integration tests (requires zk binary)
make lint             # ruff check
make serve            # start the server
```

### Project structure

```
src/alaya/
├── server.py           # FastMCP server, tool registration, audit wrapping
├── config.py           # env var loading, vault validation
├── vault.py            # path safety, frontmatter parsing
├── zk.py               # zk CLI subprocess wrapper
├── events.py           # pub/sub event bus for write-through indexing
├── watcher.py          # watchdog file system monitor
├── errors.py           # structured error codes
├── audit.py            # JSONL tool call logging
├── tools/
│   ├── read.py         # get_note, list_notes, backlinks, links, tags, reindex
│   ├── write.py        # create_note, append_to_note, update_tags
│   ├── inbox.py        # capture, get_inbox, clear_inbox_item
│   ├── capture.py      # smart_capture (auto-routing)
│   ├── search.py       # adaptive search with corrective RAG pipeline
│   ├── structure.py    # move, rename, delete, find_references
│   ├── edit.py         # replace_section, extract_section
│   ├── tasks.py        # get_todos, complete_todo
│   ├── external.py     # pull_external, push_external
│   ├── ingest.py       # URL/PDF/markdown ingestion
│   ├── stats.py        # vault_stats
│   └── graph.py        # vault_graph (wikilink topology)
├── providers/
│   ├── gitlab.py       # glab CLI wrapper
│   └── github.py       # gh CLI wrapper
└── index/
    ├── embedder.py     # chunk notes, embed via nomic ONNX
    ├── store.py        # LanceDB: upsert, delete, hybrid/keyword/vector search
    ├── router.py       # adaptive query classification
    ├── corrective.py   # retrieval quality check + query reformulation
    ├── graph_rag.py    # wikilink-based search expansion
    ├── hyde.py         # hypothetical document embeddings
    ├── contextual.py   # chunk context prepending
    ├── chunking.py     # pluggable chunking strategies
    ├── models.py       # embedding model registry
    ├── reindex.py      # full/incremental rebuild
    └── health.py       # index health tracking
```

### Testing approach

- **Unit tests** mock `run_zk` and the embedding model at the boundary. No subprocess calls, no model loading.
- **Integration tests** use the real `zk` binary and LanceDB against `vault_fixture/`.
- Tests use a copy of `vault_fixture/` in a temp directory — vault is never modified in place.
- TDD: failing tests written before implementation for every tool.

## Companion: alaya-tui

[alaya-tui](https://github.com/luke-kucing/alaya-tui) is a Go + Bubble Tea terminal dashboard for vault observability and agent-agnostic chat. It shows vault health, tails the audit log, browses notes, and spawns any configured LLM agent as a subprocess.

## Status

All 5 milestones implemented plus advanced RAG pipeline. 464 unit tests passing. See [open issues](https://github.com/luke-kucing/alaya/issues) for planned improvements.
