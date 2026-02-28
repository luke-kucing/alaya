# alaya

> **ālaya** (ālayavijñāna) — storehouse consciousness. The layer of mind that holds all impressions, memories, and seeds of knowledge.

A FastMCP server that makes Claude Code the primary interface for a `zk`-managed personal knowledge vault. Full read/write/search/synthesis access — the AI is the interface, the vault is the source of truth.

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
│  │  tasks.py   │ │  ingest.py  │ │  gitlab.py     │  │
│  │             │ │             │ │  github.py     │  │
│  └──────┬──────┘ └──────┬──────┘ └───────┬────────┘  │
│         │               │                │            │
│  ┌──────▼───────────────▼────────────────▼─────────┐  │
│  │                 Shared layer                     │  │
│  │  vault.py (path safety)    zk.py (CLI wrapper)  │  │
│  │  config.py (env vars)      watcher.py (watchdog)│  │
│  └──────────────────┬──────────────────────────────┘  │
│                     │                                 │
│  ┌──────────────────▼──────────────────────────────┐  │
│  │              index/                              │  │
│  │  embedder.py  (chunk + embed via nomic ONNX)    │  │
│  │  store.py     (LanceDB upsert/search)           │  │
│  │  reindex.py   (full vault rebuild)              │  │
│  └──────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────┘
         │                              │
    ┌────▼─────┐          ┌──────▼──────┐  ┌─────────────┐
    │  zk CLI  │          │   glab CLI  │  │   gh CLI    │
    │ (notes,  │          │  (GitLab    │  │  (GitHub    │
    │  links,  │          │   issues)   │  │   issues)   │
    │  tags)   │          └─────────────┘  └─────────────┘
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
    │      └── vectors/ (lance) │
    └───────────────────────────┘
```

### Design decisions

**Plain functions, not classes.** Tools are `async def get_note(path, vault) -> str` — no inheritance, no base classes. State is passed explicitly. A `Chunk` dataclass is the only data container.

**zk CLI as the seam.** All shell calls go through `run_zk()`. Unit tests mock at this boundary. Integration tests use the real binary.

**LanceDB is additive.** M1-M2 tools work without any index. Search falls back to `zk list --match`. The vector index is an optimization layer, not a requirement.

**Tools return Markdown strings.** Claude reads Markdown; it doesn't parse JSON. Tables, bullet lists, and metadata headers are formatted for Claude consumption.

**Confirmation lives in Claude, not the server.** The server executes; Claude proposes and waits for user approval on destructive ops.

## Tools

| Tool | Purpose |
|---|---|
| `get_note` | Read a note by path |
| `list_notes` | List notes filtered by directory, tag |
| `get_backlinks` | Notes that link to a given note |
| `get_links` | Outgoing links from a note |
| `get_tags` | All tags with counts |
| `create_note` | Create a new note with frontmatter and tags |
| `append_to_note` | Append text to an existing note |
| `update_tags` | Add or remove inline #tags |
| `capture_to_inbox` | Timestamped quick capture to inbox.md |
| `get_inbox` | Read inbox contents |
| `clear_inbox_item` | Remove a processed inbox item |
| `search_notes` | Hybrid semantic + keyword search (falls back to zk) |
| `move_note` | Move note to a different directory |
| `rename_note` | Rename note, update all wikilinks vault-wide |
| `delete_note` | Soft-delete to archives/ |
| `find_references` | Find wikilinks and text mentions of a title |
| `replace_section` | Replace content of a named ## section |
| `extract_section` | Extract a section into a new note, leave wikilink |
| `get_todos` | Find all `- [ ]` tasks across the vault |
| `complete_todo` | Mark a task complete (fuzzy line fallback) |
| `reindex_vault` | Full LanceDB rebuild (requires confirm) |
| `create_issue` | Create an issue on GitLab or GitHub |
| `get_issues` | List open issues from GitLab or GitHub |
| `close_issue` | Close an issue (requires confirm) |
| `issue_to_note` | Pull an issue into the vault as a note |
| `ingest` | Ingest a URL, PDF, or markdown file into LanceDB |

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
| Search | Hybrid vector + keyword via LanceDB |
| PDF extraction | pymupdf4llm |
| Web extraction | trafilatura |
| File watching | watchdog |
| HTTP client | httpx |
| Issue tracking | glab CLI (GitLab) / gh CLI (GitHub) |

## Setup

### Prerequisites

- [zk](https://github.com/zk-org/zk) — `brew install zk`
- [glab](https://gitlab.com/gitlab-org/cli) — `brew install glab` (optional, for GitLab integration)
- [gh](https://cli.github.com/) — `brew install gh` (optional, for GitHub integration)
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

### Install

```bash
git clone git@github.com:luke-kucing/alaya.git
cd alaya
uv sync
```

### Configure

```bash
cp .env.example .env
# edit .env — set ZK_NOTEBOOK_DIR to your vault path
```

| Variable | Required | Description |
|---|---|---|
| `ZK_NOTEBOOK_DIR` | Yes | Path to your zk vault (e.g. `~/notes`) |
| `ISSUE_BACKEND` | No | `gitlab` or `github` (default: auto-detected from env vars) |
| `GITLAB_PROJECT` | No | GitLab project path (e.g. `myorg/myrepo`) |
| `GITLAB_DEFAULT_LABELS` | No | Comma-separated default labels for new issues |
| `GITHUB_REPO` | No | GitHub repo (e.g. `owner/repo`) |
| `GITHUB_DEFAULT_LABELS` | No | Comma-separated default labels for new issues |

Configure **one** of `GITLAB_PROJECT` or `GITHUB_REPO`. If both are set, `ISSUE_BACKEND` determines which is used.

### Run

```bash
# start the MCP server
make serve

