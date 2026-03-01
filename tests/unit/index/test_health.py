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
