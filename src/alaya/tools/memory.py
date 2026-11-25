"""Agent memory tools: memory_recall, memory_checkpoint, memory_resume,
memory_supersede, memory_stale.

These exist for agent harnesses rather than humans. A harness loop needs
budgeted retrieval in one call, a durable place to put a summary when its
context is compacted, and a single call that rebuilds working memory from the
vault at the start of a fresh-context iteration.

Notes written here carry frontmatter ``type: agent-memory`` so that
``search_notes`` excludes them from human-facing search by default.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastmcp import FastMCP

from alaya.errors import error, INVALID_ARGUMENT, NOT_FOUND
from alaya.events import emit, NoteEvent, EventType
from alaya.tokens import count_tokens, truncate_to_tokens
from alaya.tools._locks import get_path_lock, atomic_write
from alaya.tools.search import AGENT_MEMORY_TYPE
from alaya.vault import _yaml_quote, resolve_note_path

logger = logging.getLogger(__name__)

DEFAULT_RECALL_BUDGET = 2000
DEFAULT_RESUME_BUDGET = 4000
DEFAULT_STALE_BUDGET = 2000
LOW_CONFIDENCE = 0.5
DUPLICATE_SIMILARITY = 0.92

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
    since: str | None = None,
    include_expired: bool = False,
    include_superseded: bool = False,
    backend=None,
    cache=None,
) -> str:
    """Retrieve vault context for *query*, trimmed to *budget_tokens*.

    Runs the same routed + corrective search pipeline as ``search_notes`` and
    returns the matching chunk text, so the caller does not need a follow-up
    ``get_note`` per hit. Agent memory past its ``ttl_days`` is dropped unless
    *include_expired*, and its score is weighted by its ``confidence``. Notes
    with ``superseded_by`` set are dropped unless *include_superseded*.
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
        include_types=include_types or None, exclude_types=None, since=since or None,
    )
    results = _weigh_memory(results, vault, include_expired, include_superseded)
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
        if r.get("superseded_by"):
            header += f" — superseded by {r['superseded_by']}"
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


def _memory_weight(
    path: Path, now: datetime, include_expired: bool, include_superseded: bool = False,
) -> tuple[float | None, str]:
    """Score multiplier for a hit, and what superseded it ("" if nothing).

    The multiplier is its confidence if it is agent memory, else 1; None when
    it is agent memory past ``updated + ttl_days``, or superseded and
    *include_superseded* is off.
    """
    from alaya.cache import _parse_frontmatter

    try:
        meta = _parse_frontmatter(path.read_text())
    except OSError:
        return 1.0, ""
    superseded_by = meta.get("superseded_by", "")
    return _weight(meta, now, include_expired, superseded_by and not include_superseded), superseded_by


def _weight(meta: dict, now: datetime, include_expired: bool, dropped: bool) -> float | None:
    if dropped:
        return None
    if meta.get("type") != AGENT_MEMORY_TYPE:
        return 1.0
    if not include_expired and _expired(meta, now):
        return None
    confidence = _confidence(meta)
    return 1.0 if confidence is None else confidence


def _expired(meta: dict, now: datetime) -> bool:
    """Past ``updated + ttl_days``; a note without a usable ttl never expires."""
    try:
        updated = datetime.fromisoformat(meta["updated"])
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        return updated + timedelta(days=float(meta["ttl_days"])) < now
    except (KeyError, ValueError):
        return False


def _confidence(meta: dict) -> float | None:
    try:
        return min(1.0, max(0.0, float(meta["confidence"])))
    except (KeyError, ValueError):
        return None


