"""Smart capture tool: automatic thought routing to the right note."""
import re
import threading
from datetime import date
from pathlib import Path

from fastmcp import FastMCP
from alaya.errors import error, INVALID_ARGUMENT
from alaya.vault import parse_note
from alaya.tools.write import create_note, append_to_note, _slugify
from alaya.tools.inbox import capture_to_inbox

_MATCH_THRESHOLD = 0.55

_DAILY_TRIGGERS = frozenset({
    "today", "this morning", "this afternoon", "tonight",
    "standup", "daily", "end of day", "eod",
})

# Default intent -> directory mapping (overridden by backend config when available)
_DEFAULT_DIR_MAP = {
    "person": "people",
    "idea": "ideas",
    "project": "projects",
    "learning": "learning",
    "resource": "resources",
    "daily": "daily",
}

# Cached person name -> relative path mapping per vault
_person_cache: dict[Path, dict[str, str]] = {}
_person_cache_lock = threading.Lock()


def invalidate_person_cache(vault: Path) -> None:
    """Clear the person cache for a vault. Call when people/ files change."""
    with _person_cache_lock:
        _person_cache.pop(vault.resolve(), None)


def _load_person_cache(vault: Path, people_dir: str = "people") -> dict[str, str]:
    """Build or return cached name -> relative path mapping."""
    resolved = vault.resolve()
    if resolved in _person_cache:
        return _person_cache[resolved]

    with _person_cache_lock:
        if resolved in _person_cache:
            return _person_cache[resolved]

        mapping: dict[str, str] = {}
        # nosemgrep: semgrep.alaya-path-traversal -- people_dir from backend config, validated below
        people_path = (vault / people_dir).resolve()
        if not people_path.is_relative_to(vault.resolve()):
            return mapping
        if people_path.is_dir():
            for md_file in people_path.glob("*.md"):
                try:
                    content = md_file.read_text()
                except OSError:
                    continue
                meta = parse_note(content)
                name = meta.title.strip()
                if name:
                    mapping[name] = str(md_file.relative_to(vault))

        _person_cache[resolved] = mapping
        return mapping


def _detect_person(text: str, vault: Path, people_dir: str = "people") -> str | None:
    """Return relative path to a matching person note, or None."""
    people = _load_person_cache(vault, people_dir)
    for name, rel_path in people.items():
        if re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE):
            return rel_path
    return None


def _detect_daily(text: str) -> bool:
    """Return True if text contains a daily trigger phrase."""
    lower = text.lower()
    for trigger in _DAILY_TRIGGERS:
        if re.search(r"\b" + re.escape(trigger) + r"\b", lower):
            return True
    return False


def _find_matching_note(text: str, vault: Path) -> dict | None:
    """Find a semantically similar note above threshold, or None."""
    try:
        from alaya.tools.search import _run_hybrid_search, _hybrid_search_available

        if not _hybrid_search_available(vault):
            return None
        results = _run_hybrid_search(text, vault, limit=3)
        if results and results[0]["score"] >= _MATCH_THRESHOLD:
            return results[0]
    except Exception:
        pass
    return None


def _ensure_daily_note(vault: Path, daily_dir: str = "daily") -> str:
    """Return relative path to today's daily note, creating it if needed."""
    today = date.today().isoformat()
    rel_path = f"{daily_dir}/{today}.md"
    full_path = vault / rel_path

    if full_path.exists():
        return rel_path

    return create_note(
        title=today,
        directory=daily_dir,
        tags=[],
        body="",
        vault=vault,
        template="daily",
    )


def _derive_title(text: str, max_words: int = 6) -> str:
    """Derive a short title from the first sentence of text."""
    first_sentence = re.split(r"[.!?\n]", text, maxsplit=1)[0].strip()
    words = first_sentence.split()[:max_words]
    return " ".join(words) if words else "untitled"


def _infer_directory(intent: str | None, dir_map: dict[str, str] | None = None, default: str = "ideas") -> str:
    """Map an intent string to a vault directory."""
    mapping = dir_map or _DEFAULT_DIR_MAP
    if intent and intent in mapping:
        return mapping[intent]
    return default


def _append_to_section_or_eof(
    rel_path: str, text: str, vault: Path, section: str, dated: bool = False,
) -> None:
    """Append text under a section header, falling back to EOF if section missing."""
    try:
        append_to_note(rel_path, text, vault, section_header=section, dated=dated)
    except ValueError:
        # Section not found -- append at end of file
        append_to_note(rel_path, text, vault, dated=dated)


def smart_capture(
    text: str, vault: Path, intent: str | None = None, fallback: str = "inbox",
    dir_map: dict[str, str] | None = None,
    people_dir: str = "people",
    daily_dir: str = "daily",
    default_capture_dir: str = "ideas",
) -> str:
    """Capture text to the vault, routing automatically to the right note.

    Returns a confirmation string describing where text was captured.
    """
    # Step 1: Person routing
    if intent == "person" or not intent:
        person_path = _detect_person(text, vault, people_dir)
        if person_path:
            _append_to_section_or_eof(person_path, text, vault, "Notes", dated=True)
            return f"Appended to `{person_path}` (person match)."

    # Step 2: Daily routing
    if intent == "daily" or (not intent and _detect_daily(text)):
        daily_path = _ensure_daily_note(vault, daily_dir)
        _append_to_section_or_eof(daily_path, text, vault, "Notes", dated=False)
        return f"Appended to `{daily_path}` (daily note)."

    # Step 3: Topic match via semantic search
    if not intent:
        match = _find_matching_note(text, vault)
        if match:
            append_to_note(match["path"], text, vault, dated=True)
            return f"Appended to `{match['path']}` (topic match, score={match['score']:.2f})."

    # Step 4: Fallback
    if fallback == "create":
        title = _derive_title(text)
        directory = _infer_directory(intent, dir_map, default_capture_dir)
        path = create_note(
            title=title,
            directory=directory,
            tags=[],
            body=text,
            vault=vault,
        )
        return f"Created `{path}` (new note)."

    # Default: inbox
    return capture_to_inbox(text, vault)


# --- FastMCP tool registration ---

def _register(mcp: FastMCP, vault: Path, backend=None) -> None:
    # Extract config from backend if available
    if backend:
        _dir_map = backend.config.directory_map
        _people_dir = backend.config.people_dir
        _daily_dir = backend.config.daily_dir
        _default_capture = backend.config.default_capture_dir
    else:
        _dir_map = _DEFAULT_DIR_MAP
        _people_dir = "people"
        _daily_dir = "daily"
        _default_capture = "ideas"

    @mcp.tool()
    def smart_capture_tool(
        text: str,
        intent: str = "",
        fallback: str = "",
    ) -> str:
        """Capture a thought to the vault. Routes automatically to the right note.

        Preserves text verbatim -- never summarizes or paraphrases.
        Detects person mentions, topic matches, and daily note patterns.
        Appends to existing notes when a strong match is found.

        intent: optional hint -- "person", "daily", "idea", "topic", or empty for auto-detect.
        fallback: when no match found -- "inbox" (default) or "create" (new note in ideas/).
        """
        try:
            return smart_capture(
                text,
                vault,
                intent=intent or None,
                fallback=fallback or "inbox",
                dir_map=_dir_map,
                people_dir=_people_dir,
                daily_dir=_daily_dir,
                default_capture_dir=_default_capture,
            )
        except (FileNotFoundError, ValueError) as e:
            return error(INVALID_ARGUMENT, str(e))
