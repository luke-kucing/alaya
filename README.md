# alaya

> ālaya (ālayavijñāna) — storehouse consciousness. The layer of mind that holds all impressions, memories, and seeds of knowledge.

A FastMCP server that makes Claude Code the primary interface for a `zk`-managed personal knowledge vault. Read, write, search, link, synthesize, and maintain notes without ever touching a file directly.

## Stack

- **FastMCP** — MCP server framework
- **zk** — note graph engine (wikilinks, backlinks, tags)
- **LanceDB** — local hybrid vector search
- **nomic-embed-text-v1.5** — local embeddings via sentence-transformers ONNX backend
- **pymupdf4llm** — PDF extraction to clean Markdown
- **trafilatura** — web page extraction with focused crawling
- **watchdog** — file system watcher for live index updates

## Setup

```bash
# requires zk CLI installed: brew install zk
uv sync
ZK_NOTEBOOK_DIR=~/notes uv run python -m alaya.server
```

## Development

```bash
# run unit tests
uv run pytest -m "not integration"

# run all tests (requires zk binary)
uv run pytest
```

## Docs

- [REQUIREMENTS.md](docs/REQUIREMENTS.md)
- [PRD.md](docs/PRD.md)
