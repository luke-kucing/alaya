"""Unit tests for index health tracking."""
import pytest

from alaya.index import health


@pytest.fixture(autouse=True)
def reset_health():
    health.reset()
    yield
    health.reset()


def test_initial_state_has_no_failures():
    status = health.get_status()
    assert status["failed_paths"] == {}
    assert status["last_success_ago_seconds"] is None


def test_record_failure_adds_to_failed_paths():
    health.record_failure("projects/foo.md", "OSError: disk full")
    status = health.get_status()
    assert "projects/foo.md" in status["failed_paths"]
    assert "OSError: disk full" in status["failed_paths"]["projects/foo.md"]


def test_record_success_removes_from_failed_paths():
    health.record_failure("projects/foo.md", "some error")
    health.record_success("projects/foo.md")
    status = health.get_status()
    assert "projects/foo.md" not in status["failed_paths"]


def test_record_success_updates_last_success_timestamp():
    assert health.get_status()["last_success_ago_seconds"] is None
    health.record_success("projects/foo.md")
    assert health.get_status()["last_success_ago_seconds"] is not None


def test_multiple_failures_tracked_independently():
    health.record_failure("a.md", "err a")
    health.record_failure("b.md", "err b")
    status = health.get_status()
    assert len(status["failed_paths"]) == 2
    assert status["failed_paths"]["a.md"] == "err a"
    assert status["failed_paths"]["b.md"] == "err b"


def test_success_on_untracked_path_is_safe():
    # should not raise
    health.record_success("never/failed.md")
    assert health.get_status()["failed_paths"] == {}


def test_subsequent_failure_overwrites_previous_error():
    health.record_failure("projects/foo.md", "first error")
    health.record_failure("projects/foo.md", "second error")
    status = health.get_status()
    assert status["failed_paths"]["projects/foo.md"] == "second error"


def test_concurrent_access_no_data_race():
    """10 threads hammering record_failure/record_success/get_status must not crash."""
    import threading

    errors = []

    def worker(i):
        try:
            for _ in range(50):
                health.record_failure(f"path{i}.md", "err")
                health.record_success(f"path{i}.md")
                health.get_status()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent health access raised: {errors}"


class TestReport:
    """#162: vault_health shows lag, in-flight reindex, embedder and store."""

    @pytest.fixture
    def setup(self, tmp_path):
        import os
        import time
        from alaya.index.store import get_store, reset_store
        vault = tmp_path / "vault"
        vault.mkdir()
        for name in ("a", "b", "c"):
            (vault / f"{name}.md").write_text("# n\n")
            os.utime(vault / f"{name}.md", (time.time() - 600,) * 2)  # edited before the index
        store = get_store(vault)
        store._get_table()  # first index write
        yield vault, store
        reset_store()

    def test_no_lag_when_nothing_edited_since_index_write(self, setup):
        vault, store = setup
        out = health.report(vault, store)
        assert "Index lag: 0s (no notes edited since the last index write)" in out
        assert "Reindex in progress: no" in out
        assert "Embedder: fastembed " in out and " dims)" in out
        assert "Store: LanceDB" in out

    def test_counts_notes_edited_after_index_write(self, setup):
        import os
        vault, store = setup
        later = store.last_write_time() + 30
        os.utime(vault / "b.md", (later, later))
        n, lag = health.index_lag(vault, store.last_write_time())
        assert n == 1 and lag is not None
        assert "(1 notes edited since the last index write)" in health.report(vault, store)

    def test_shows_in_flight_reindex_and_migration(self, setup):
        import threading
        vault, store = setup
        release = threading.Event()
        t = threading.Thread(target=release.wait, name="alaya-schema-reindex", daemon=True)
        t.start()
        health.start_migration("old-model", "new-model", total=10)
        health.update_migration_progress(4)
        try:
            out = health.report(vault, store)
        finally:
            release.set()
            t.join()
        assert "Reindex in progress: yes (alaya-schema-reindex)" in out
        assert "Re-embed: 4/10 notes (old-model -> new-model)" in out
        assert "Reindex in progress: no" in health.report(vault, store)

    def test_unknown_lag_before_index_exists(self, tmp_path):
        from alaya.index.store import get_store, reset_store
        store = get_store(tmp_path)
        assert store.last_write_time() is None
        reset_store()
