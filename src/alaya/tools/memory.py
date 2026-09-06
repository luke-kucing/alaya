"""Agent memory tools: memory_recall, memory_checkpoint, memory_resume.

These exist for agent harnesses rather than humans. A harness loop needs
budgeted retrieval in one call, a durable place to put a summary when its
context is compacted, and a single call that rebuilds working memory from the
vault at the start of a fresh-context iteration.

Notes written here carry frontmatter ``type: agent-memory`` so that
``search_notes`` excludes them from human-facing search by default.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from fastmcp import FastMCP

from alaya.errors import error, INVALID_ARGUMENT
from alaya.events import emit, NoteEvent, EventType
from alaya.tokens import count_tokens, truncate_to_tokens
from alaya.tools._locks import get_path_lock, atomic_write
from alaya.tools.search import AGENT_MEMORY_TYPE

logger = logging.getLogger(__name__)

DEFAULT_RECALL_BUDGET = 2000
DEFAULT_RESUME_BUDGET = 4000

# Tokens reserved for the header/footer comment lines so the total response
# still fits the caller's budget.
_ENVELOPE_TOKENS = 40


def _agent_dir(vault: Path, backend=None) -> str:
    return getattr(getattr(backend, "config", None), "agent_dir", None) or "agents"


def _safe_session_id(session_id: str) -> str:
    """Reject session ids that would escape the agent directory."""
    sid = session_id.strip()
    if not sid or sid in (".", "..") or "/" in sid or "\\" in sid or sid.startswith("."):
        raise ValueError(
            f"Invalid session_id {session_id!r}: must be a single path segment "
            "with no separators and no leading dot"
        )
    return sid


def _checkpoint_path(vault: Path, session_id: str, backend=None) -> Path:
    sid = _safe_session_id(session_id)
    # nosemgrep: semgrep.alaya-path-traversal — sid validated by _safe_session_id()
    return vault / _agent_dir(vault, backend) / sid / "checkpoint.md"


def _envelope(body: str, sources: int | None = None) -> str:
    """Append the token_count comment agents use for budget accounting."""
    if sources is None:
        return f"{body}\n\n<!-- token_count: {count_tokens(body)} -->"
    return f"{body}\n\n<!-- token_count: {count_tokens(body)}; sources: {sources} -->"


# --- memory_recall ---------------------------------------------------------

def memory_recall(
    query: str,
    vault: Path,
    budget_tokens: int = DEFAULT_RECALL_BUDGET,
    scope: str | None = None,
    include_types: list[str] | None = None,
    backend=None,
    cache=None,
) -> str:
    """Retrieve vault context for *query*, trimmed to *budget_tokens*.

    Runs the same routed + corrective search pipeline as ``search_notes`` and
    returns the matching chunk text, so the caller does not need a follow-up
    ``get_note`` per hit.
    """
    if budget_tokens <= 0:
        raise ValueError("budget_tokens must be positive")

    from alaya.tools.search import _hybrid_search_available, _run_corrective_search

    if not _hybrid_search_available(vault):
        return _envelope(
            "No index available — memory_recall requires the vector index. "
            "Call vault_health to check index status.",
            sources=0,
        )

    # Recall is for agents, so agent memory is *included* unless narrowed.
    results = _run_corrective_search(
        query, vault, directory=scope or None, limit=20,
        include_types=include_types or None, exclude_types=None,
    )
    if not results:
        return _envelope(f"No vault context found for: {query}", sources=0)

    remaining = max(0, budget_tokens - _ENVELOPE_TOKENS)
    blocks: list[str] = []
    used = 0
    seen: set[str] = set()

    for r in results:
        if r["path"] in seen:
            continue
        seen.add(r["path"])

        header = f"### [[{r['title']}]] — `{r['path']}` (score {r['score']:.2f})"
        header_cost = count_tokens(header) + 2
        if used + header_cost >= remaining:
            break

        text, truncated = truncate_to_tokens(r["text"], remaining - used - header_cost)
        if not text:
            break
        if truncated:
            text += f"\n\n…[truncated; get_note(\"{r['path']}\") for the full note]"

        block = f"{header}\n\n{text}"
        used += count_tokens(block) + 2
        blocks.append(block)
        if used >= remaining:
            break

    if not blocks:
        return _envelope(
            f"Results found for {query!r} but budget_tokens={budget_tokens} is too small "
            "to return any of them.",
            sources=0,
        )

    body = f"## Recall: {query}\n\n" + "\n\n".join(blocks)
    return _envelope(body, sources=len(blocks))


# --- memory_checkpoint -----------------------------------------------------

def _render_checkpoint(
    session_id: str,
    agent: str,
    summary_md: str,
    open_items: list[str],
    decisions: list[str],
    entities: list[str],
    confidence: float,
    ttl_days: int,
) -> str:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    lines = [
        "---",
        f"title: Checkpoint {session_id}",
        f"type: {AGENT_MEMORY_TYPE}",
        "kind: checkpoint",
        f"session: {session_id}",
        f"agent: {agent}",
        f"confidence: {confidence}",
        f"ttl_days: {ttl_days}",
        f"updated: {now}",
        "---",
        "",
        f"# Checkpoint — {session_id}",
        "",
        "## Summary",
        "",
        summary_md.strip() or "_(none)_",
        "",
        "## Decisions",
        "",
    ]
    lines += [f"- {d}" for d in decisions] or ["_(none)_"]
    lines += ["", "## Open items", ""]
    lines += [f"- [ ] {o}" for o in open_items] or ["_(none)_"]
    lines += ["", "## Entities", ""]
    # Wikilinks so graph_rag connects this session to people/project notes.
    lines += [" ".join(f"[[{e}]]" for e in entities)] if entities else ["_(none)_"]
    lines += [""]
    return "\n".join(lines)


def memory_checkpoint(
    session_id: str,
    agent: str,
    summary_md: str,
    vault: Path,
    open_items: list[str] | None = None,
    decisions: list[str] | None = None,
    entities: list[str] | None = None,
    confidence: float = 0.7,
    ttl_days: int = 30,
    backend=None,
) -> str:
    """Write (or overwrite) the checkpoint for *session_id*. Returns its path."""
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be between 0.0 and 1.0, got {confidence}")

    path = _checkpoint_path(vault, session_id, backend)
    content = _render_checkpoint(
        _safe_session_id(session_id), agent, summary_md,
        open_items or [], decisions or [], entities or [], confidence, ttl_days,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with get_path_lock(path):
        existed = path.exists()
        atomic_write(path, content)

    relative = str(path.relative_to(vault))
    emit(NoteEvent(EventType.MODIFIED if existed else EventType.CREATED, relative))
    return relative


# --- memory_resume ---------------------------------------------------------

def memory_resume(
    session_id: str,
    vault: Path,
    budget_tokens: int = DEFAULT_RESUME_BUDGET,
    backend=None,
    cache=None,
) -> str:
    """Return the checkpoint for *session_id* plus its 1-hop linked notes.

    This is the handoff document a fresh-context loop iteration starts from.
    """
    if budget_tokens <= 0:
        raise ValueError("budget_tokens must be positive")

    path = _checkpoint_path(vault, session_id, backend)
    if not path.exists():
        return _envelope(
            f"No checkpoint for session {session_id!r}. "
            "Call memory_checkpoint first, or start from the task brief.",
            sources=0,
        )

    checkpoint = path.read_text()
    remaining = max(0, budget_tokens - _ENVELOPE_TOKENS)
    body, truncated = truncate_to_tokens(checkpoint, remaining)
    used = count_tokens(body)
    sources = 1

    if truncated:
        return _envelope(body + "\n\n…[checkpoint truncated to budget]", sources=sources)

    # 1-hop expansion: pull the notes the checkpoint links to, budget permitting.
    linked = _linked_notes(checkpoint, vault, backend)
    if linked:
        parts = [body, "\n---\n\n## Linked context\n"]
        used += 10
        for rel_path, text in linked:
            header = f"### `{rel_path}`\n"
            cost = count_tokens(header) + 2
            if used + cost >= remaining:
                break
            snippet, was_cut = truncate_to_tokens(text, remaining - used - cost)
            if not snippet:
                break
            if was_cut:
                snippet += f"\n\n…[truncated; get_note(\"{rel_path}\")]"
            parts.append(f"{header}\n{snippet}\n")
            used += count_tokens(snippet) + cost
            sources += 1
        body = "\n".join(parts)

    return _envelope(body, sources=sources)


def _linked_notes(content: str, vault: Path, backend=None) -> list[tuple[str, str]]:
    """Resolve wikilinks in *content* to (relative_path, text) pairs."""
    import re

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for link in re.findall(r"\[\[([^\]|#]+)", content):
        name = link.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        target = backend.resolve_wikilink(name) if backend else None
        if target is None or not target.exists():
            continue
        try:
            out.append((str(target.relative_to(vault)), target.read_text()))
        except (OSError, ValueError) as e:
            logger.debug("Skipping linked note %s: %s", name, e)
    return out


# --- FastMCP tool registration ---------------------------------------------

def _register(mcp: FastMCP, vault: Path, backend=None, cache=None) -> None:
    @mcp.tool()
    def memory_recall_tool(
        query: str,
        budget_tokens: int = DEFAULT_RECALL_BUDGET,
        scope: str = "",
        include_types: list[str] | None = None,
    ) -> str:
        """Retrieve vault context for a query, trimmed to a token budget.

        One call instead of search-then-read-each-hit: returns the matching
        chunk text directly, never exceeding budget_tokens. Restrict to a
        directory with scope, or to specific frontmatter types with
        include_types. The response ends with a token_count comment.
        """
        try:
            return memory_recall(
                query, vault, budget_tokens=budget_tokens, scope=scope or None,
                include_types=include_types or None, backend=backend, cache=cache,
            )
        except ValueError as e:
            return error(INVALID_ARGUMENT, str(e))

    @mcp.tool()
    def memory_checkpoint_tool(
        session_id: str,
        agent: str,
        summary_md: str,
        open_items: list[str] | None = None,
        decisions: list[str] | None = None,
        entities: list[str] | None = None,
        confidence: float = 0.7,
        ttl_days: int = 30,
    ) -> str:
        """Persist an agent session summary to the vault as a durable checkpoint.

        Call this when compacting context or finishing a loop iteration.
        Entities are written as wikilinks so the checkpoint joins the note
        graph. Overwrites any previous checkpoint for the same session_id.
        """
        try:
            path = memory_checkpoint(
                session_id, agent, summary_md, vault,
                open_items=open_items, decisions=decisions, entities=entities,
                confidence=confidence, ttl_days=ttl_days, backend=backend,
            )
        except ValueError as e:
            return error(INVALID_ARGUMENT, str(e))
        return f"Checkpoint saved: {path}"

    @mcp.tool()
    def memory_resume_tool(
        session_id: str,
        budget_tokens: int = DEFAULT_RESUME_BUDGET,
    ) -> str:
        """Rebuild working memory for a session from its checkpoint.

        Returns the latest checkpoint plus the notes it links to, trimmed to
        budget_tokens. Start a fresh-context iteration from this instead of
        replaying conversation history.
        """
        try:
            return memory_resume(
                session_id, vault, budget_tokens=budget_tokens,
                backend=backend, cache=cache,
            )
        except ValueError as e:
            return error(INVALID_ARGUMENT, str(e))