def _weigh_memory(
    results: list[dict], vault: Path, include_expired: bool, include_superseded: bool = False,
) -> list[dict]:
    """Drop expired or superseded memory and weight the rest by confidence."""
    now = datetime.now(UTC)
    seen: dict[str, tuple[float | None, str]] = {}
    out = []
    for r in results:
        if r["path"] not in seen:
            seen[r["path"]] = _memory_weight(vault / r["path"], now, include_expired, include_superseded)
        w, superseded_by = seen[r["path"]]
        if w is None:
            continue
        if w != 1.0:
            r = {**r, "score": r["score"] * w}
        out.append({**r, "superseded_by": superseded_by} if superseded_by else r)
    if any(w not in (None, 1.0) for w, _ in seen.values()):
        out.sort(key=lambda r: r["score"], reverse=True)
    return out


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
        f"title: {_yaml_quote(f'Checkpoint {session_id}')}",
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
    supersedes: list[str] | None = None,
    backend=None,
) -> str:
    """Write (or overwrite) the checkpoint for *session_id*. Returns its path.

    Each note in *supersedes* is marked replaced by this checkpoint.
    """
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be between 0.0 and 1.0, got {confidence}")

    path = _checkpoint_path(vault, session_id, backend)
    for old in supersedes or []:
        _note_path(old, vault, backend)  # fail before writing anything
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
    for old in supersedes or []:
        memory_supersede(old, relative, vault, backend=backend)
    return relative


# --- memory_supersede ------------------------------------------------------

def _note_path(ref: str, vault: Path, backend=None) -> Path:
    """A vault-relative path, or a [[wikilink]] the backend resolves."""
    ref = ref.strip()
    if ref.startswith("[[") and ref.endswith("]]"):
        target = backend.resolve_wikilink(ref[2:-2].split("|")[0].strip()) if backend else None
        if target is None:
            raise FileNotFoundError(f"No note for {ref}")
        path = resolve_note_path(str(target.resolve().relative_to(vault.resolve())), vault)
    else:
        path = resolve_note_path(ref, vault)
    if not path.is_file():
        raise FileNotFoundError(f"No note at {ref}")
    return path


def _link(path: Path, backend=None) -> str:
    key = backend.note_link_key(path, path.read_text()) if backend else path.stem
    return f"[[{key}]]"


def _set_frontmatter_field(content: str, key: str, value) -> str:
    """Set *key* to *value* (written as a JSON scalar or flow list, which is YAML),
    replacing any existing value, leaving the rest of the frontmatter as written."""
    line = f"{key}: {json.dumps(value, ensure_ascii=False)}\n"
    if not content.startswith("---\n"):
        return f"---\n{line}---\n\n{content}"
    end = content.find("\n---", 3)
    if end == -1:
        return f"---\n{line}---\n\n{content}"
    lines = content[4:end + 1].splitlines(keepends=True)
    kept, skipping = [], False
    for existing in lines:
        if existing.startswith(f"{key}:"):
            skipping = True
            continue
        # A replaced block value continues on indented or "- " lines.
        if skipping and existing[:1] in (" ", "\t", "-"):
            continue
        skipping = False
        kept.append(existing)
    return "---\n" + "".join(kept) + line + content[end + 1:]


def memory_supersede(old: str, new: str, vault: Path, reason: str = "", backend=None) -> str:
    """Mark note *old* replaced by note *new*, keeping both.

    *old* gets ``superseded_by`` and a dated line with *reason*; *new* gets
    *old* added to ``supersedes``. Each takes a path or a [[wikilink]].
    """
    from alaya.cache import _parse_frontmatter

    old_path, new_path = _note_path(old, vault, backend), _note_path(new, vault, backend)
    if old_path == new_path:
        raise ValueError("A note cannot supersede itself")
    first, second = sorted((old_path, new_path))  # one lock order, no deadlock
    with get_path_lock(first), get_path_lock(second):
        old_link, new_link = _link(old_path, backend), _link(new_path, backend)
        old_text = _set_frontmatter_field(old_path.read_text(), "superseded_by", new_link)
        note = f"Superseded by {new_link} on {datetime.now(UTC).date().isoformat()}"
        if reason.strip():
            note += f": {' '.join(reason.split())}"
        old_text = old_text.rstrip("\n") + f"\n\n> {note}\n"

        new_text = new_path.read_text()
        listed = _parse_frontmatter(new_text).get("supersedes") or []
        listed = [listed] if isinstance(listed, str) else [str(x) for x in listed]
        if old_link not in listed:
            new_text = _set_frontmatter_field(new_text, "supersedes", listed + [old_link])

        atomic_write(old_path, old_text)
        atomic_write(new_path, new_text)

    old_rel, new_rel = str(old_path.relative_to(vault.resolve())), str(new_path.relative_to(vault.resolve()))
    emit(NoteEvent(EventType.MODIFIED, old_rel))
    emit(NoteEvent(EventType.MODIFIED, new_rel))
    return f"{old_rel} superseded by {new_rel}"


