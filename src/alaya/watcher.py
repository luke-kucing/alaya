"""Watchdog file watcher: debounce vault changes, sync LanceDB, trigger raw/ ingestion."""
from __future__ import annotations

import threading
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from alaya.index.embedder import chunk_note, embed_chunks
from alaya.index.store import upsert_note, delete_note_from_index, VaultStore
from alaya.tools.ingest import ingest

_IGNORED_DIRS = {".zk", ".git", ".venv"}
_INGESTIBLE_SUFFIXES = {".pdf", ".md", ".txt"}
_DEBOUNCE_SECONDS = 2.0


class VaultEventHandler(FileSystemEventHandler):
    """Handle file system events in the vault.

    - .md file created/modified → upsert into LanceDB
    - .md file deleted → remove from LanceDB
    - file created in raw/ → trigger ingest
    - directories and non-text files → ignored
    """

    def __init__(self, vault: Path, store: VaultStore) -> None:
        super().__init__()
        self.vault = vault
        self.store = store
        self._timers: dict[str, threading.Timer] = {}

    def _is_ignored(self, path: str) -> bool:
        parts = Path(path).parts
        return any(d in parts for d in _IGNORED_DIRS)

    def _relative(self, path: str) -> str:
        return str(Path(path).relative_to(self.vault))

    def _debounced_upsert(self, src_path: str) -> None:
        """Schedule an upsert with debounce — resets the timer on repeated events."""
        if src_path in self._timers:
            self._timers[src_path].cancel()
        timer = threading.Timer(_DEBOUNCE_SECONDS, self._do_upsert, args=[src_path])
        self._timers[src_path] = timer
        timer.start()

    def _do_upsert(self, src_path: str) -> None:
        self._timers.pop(src_path, None)
        try:
            path = Path(src_path)
            if not path.exists():
                return
            content = path.read_text()
            rel = self._relative(src_path)
            chunks = chunk_note(rel, content)
            embeddings = embed_chunks(chunks)
            upsert_note(rel, chunks, embeddings, self.store)
        except Exception:
            pass

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
            delete_note_from_index(rel, self.store)

    def _trigger_ingest(self, src_path: str) -> None:
        """Fire-and-forget ingest for a file dropped into raw/."""
        def _run():
            try:
                ingest(src_path, vault=self.vault)
            except Exception:
                pass

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()


def start_watcher(vault: Path, store: VaultStore) -> Observer:
    """Start the watchdog observer and return it (caller is responsible for stop())."""
    handler = VaultEventHandler(vault=vault, store=store)
    observer = Observer()
    observer.schedule(handler, str(vault), recursive=True)
    observer.start()
    return observer
