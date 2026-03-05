"""Unit tests for audit logging."""
import json
import threading
from pathlib import Path

import pytest

from alaya.audit import log_tool_call, _truncate_args


class TestTruncateArgs:
    def test_short_values_unchanged(self) -> None:
        args = {"text": "hello", "count": 5}
        result = _truncate_args(args)
        assert result == args

    def test_long_string_truncated(self) -> None:
        args = {"text": "x" * 300}
        result = _truncate_args(args)
        assert len(result["text"]) == 203  # 200 + "..."
        assert result["text"].endswith("...")

    def test_non_string_values_unchanged(self) -> None:
        args = {"count": 42, "flag": True, "items": [1, 2, 3]}
        result = _truncate_args(args)
        assert result == args


class TestLogToolCall:
    def test_writes_jsonl_entry(self, vault: Path) -> None:
        log_tool_call(vault, "search_notes", {"query": "test"}, "Found 3 results", 12.5)

        audit_file = vault / ".zk" / "audit.jsonl"
        assert audit_file.exists()

        entry = json.loads(audit_file.read_text().strip())
        assert entry["tool"] == "search_notes"
        assert entry["args"] == {"query": "test"}
        assert entry["status"] == "ok"
        assert entry["duration_ms"] == 12.5
        assert "Found 3 results" in entry["summary"]
        assert "ts" in entry

    def test_error_status_detected(self, vault: Path) -> None:
        log_tool_call(vault, "get_note", {"path": "bad"}, "ERROR [NOT_FOUND]: bad", 1.0)

        audit_file = vault / ".zk" / "audit.jsonl"
        entry = json.loads(audit_file.read_text().strip())
        assert entry["status"] == "error"

    def test_multiple_entries_appended(self, vault: Path) -> None:
        log_tool_call(vault, "tool_a", {}, "ok", 1.0)
        log_tool_call(vault, "tool_b", {}, "ok", 2.0)

        audit_file = vault / ".zk" / "audit.jsonl"
        lines = audit_file.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["tool"] == "tool_a"
        assert json.loads(lines[1])["tool"] == "tool_b"

    def test_summary_truncated(self, vault: Path) -> None:
        long_summary = "x" * 500
        log_tool_call(vault, "test", {}, long_summary, 1.0)

        audit_file = vault / ".zk" / "audit.jsonl"
        entry = json.loads(audit_file.read_text().strip())
        assert len(entry["summary"]) == 200

    def test_creates_zk_dir_if_missing(self, vault: Path) -> None:
        zk_dir = vault / ".zk"
        if zk_dir.exists():
            import shutil
            shutil.rmtree(zk_dir)

        log_tool_call(vault, "test", {}, "ok", 1.0)
        assert (vault / ".zk" / "audit.jsonl").exists()

    def test_thread_safety(self, vault: Path) -> None:
        """Multiple threads writing concurrently should not corrupt the file."""
        errors = []

        def _write(i: int) -> None:
            try:
                log_tool_call(vault, f"tool_{i}", {"i": i}, f"result {i}", float(i))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_write, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

        audit_file = vault / ".zk" / "audit.jsonl"
        lines = audit_file.read_text().strip().splitlines()
        assert len(lines) == 20

        # each line is valid JSON
        for line in lines:
            entry = json.loads(line)
            assert "tool" in entry