# --- memory_stale ----------------------------------------------------------

def _near_duplicates(vault: Path, paths: set[str], threshold: float) -> list[tuple[str, str, float]]:
    """Pairs of agent-memory notes whose mean chunk vectors are at least *threshold* alike.

    shortcut: all-pairs cosine over every memory note, fine to a few thousand
    notes; move to the store's ANN search if agent memory grows past that.
    """
    import numpy as np

    from alaya.index.store import get_store

    try:
        rows = (
            get_store(vault)._get_table().search()
            .where(f"note_type = '{AGENT_MEMORY_TYPE}'")
            .select(["path", "vector"]).limit(100_000).to_list()
        )
    except Exception as e:  # noqa: BLE001 — no index yet: report the other groups
        logger.debug("near-duplicate scan skipped: %s", e)
        return []
    by_path: dict[str, list] = {}
    for r in rows:
        if r["path"] in paths:
            by_path.setdefault(r["path"], []).append(r["vector"])
    names = sorted(by_path)
    if len(names) < 2:
        return []
    vectors = np.array([np.mean(by_path[n], axis=0) for n in names])
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-12
    sims = vectors @ vectors.T
    pairs = [
        (names[i], names[j], float(sims[i, j]))
        for i in range(len(names)) for j in range(i + 1, len(names))
        if sims[i, j] >= threshold
    ]
    return sorted(pairs, key=lambda p: -p[2])


