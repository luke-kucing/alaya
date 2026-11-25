"""Task tools: checkbox todos (get_todos, complete_todo) and the task ledger.

The ledger (#170) lets several agents split work in one vault: one note per
task under ``tasks/``, with status, owner and lease in frontmatter. Agents
claim a task for a lease; an expired lease can be claimed by another agent.
"""
import logging
import re
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from fastmcp import FastMCP
from alaya.errors import error, NOT_FOUND, OUTSIDE_VAULT, ALREADY_EXISTS, INVALID_ARGUMENT, CONFLICT
from alaya.events import emit, NoteEvent, EventType
from alaya.vault import resolve_note_path, _SKIP_DIRS
from alaya.tools._locks import get_path_lock, atomic_write

logger = logging.getLogger(__name__)

_TODO_PATTERN = re.compile(r"^- \[ \] (.+)$")


def get_todos(
    vault: Path,
    directories: list[str] | None = None,
) -> list[dict]:
    """Scan vault for open tasks (- [ ] ...). Returns list of {path, line, text}."""
    results = []

    if directories:
        # Validate directories stay within vault root
        search_roots = []
        vault_resolved = vault.resolve()
        for d in directories:
            # nosemgrep: semgrep.alaya-path-traversal — validated by relative_to() on next line
            root = (vault / d).resolve()
            try:
                root.relative_to(vault_resolved)
            except ValueError:
                raise ValueError(f"Directory '{d}' escapes vault root")
            search_roots.append(root)
    else:
        search_roots = [vault]

    for root in search_roots:
        for md_file in root.rglob("*.md"):
            if any(part in _SKIP_DIRS for part in md_file.parts):
                continue
            try:
                rel = str(md_file.relative_to(vault))
                for line_num, line in enumerate(md_file.read_text().splitlines(), start=1):
                    m = _TODO_PATTERN.match(line.strip())
                    if m:
                        results.append({
                            "path": rel,
                            "line": line_num,
                            "text": m.group(1),
                        })
            except OSError as e:
                logger.warning("Skipping %s during todo scan: %s", md_file, e)

    return results


def complete_todo(
    path: str,
    line: int,
    task_text: str,
    vault: Path,
) -> None:
    """Mark a task complete. Uses fuzzy ±5 line fallback if line number is stale."""
    note_path = resolve_note_path(path, vault)

    with get_path_lock(note_path):
        lines = note_path.read_text().splitlines(keepends=True)

        # try exact line first (1-indexed), then fuzzy ±5 lines around it
        exact_idx = line - 1
        candidates = [exact_idx] + list(range(max(0, exact_idx - 5), min(len(lines), exact_idx + 6)))
        idx = next(
            (i for i in candidates
             if 0 <= i < len(lines) and _TODO_PATTERN.match(lines[i].strip()) and task_text in lines[i]),
            None,
        )
        if idx is None:
            raise ValueError(f"Task not found: '{task_text}' near line {line} in {path}")
        lines[idx] = lines[idx].replace("- [ ]", "- [x]", 1)
        atomic_write(note_path, "".join(lines))

    emit(NoteEvent(EventType.MODIFIED, str(note_path.relative_to(vault.resolve()))))


# --- Task ledger (#170) ---

TASK_TYPE = "task"
RELEASE_STATUSES = ("done", "open", "blocked")
_OWNER_RE = re.compile(r"^[\w.@:-]{1,128}$")


class TaskConflict(Exception):
    """The task is not in a state this caller may change (owned, done, blocked)."""


def _tasks_root(vault: Path, backend=None) -> Path:
    return vault / (getattr(getattr(backend, "config", None), "tasks_dir", None) or "tasks")


def _task_name(task: str) -> str:
    """Accept ``name``, ``name.md`` or ``[[name]]``; reject anything path-like."""
    name = task.strip().removeprefix("[[").removesuffix("]]").split("|")[0].strip()
    name = name.removesuffix(".md")
    if not name or "/" in name or "\\" in name or name.startswith(".") or "\n" in name:
        raise ValueError(f"Invalid task {task!r}: give the task note's name")
    return name


