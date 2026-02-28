"""Unit tests for the file watcher — filesystem events are simulated."""
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from alaya.watcher import VaultEventHandler, start_watcher


class TestVaultEventHandler:
    def _make_handler(self, vault: Path) -> VaultEventHandler:
        mock_store = MagicMock()
        return VaultEventHandler(vault=vault, store=mock_store)

    def test_md_file_created_triggers_upsert(self, vault: Path) -> None:
        handler = self._make_handler(vault)
        src_path = str(vault / "projects/new-note.md")
        (vault / "projects/new-note.md").write_text("---\ntitle: new-note\ndate: 2026-02-28\n---\n\nContent.\n")

        # bypass debounce by calling _do_upsert directly
        with patch("alaya.watcher.upsert_note") as mock_upsert, \
             patch("alaya.watcher.chunk_note", return_value=[MagicMock()]), \
             patch("alaya.watcher.embed_chunks", return_value=[MagicMock()]):
            handler._do_upsert(src_path)
            mock_upsert.assert_called_once()

    def test_md_file_modified_triggers_upsert(self, vault: Path) -> None:
        handler = self._make_handler(vault)
        src_path = str(vault / "projects/second-brain.md")

        # bypass debounce by calling _do_upsert directly
        with patch("alaya.watcher.upsert_note") as mock_upsert, \
             patch("alaya.watcher.chunk_note", return_value=[MagicMock()]), \
             patch("alaya.watcher.embed_chunks", return_value=[MagicMock()]):
            handler._do_upsert(src_path)
            mock_upsert.assert_called_once()

    def test_md_file_deleted_triggers_delete(self, vault: Path) -> None:
        handler = self._make_handler(vault)
        event = MagicMock()
        event.is_directory = False
        event.src_path = str(vault / "projects/second-brain.md")

        with patch("alaya.watcher.delete_note_from_index") as mock_delete:
            handler.on_deleted(event)
            mock_delete.assert_called_once()

    def test_non_md_file_ignored(self, vault: Path) -> None:
        handler = self._make_handler(vault)
        event = MagicMock()
        event.is_directory = False
        event.src_path = str(vault / "raw/image.png")

        with patch("alaya.watcher.upsert_note") as mock_upsert:
            handler.on_created(event)
            mock_upsert.assert_not_called()

    def test_zk_dir_ignored(self, vault: Path) -> None:
        handler = self._make_handler(vault)
        event = MagicMock()
        event.is_directory = False
        event.src_path = str(vault / ".zk/notebook.db")

        with patch("alaya.watcher.upsert_note") as mock_upsert:
            handler.on_modified(event)
            mock_upsert.assert_not_called()

    def test_pdf_in_raw_triggers_ingest(self, vault: Path) -> None:
        handler = self._make_handler(vault)
        event = MagicMock()
        event.is_directory = False
        src_path = str(vault / "raw/paper.pdf")
        event.src_path = src_path
        (vault / "raw").mkdir(exist_ok=True)
        (vault / "raw/paper.pdf").write_bytes(b"%PDF-1.4 fake")

        # patch ingest at the module level where watcher imported it
        with patch("alaya.watcher.ingest") as mock_ingest:
            # call _trigger_ingest directly to avoid thread timing issues
            handler._trigger_ingest(src_path)
            import time; time.sleep(0.1)  # let the daemon thread run
            mock_ingest.assert_called_once()

    def test_stop_waits_for_ingest_threads(self, vault: Path) -> None:
        """stop() must join all in-flight ingest threads before returning."""
        import time
        handler = self._make_handler(vault)
        completed = []

        def slow_ingest(src, vault):
            time.sleep(0.05)
            completed.append(src)

        src_path = str(vault / "raw/paper.pdf")
        (vault / "raw").mkdir(exist_ok=True)
        (vault / "raw/paper.pdf").write_bytes(b"%PDF-1.4 fake")

        with patch("alaya.watcher.ingest", side_effect=slow_ingest):
            handler._trigger_ingest(src_path)
            # thread is running — completed is still empty
            assert completed == []
            handler.stop(timeout=5.0)
            # after stop(), the thread must have finished
            assert completed == [src_path]

    def test_stop_warns_on_slow_thread(self, vault: Path) -> None:
        """stop() logs a warning if a thread exceeds the timeout."""
        import time
        handler = self._make_handler(vault)

        def hung_ingest(src, vault):
            time.sleep(10)

        src_path = str(vault / "raw/hung.pdf")
        (vault / "raw").mkdir(exist_ok=True)
        (vault / "raw/hung.pdf").write_bytes(b"%PDF-1.4 fake")

        with patch("alaya.watcher.ingest", side_effect=hung_ingest), \
             patch("alaya.watcher.logger") as mock_log:
            handler._trigger_ingest(src_path)
            handler.stop(timeout=0.05)  # expire immediately
            mock_log.warning.assert_called_once()
            # cleanup: thread is daemon so it won't block test exit

    def test_directory_events_ignored(self, vault: Path) -> None:
        handler = self._make_handler(vault)
        event = MagicMock()
        event.is_directory = True
        event.src_path = str(vault / "projects/new-dir")

        with patch("alaya.watcher.upsert_note") as mock_upsert:
            handler.on_created(event)
            mock_upsert.assert_not_called()

    def test_upsert_error_is_logged_not_raised(self, vault: Path) -> None:
        handler = self._make_handler(vault)
        src_path = str(vault / "projects/second-brain.md")

        with patch("alaya.watcher.chunk_note", side_effect=RuntimeError("embed failed")), \
             patch("alaya.watcher.logger") as mock_log:
            # Must not raise — watcher must stay alive
            handler._do_upsert(src_path)
            mock_log.warning.assert_called_once()

    def test_ingest_error_is_logged_not_raised(self, vault: Path) -> None:
        handler = self._make_handler(vault)
        src_path = str(vault / "raw/broken.pdf")
        (vault / "raw").mkdir(exist_ok=True)
        (vault / "raw/broken.pdf").write_bytes(b"bad")

        with patch("alaya.watcher.ingest", side_effect=RuntimeError("parse failed")), \
             patch("alaya.watcher.logger") as mock_log:
            handler._trigger_ingest(src_path)
            import time; time.sleep(0.1)
            mock_log.warning.assert_called_once()