def memory_stale(
    vault: Path,
    scope: str | None = None,
    limit: int = 50,
    budget_tokens: int = DEFAULT_STALE_BUDGET,
    low_confidence: float = LOW_CONFIDENCE,
    similarity: float = DUPLICATE_SIMILARITY,
    backend=None,
) -> str:
    """Agent memory that needs upkeep, grouped: expired, low_confidence,
    near_duplicates and orphans (no links in or out). At most *limit* items
    per group, trimmed to *budget_tokens*.

    alaya only finds these; the calling model decides what to merge,
    supersede or delete.
    """
    import re

    from alaya.cache import _parse_frontmatter
    from alaya.vault import iter_vault_md

    if budget_tokens <= 0 or limit <= 0:
        raise ValueError("budget_tokens and limit must be positive")
    root = resolve_note_path(scope, vault) if scope else vault.resolve()
    link_re = re.compile(r"\[\[([^\]|#]+)")

    now = datetime.now(UTC)
    memory: dict[str, tuple[dict, str, set[str]]] = {}  # path -> meta, link key, outlinks
    inlinks: dict[str, set[str]] = {}  # link key -> paths linking to it
    for md in iter_vault_md(vault):
        try:
            content = md.read_text()
        except OSError:
            continue
        rel = str(md.relative_to(vault))
        outlinks = {m.strip() for m in link_re.findall(content)}
        for target in outlinks:
            inlinks.setdefault(target, set()).add(rel)
        meta = _parse_frontmatter(content)
        if meta.get("type") == AGENT_MEMORY_TYPE and md.resolve().is_relative_to(root):
            key = backend.note_link_key(md, content) if backend else md.stem
            memory[rel] = (meta, key, outlinks)

    groups: dict[str, list[str]] = {"expired": [], "low_confidence": [], "near_duplicates": [], "orphans": []}
    for rel in sorted(memory):
        meta, key, outlinks = memory[rel]
        if _expired(meta, now):
            groups["expired"].append(f"`{rel}` — updated {meta['updated']}, ttl {meta['ttl_days']} days")
        confidence = _confidence(meta)
        if confidence is not None and confidence < low_confidence:
            groups["low_confidence"].append(f"`{rel}` — confidence {confidence}")
        if not outlinks and not (inlinks.get(key, set()) - {rel}):
            groups["orphans"].append(f"`{rel}`")
    groups["near_duplicates"] = [
        f"`{a}` ≈ `{b}` ({sim:.2f})" for a, b, sim in _near_duplicates(vault, set(memory), similarity)
    ]

    lines = [f"## Stale memory: {len(memory)} agent-memory notes scanned", ""]
    for name, items in groups.items():
        more = f", first {limit}" if len(items) > limit else ""
        lines += [f"### {name} ({len(items)}{more})", ""]
        lines += [f"- {i}" for i in items[:limit]] or ["_(none)_"]
        lines.append("")
    body, truncated = truncate_to_tokens("\n".join(lines).rstrip(), max(1, budget_tokens - _ENVELOPE_TOKENS))
    if truncated:
        body += "\n\n…[truncated; lower limit or narrow scope]"
    return _envelope(body)


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
    @mcp.tool(name="memory_recall")
    def memory_recall_tool(
        query: str,
        budget_tokens: int = DEFAULT_RECALL_BUDGET,
        scope: str = "",
        include_types: list[str] | None = None,
        since: str = "",
        include_expired: bool = False,
        include_superseded: bool = False,
    ) -> str:
        """Retrieve vault context for a query, trimmed to a token budget.

        One call instead of search-then-read-each-hit: returns the matching
        chunk text directly, never exceeding budget_tokens. Restrict to a
        directory with scope, to specific frontmatter types with
        include_types, or to notes modified on or after since (YYYY-MM-DD).
        Agent memory past its ttl_days is left out unless include_expired;
        low-confidence memory ranks lower. Notes replaced via memory_supersede
        are left out unless include_superseded. The response ends with a
        token_count comment.
        """
        try:
            return memory_recall(
                query, vault, budget_tokens=budget_tokens, scope=scope or None,
                include_types=include_types or None, since=since or None,
                include_expired=include_expired, include_superseded=include_superseded,
                backend=backend, cache=cache,
            )
        except ValueError as e:
            return error(INVALID_ARGUMENT, str(e))

    @mcp.tool(name="memory_checkpoint")
    def memory_checkpoint_tool(
        session_id: str,
        agent: str,
        summary_md: str,
        open_items: list[str] | None = None,
        decisions: list[str] | None = None,
        entities: list[str] | None = None,
        confidence: float = 0.7,
        ttl_days: int = 30,
        supersedes: list[str] | None = None,
    ) -> str:
        """Persist an agent session summary to the vault as a durable checkpoint.

        Call this when compacting context or finishing a loop iteration.
        Entities are written as wikilinks so the checkpoint joins the note
        graph. Overwrites any previous checkpoint for the same session_id.
        supersedes lists notes (paths or [[links]]) this checkpoint replaces.
        """
        try:
            path = memory_checkpoint(
                session_id, agent, summary_md, vault,
                open_items=open_items, decisions=decisions, entities=entities,
                confidence=confidence, ttl_days=ttl_days, supersedes=supersedes,
                backend=backend,
            )
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except ValueError as e:
            return error(INVALID_ARGUMENT, str(e))
        return f"Checkpoint saved: {path}"

    @mcp.tool(name="memory_stale")
    def memory_stale_tool(scope: str = "", limit: int = 50, budget_tokens: int = DEFAULT_STALE_BUDGET) -> str:
        """Find agent memory that needs upkeep: expired (past ttl_days),
        low_confidence, near_duplicates (similar embeddings) and orphans (no
        links in or out). Returns paths only; read them with get_note, then
        merge with memory_supersede or remove with delete_note.
        """
        try:
            return memory_stale(vault, scope=scope or None, limit=limit,
                                budget_tokens=budget_tokens, backend=backend)
        except ValueError as e:
            return error(INVALID_ARGUMENT, str(e))

    @mcp.tool(name="memory_supersede")
    def memory_supersede_tool(old: str, new: str, reason: str = "") -> str:
        """Mark note old as replaced by note new, keeping both for history.

        Use when a decision or fact changes: memory_recall then returns new
        and leaves old out. Takes vault paths or [[wikilinks]]; the reason is
        appended to old.
        """
        try:
            return memory_supersede(old, new, vault, reason=reason, backend=backend)
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except ValueError as e:
            return error(INVALID_ARGUMENT, str(e))

    @mcp.tool(name="memory_resume")
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