# or directly
ZK_NOTEBOOK_DIR=~/notes uv run python -m alaya.server
```

### Claude Code integration

Add to your Claude Code MCP settings (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "alaya": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/alaya", "python", "-m", "alaya.server"],
      "env": {
        "ZK_NOTEBOOK_DIR": "/Users/you/notes"
      }
    }
  }
}
```

## Development

```bash
make install          # install dependencies
make test             # run unit tests (148 tests)
make test-unit        # run unit tests verbose
make test-integration # run integration tests (requires zk binary)
make lint             # ruff check
make serve            # start the server
```

### Project structure

```
src/alaya/
├── server.py           # FastMCP server, tool registration
├── config.py           # env var loading, vault validation
├── vault.py            # path safety utilities
├── zk.py               # zk CLI subprocess wrapper
├── watcher.py          # watchdog file system monitor
├── tools/
│   ├── read.py         # get_note, list_notes, backlinks, links, tags
│   ├── write.py        # create_note, append_to_note, update_tags
│   ├── inbox.py        # capture, get_inbox, clear_inbox_item
│   ├── search.py       # hybrid search with zk fallback
│   ├── structure.py    # move, rename, delete, find_references
│   ├── edit.py         # replace_section, extract_section
│   ├── tasks.py        # get_todos, complete_todo
│   ├── gitlab.py       # GitLab issue CRUD via glab
│   ├── github.py       # GitHub issue CRUD via gh
│   └── ingest.py       # URL/PDF/markdown ingestion
└── index/
    ├── embedder.py     # chunk notes by section, embed via nomic ONNX
    ├── store.py        # LanceDB table management, hybrid search
    └── reindex.py      # full vault rebuild
```

### Testing approach

- **Unit tests** mock `run_zk` and the embedding model at the boundary. No subprocess calls, no model loading.
- **Integration tests** use the real `zk` binary and LanceDB against `vault_fixture/`.
- Tests use a copy of `vault_fixture/` in a temp directory — vault is never modified in place.
- TDD: failing tests written before implementation for every tool.

### Git workflow

```
main  ← stable, receives from dev when full milestone is done
  └── dev  ← integration branch, always green
        └── feat/m*  ← one branch per milestone
```

## Docs

- [REQUIREMENTS.md](docs/REQUIREMENTS.md) — 55 user stories, 26 tools, full functional spec
- [PRD.md](docs/PRD.md) — 5 milestones, TDD strategy, risk register

## Status

All 5 milestones implemented. 148 unit tests passing. See [open issues](https://github.com/luke-kucing/alaya/issues) for known bugs and planned improvements.
