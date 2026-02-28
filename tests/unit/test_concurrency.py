"""Concurrent access tests for watcher and write tools."""
from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from alaya.watcher import VaultEventHandler


# --- Watcher concurrency ---

class TestWatcherConcurrency:
    def _make_handler(self, vault: Path) -> VaultEventHandler:
        return VaultEventHandler(vault=vault, store=MagicMock())

    def test_concurrent_mark_and_check_no_data_race(self, vault: Path) -> None:
        """mark_indexed and _was_recently_indexed called concurrently must not crash."""
        handler = self._make_handler(vault)
        errors = []

        def mark():
            try:
                for _ in range(100):
                    handler.mark_indexed("projects/foo.md")
            except Exception as e:
                errors.append(e)

        def check():
            try:
                for _ in range(100):
                    handler._was_recently_indexed("projects/foo.md")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=mark), threading.Thread(target=check)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent access raised: {errors}"

    def test_debounce_rapid_events_single_upsert(self, vault: Path) -> None:
        """10 rapid on_modified events on the same file must result in exactly 1 upsert."""
        import time
        handler = VaultEventHandler(vault=vault, store=MagicMock(), debounce_seconds=0.05)
        src_path = str(vault / "projects/second-brain.md")

        with patch("alaya.watcher.upsert_note") as mock_upsert, \
             patch("alaya.watcher.chunk_note", return_value=[MagicMock()]), \
             patch("alaya.watcher.embed_chunks", return_value=[MagicMock()]):

            for _ in range(10):
                handler._debounced_upsert(src_path)

            time.sleep(0.15)
            assert mock_upsert.call_count == 1

    def test_concurrent_debounce_different_files(self, vault: Path) -> None:
        """Concurrent debounced upserts on different files must each fire exactly once."""
        import time
        handler = VaultEventHandler(vault=vault, store=MagicMock(), debounce_seconds=0.05)
        paths = [
            str(vault / "projects/second-brain.md"),
            str(vault / "resources/kubernetes-notes.md"),
            str(vault / "ideas/voice-capture.md"),
        ]

        with patch("alaya.watcher.upsert_note") as mock_upsert, \
             patch("alaya.watcher.chunk_note", return_value=[MagicMock()]), \
             patch("alaya.watcher.embed_chunks", return_value=[MagicMock()]):

            barrier = threading.Barrier(len(paths))

            def trigger(p):
                barrier.wait()
                handler._debounced_upsert(p)

            threads = [threading.Thread(target=trigger, args=(p,)) for p in paths]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            time.sleep(0.15)
            assert mock_upsert.call_count == len(paths)


# --- Write tool concurrency ---

class TestWriteConcurrency:
    def test_concurrent_append_no_data_loss(self, vault: Path) -> None:
        """Two threads appending to the same note must not lose either append."""
        from alaya.tools.write import append_to_note

        note_path = "projects/second-brain.md"

        barrier = threading.Barrier(2)
        errors = []

        def append(text):
            try:
                barrier.wait()
                append_to_note(note_path, text, vault)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=append, args=("THREAD_A_CONTENT",))
        t2 = threading.Thread(target=append, args=("THREAD_B_CONTENT",))
        t1.start(); t2.start()
        t1.join(); t2.join()

        assert not errors, f"Concurrent append raised: {errors}"

        content = (vault / note_path).read_text()
        assert "THREAD_A_CONTENT" in content
        assert "THREAD_B_CONTENT" in content

    def test_concurrent_create_different_notes_no_interference(self, vault: Path) -> None:
        """Two threads creating different notes must both succeed."""
        from alaya.tools.write import create_note

        results = []
        errors = []
        barrier = threading.Barrier(2)

        def create(title):
            try:
                barrier.wait()
                path = create_note(title, "ideas", [], "", vault)
                results.append(path)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=create, args=("concurrent note alpha",))
        t2 = threading.Thread(target=create, args=("concurrent note beta",))
        t1.start(); t2.start()
        t1.join(); t2.join()

        assert not errors, f"Concurrent create raised: {errors}"
        assert len(results) == 2
        assert (vault / results[0]).exists()
        assert (vault / results[1]).exists()