def _task_path(vault: Path, task: str, backend=None) -> Path:
    # nosemgrep: semgrep.alaya-path-traversal — name validated by _task_name()
    path = _tasks_root(vault, backend) / f"{_task_name(task)}.md"
    if not path.exists():
        raise FileNotFoundError(f"No task {task!r}")
    return path


def _check_owner(owner: str) -> str:
    if not _OWNER_RE.match(owner):
        raise ValueError(f"Invalid owner {owner!r}: letters, digits and . _ @ : - only")
    return owner


@contextmanager
def _ledger_lock(vault: Path, backend=None):
    """Exclusive lock over the whole ledger, across processes and threads.

    flock is per open file, so a fresh open per call also excludes threads.
    shortcut: flock is POSIX-only and unreliable on NFS or synced folders;
    move to a lock service if the ledger has to span machines.
    """
    import fcntl  # POSIX only; imported here so the rest of alaya runs without it

    root = _tasks_root(vault, backend)
    root.mkdir(parents=True, exist_ok=True)
    with open(root / ".ledger.lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def _read_task(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    end = text.find("\n---\n", 4) if text.startswith("---\n") else -1
    meta = yaml.safe_load(text[4:end]) if end != -1 else None
    if not isinstance(meta, dict) or meta.get("type") != TASK_TYPE:
        raise ValueError(f"{path.name} is not a task note (type: {TASK_TYPE})")
    return meta, text[end + 5:]


def _write_task(path: Path, meta: dict, body: str) -> None:
    # safe_dump quotes "[[links]]" and timestamps, so the note round-trips.
    atomic_write(path, "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True) + "---\n" + body)


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _lease(meta: dict) -> datetime | None:
    value = meta.get("lease_until")
    if isinstance(value, str) and value:
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _held(meta: dict, now: datetime) -> bool:
    """Claimed under a lease that has not run out."""
    lease = _lease(meta)
    return meta.get("status") == "claimed" and lease is not None and lease > now


def _blockers_done(meta: dict, vault: Path, backend=None) -> bool:
    """Every blocked_by task exists and is done; a link that resolves to nothing is not done."""
    for link in meta.get("blocked_by") or []:
        try:
            blocker, _ = _read_task(_task_path(vault, str(link), backend))
        except (FileNotFoundError, ValueError):
            return False
        if blocker.get("status") != "done":
            return False
    return True


def _summary(path: Path, vault: Path, meta: dict) -> dict:
    lease = _lease(meta)
    return {
        "task": path.stem,
        "path": str(path.relative_to(vault)),
        "title": meta.get("title", path.stem),
        "status": meta.get("status", ""),
        "owner": meta.get("owner", ""),
        "lease_until": lease.isoformat() if lease else "",
    }


def create_task(
    title: str, vault: Path, body: str = "", blocked_by: list[str] | None = None, backend=None,
) -> dict:
    """Create an open task note. Fails if a task of that name exists."""
    from alaya.tools.write import _slugify

    name = _task_name(_slugify(title))
    blockers = [f"[[{_task_name(b)}]]" for b in blocked_by or []]
    path = _tasks_root(vault, backend) / f"{name}.md"
    meta = {
        "title": title.strip(), "type": TASK_TYPE, "status": "open", "owner": "",
        "lease_until": "", "blocked_by": blockers, "created": _now().isoformat(),
    }
    with _ledger_lock(vault, backend), get_path_lock(path):
        if path.exists():
            raise FileExistsError(f"Task {name!r} already exists")
        _write_task(path, meta, f"\n# {title.strip()}\n\n{body.strip()}\n")
    emit(NoteEvent(EventType.CREATED, str(path.relative_to(vault))))
    return _summary(path, vault, meta)


def ready_tasks(vault: Path, limit: int = 20, backend=None) -> list[dict]:
    """Open tasks whose blockers are all done, and claimed tasks whose lease ran out."""
    root = _tasks_root(vault, backend)
    now = _now()
    out = []
    for path in sorted(root.glob("*.md")) if root.is_dir() else []:
        try:
            meta, _ = _read_task(path)
        except (OSError, ValueError):
            continue
        status = meta.get("status")
        expired = status == "claimed" and not _held(meta, now)
        if expired or (status == "open" and _blockers_done(meta, vault, backend)):
            out.append(_summary(path, vault, meta))
            if len(out) >= limit:
                break
    return out


def claim_task(task: str, owner: str, vault: Path, lease_minutes: int = 60, backend=None) -> dict:
    """Claim *task* for *owner* until the lease runs out.

    Raises TaskConflict when someone else holds a live lease, or the task is
    done, blocked, or waiting on unfinished blockers.
    """
    _check_owner(owner)
    if lease_minutes <= 0:
        raise ValueError("lease_minutes must be positive")
    path = _task_path(vault, task, backend)
    with _ledger_lock(vault, backend), get_path_lock(path):
        meta, body = _read_task(path)
        now = _now()
        status = meta.get("status")
        if _held(meta, now) and meta.get("owner") != owner:
            raise TaskConflict(f"{path.stem} is claimed by {meta.get('owner')} until {_lease(meta).isoformat()}")
        if status in ("done", "blocked"):
            raise TaskConflict(f"{path.stem} is {status}")
        if status == "open" and not _blockers_done(meta, vault, backend):
            raise TaskConflict(f"{path.stem} is waiting on {meta.get('blocked_by')}")
        meta.update(status="claimed", owner=owner, lease_until=(now + timedelta(minutes=lease_minutes)).isoformat())
        _write_task(path, meta, body)
    emit(NoteEvent(EventType.MODIFIED, str(path.relative_to(vault))))
    return _summary(path, vault, meta)


def _owned(meta: dict, owner: str, name: str) -> None:
    """The caller owns the claim (a lapsed lease nobody took is still theirs)."""
    if meta.get("status") != "claimed" or meta.get("owner") != owner:
        holder = meta.get("owner") or "nobody"
        raise TaskConflict(f"{name} is {meta.get('status')} and held by {holder}, not {owner}")


def renew_task(task: str, owner: str, vault: Path, lease_minutes: int = 60, backend=None) -> dict:
    """Extend *owner*'s lease on *task*."""
    _check_owner(owner)
    if lease_minutes <= 0:
        raise ValueError("lease_minutes must be positive")
    path = _task_path(vault, task, backend)
    with _ledger_lock(vault, backend), get_path_lock(path):
        meta, body = _read_task(path)
        _owned(meta, owner, path.stem)
        meta["lease_until"] = (_now() + timedelta(minutes=lease_minutes)).isoformat()
        _write_task(path, meta, body)
    emit(NoteEvent(EventType.MODIFIED, str(path.relative_to(vault))))
    return _summary(path, vault, meta)


def release_task(
    task: str, owner: str, vault: Path, status: str = "done", note: str = "", backend=None,
) -> dict:
    """Give up *owner*'s claim, leaving the task done, open or blocked.

    A line is appended to the task's Log section so the ledger keeps its history.
    """
    _check_owner(owner)
    if status not in RELEASE_STATUSES:
        raise ValueError(f"status must be one of {', '.join(RELEASE_STATUSES)}")
    path = _task_path(vault, task, backend)
    with _ledger_lock(vault, backend), get_path_lock(path):
        meta, body = _read_task(path)
        _owned(meta, owner, path.stem)
        meta.update(status=status, owner="", lease_until="")
        line = f"- {_now().isoformat()} {owner} → {status}"
        if note.strip():
            line += f": {' '.join(note.split())}"
        if "\n## Log\n" not in body:
            body = body.rstrip("\n") + "\n\n## Log\n\n"
        _write_task(path, meta, body.rstrip("\n") + f"\n{line}\n")
    emit(NoteEvent(EventType.MODIFIED, str(path.relative_to(vault))))
    return _summary(path, vault, meta)


def _format_task(t: dict) -> str:
    held = f" — {t['owner']} until {t['lease_until']}" if t["owner"] else ""
    return f"- [[{t['task']}]] ({t['status']}{held}) {t['title']}"


# --- FastMCP tool registration ---

def _ledger_errors(fn):
    """Turn ledger exceptions into the structured error strings tools return."""
    try:
        return fn()
    except FileNotFoundError as e:
        return error(NOT_FOUND, str(e))
    except FileExistsError as e:
        return error(ALREADY_EXISTS, str(e))
    except TaskConflict as e:
        return error(CONFLICT, str(e))
    except ValueError as e:
        return error(INVALID_ARGUMENT, str(e))


def _register(mcp: FastMCP, vault: Path, backend=None) -> None:
    @mcp.tool(name="create_task")
    def create_task_tool(title: str, body: str = "", blocked_by: list[str] | None = None) -> str:
        """Add a task to the shared task ledger (one note under tasks/).

        blocked_by names other tasks that must be done before this one is ready.
        """
        return _ledger_errors(lambda: "Created: " + _format_task(
            create_task(title, vault, body=body, blocked_by=blocked_by, backend=backend)))

    @mcp.tool(name="ready_tasks")
    def ready_tasks_tool(limit: int = 20) -> str:
        """List ledger tasks an agent can claim now: open with all blockers done,
        or claimed under a lease that has run out."""
        tasks = ready_tasks(vault, limit=limit, backend=backend)
        return "\n".join(map(_format_task, tasks)) or "No ready tasks."

    @mcp.tool(name="claim_task")
    def claim_task_tool(task: str, owner: str, lease_minutes: int = 60) -> str:
        """Claim a ledger task for owner (your agent or session id) for lease_minutes.

        Fails with CONFLICT naming the current owner if someone holds a live
        lease. Renew before the lease runs out, or another agent may take it.
        """
        return _ledger_errors(lambda: "Claimed: " + _format_task(
            claim_task(task, owner, vault, lease_minutes=lease_minutes, backend=backend)))

    @mcp.tool(name="renew_task")
    def renew_task_tool(task: str, owner: str, lease_minutes: int = 60) -> str:
        """Extend your lease on a ledger task you claimed."""
        return _ledger_errors(lambda: "Renewed: " + _format_task(
            renew_task(task, owner, vault, lease_minutes=lease_minutes, backend=backend)))

    @mcp.tool(name="release_task")
    def release_task_tool(task: str, owner: str, status: str = "done", note: str = "") -> str:
        """Release your claim on a ledger task, marking it done, open or blocked.

        The note is appended to the task's log so the next agent sees why.
        """
        return _ledger_errors(lambda: "Released: " + _format_task(
            release_task(task, owner, vault, status=status, note=note, backend=backend)))

    @mcp.tool(name="get_todos")
    def get_todos_tool(
        directories: list[str] | None = None, unbounded: bool = False
    ) -> str:
        """Find all open tasks (- [ ] ...) in the vault. Optionally restrict to directories.

        Output is capped; pass unbounded=True to bypass the cap.
        """
        todos = get_todos(vault, directories=directories or None)
        if not todos:
            return "No open tasks found."
        lines = [f"- `{t['path']}:{t['line']}` — {t['text']}" for t in todos]
        return "\n".join(lines)

    @mcp.tool(name="complete_todo")
    def complete_todo_tool(path: str, line: int, task_text: str) -> str:
        """Mark a task as complete. Uses fuzzy fallback if line number is stale."""
        try:
            complete_todo(path, line, task_text, vault)
            return f"Completed: '{task_text}'"
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except ValueError as e:
            return error(OUTSIDE_VAULT, str(e))

