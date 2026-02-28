"""Watchdog file watcher: debounce vault changes, sync LanceDB, trigger raw/ ingestion."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from alaya.index.embedder import chunk_note, embed_chunks
from alaya.index.store import upsert_note, delete_note_from_index, VaultStore
from alaya.tools.ingest import ingest

_IGNORED_DIRS = {".zk", ".git", ".venv"}
_INGESTIBLE_SUFFIXES = {".pdf", ".md", ".txt"}
_DEBOUNCE_SECONDS = 2.0
# How long (seconds) a path is considered "recently indexed" by the event system.
# 30s is conservative — covers slow embedding runs on large files.
_SKIP_WINDOW = 30.0


class VaultEventHandler(FileSystemEventHandler):
    """Handle file system events in the vault.

    - .md file created/modified -> upsert into LanceDB
    - .md file deleted -> remove from LanceDB
    - file created in raw/ -> trigger ingest
    - directories and non-text files -> ignored

    Paths recently indexed by the write-through event system are skipped
    to avoid redundant re-indexing.
    """

    def __init__(self, vault: Path, store: VaultStore, debounce_seconds: float = _DEBOUNCE_SECONDS) -> None:
        super().__init__()
        self.vault = vault
        self.store = store
        self._debounce_seconds = debounce_seconds
        self._timers: dict[str, threading.Timer] = {}
        self._recently_indexed: dict[str, float] = {}
        self._lock = threading.Lock()

    def mark_indexed(self, relative_path: str) -> None:
        """Mark a path as recently indexed by the event system."""
        with self._lock:
            self._recently_indexed[relative_path] = time.monotonic()

    def _was_recently_indexed(self, relative_path: str) -> bool:
        """Check if the event system already indexed this path recently.

        The read and age-check are both performed inside the lock so that a
        concurrent mark_indexed() call cannot slip in between them.
        Expired entries are removed inside the lock to keep the dict tidy.
        """
        with self._lock:
            ts = self._recently_indexed.get(relative_path)
            if ts is None:
                return False
            if (time.monotonic() - ts) < _SKIP_WINDOW:
                return True
            # expired — remove and let the watcher proceed
            del self._recently_indexed[relative_path]
            return False

    def _is_ignored(self, path: str) -> bool:
        parts = Path(path).parts
        return any(d in parts for d in _IGNORED_DIRS)

    def _relative(self, path: str) -> str:
        return str(Path(path).relative_to(self.vault))

    def _debounced_upsert(self, src_path: str) -> None:
        """Schedule an upsert with debounce — resets the timer on repeated events."""
        if src_path in self._timers:
            self._timers[src_path].cancel()
        timer = threading.Timer(self._debounce_seconds, self._do_upsert, args=[src_path])
        self._timers[src_path] = timer
        timer.start()

    def _do_upsert(self, src_path: str) -> None:
        self._timers.pop(src_path, None)
        try:
            path = Path(src_path)
            if not path.exists():
                return
            rel = self._relative(src_path)
            if self._was_recently_indexed(rel):
                logger.debug("Skipping watcher upsert for %s (already indexed by event)", rel)
                return
            content = path.read_text()
            chunks = chunk_note(rel, content)
            embeddings = embed_chunks(chunks)
            upsert_note(rel, chunks, embeddings, self.store)
        except Exception as e:
            logger.warning("Failed to upsert %s into index: %s", src_path, e)

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        src = event.src_path
        if self._is_ignored(src):
            return

        path = Path(src)
        suffix = path.suffix.lower()

        # raw/ drop-in: trigger ingest for supported types
        if "raw" in path.parts and suffix in _INGESTIBLE_SUFFIXES:
            self._trigger_ingest(src)
            return

        if suffix == ".md":
            self._debounced_upsert(src)

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        src = event.src_path
        if self._is_ignored(src):
            return
        if Path(src).suffix.lower() == ".md":
            self._debounced_upsert(src)

    def on_deleted(self, event) -> None:
        if event.is_directory:
            return
        src = event.src_path
        if self._is_ignored(src):
            return
        if Path(src).suffix.lower() == ".md":
            rel = self._relative(src)
            if not self._was_recently_indexed(rel):
                delete_note_from_index(rel, self.store)

    def _trigger_ingest(self, src_path: str) -> None:
        """Fire-and-forget ingest for a file dropped into raw/."""
        def _run():
            try:
                ingest(src_path, vault=self.vault)
            except Exception as e:
                logger.warning("Failed to ingest %s: %s", src_path, e)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()


def start_watcher(vault: Path, store: VaultStore) -> tuple[Observer, VaultEventHandler]:
    """Start the watchdog observer. Returns (observer, handler)."""
    handler = VaultEventHandler(vault=vault, store=store)
    observer = Observer()
    observer.schedule(handler, str(vault), recursive=True)
    observer.start()
    return observer, handler
