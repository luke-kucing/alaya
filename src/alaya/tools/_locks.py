"""Per-path file locks for atomic read-modify-write operations.

All vault file writes acquire a per-path lock so concurrent MCP tool calls
(FastMCP dispatches sync tools to a thread pool) cannot interleave reads and
writes on the same file.

Only protects within a single process — sufficient for the MCP server model.
"""
import os
import tempfile
import threading
from pathlib import Path

_registry_lock = threading.Lock()
_path_locks: dict[Path, threading.Lock] = {}


def get_path_lock(path: Path) -> threading.Lock:
    """Return the lock for *path*, creating it if needed.

    Uses path.resolve() so that relative and absolute references to the
    same file share a single lock.
    """
    resolved = path.resolve()
    with _registry_lock:
        if resolved not in _path_locks:
            _path_locks[resolved] = threading.Lock()
        return _path_locks[resolved]


def atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically via a sibling temp file.

    On POSIX, os.replace() is guaranteed atomic when src and dst are on the
    same filesystem (which is always true for a sibling temp file).
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        os.close(fd)
        tmp.write_text(content)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