class TestDebounce:
    """Tests for debounce logic — uses a very short interval to keep tests fast."""

    def _make_handler(self, vault: Path) -> "VaultEventHandler":
        mock_store = MagicMock()
        return VaultEventHandler(vault=vault, store=mock_store, debounce_seconds=0.05)

    def test_single_event_fires_upsert_once(self, vault: Path) -> None:
        import time
        handler = self._make_handler(vault)
        src_path = str(vault / "projects/second-brain.md")

        with patch("alaya.watcher.upsert_note") as mock_upsert, \
             patch("alaya.watcher.chunk_note", return_value=[MagicMock()]), \
             patch("alaya.watcher.embed_chunks", return_value=[MagicMock()]):
            handler._debounced_upsert(src_path)
            time.sleep(0.15)  # wait past debounce
            mock_upsert.assert_called_once()

    def test_rapid_events_fire_upsert_once(self, vault: Path) -> None:
        import time
        handler = self._make_handler(vault)
        src_path = str(vault / "projects/second-brain.md")

        with patch("alaya.watcher.upsert_note") as mock_upsert, \
             patch("alaya.watcher.chunk_note", return_value=[MagicMock()]), \
             patch("alaya.watcher.embed_chunks", return_value=[MagicMock()]):
            # rapid-fire 5 events — debounce resets each time
            for _ in range(5):
                handler._debounced_upsert(src_path)
            time.sleep(0.15)  # wait past debounce
            mock_upsert.assert_called_once()

    def test_different_files_have_independent_debounce(self, vault: Path) -> None:
        import time
        handler = self._make_handler(vault)
        path_a = str(vault / "projects/second-brain.md")
        path_b = str(vault / "resources/kubernetes-notes.md")

        with patch("alaya.watcher.upsert_note") as mock_upsert, \
             patch("alaya.watcher.chunk_note", return_value=[MagicMock()]), \
             patch("alaya.watcher.embed_chunks", return_value=[MagicMock()]):
            handler._debounced_upsert(path_a)
            handler._debounced_upsert(path_b)
            time.sleep(0.15)
            assert mock_upsert.call_count == 2

    def test_timer_cleaned_up_after_firing(self, vault: Path) -> None:
        import time
        handler = self._make_handler(vault)
        src_path = str(vault / "projects/second-brain.md")

        with patch("alaya.watcher.upsert_note"), \
             patch("alaya.watcher.chunk_note", return_value=[MagicMock()]), \
             patch("alaya.watcher.embed_chunks", return_value=[MagicMock()]):
            handler._debounced_upsert(src_path)
            assert src_path in handler._timers
            time.sleep(0.15)
            # timer entry removed after firing
            assert src_path not in handler._timers
