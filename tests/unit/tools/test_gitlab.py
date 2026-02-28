"""Unit tests for GitLab tools — glab subprocess is mocked throughout."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from alaya.tools.gitlab import (
    create_issue,
    get_issues,
    close_issue,
    issue_to_note,
    GitLabError,
    GITLAB_NOT_CONFIGURED,
)

SAMPLE_ISSUE_LIST = json.dumps([
    {
        "iid": 42,
        "title": "Add health check to api chart",
        "description": "The API chart is missing a liveness probe.",
        "labels": ["platform", "infra"],
        "state": "opened",
        "web_url": "https://gitlab.example.com/team/platform/-/issues/42",
    },
    {
        "iid": 43,
        "title": "Update ArgoCD app of apps",
        "description": "Sync with new cluster structure.",
        "labels": ["platform"],
        "state": "opened",
        "web_url": "https://gitlab.example.com/team/platform/-/issues/43",
    },
])

GLAB_CREATE_OUTPUT = (
    "https://gitlab.example.com/team/platform/-/issues/44\n"
    "Issue #44 created.\n"
)


class TestCreateIssue:
    def test_calls_glab_with_title(self, vault: Path, monkeypatch) -> None:
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        with patch("alaya.tools.gitlab.run_glab", return_value=GLAB_CREATE_OUTPUT) as mock_glab:
            create_issue("Add liveness probe", vault=vault)
        args = mock_glab.call_args[0][0]
        assert "issue" in args
        assert "create" in args
        assert "Add liveness probe" in " ".join(args)

    def test_returns_issue_number_and_url(self, vault: Path, monkeypatch) -> None:
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        with patch("alaya.tools.gitlab.run_glab", return_value=GLAB_CREATE_OUTPUT):
            result = create_issue("Add liveness probe", vault=vault)
        assert result["issue_number"] == 44
        assert "issues/44" in result["url"]

    def test_with_note_path_appends_reference(self, vault: Path, monkeypatch) -> None:
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        with patch("alaya.tools.gitlab.run_glab", return_value=GLAB_CREATE_OUTPUT):
            create_issue(
                "Add liveness probe",
                note_path="projects/platform-migration.md",
                vault=vault,
            )
        content = (vault / "projects/platform-migration.md").read_text()
        assert "issues/44" in content

    def test_default_labels_from_env(self, vault: Path, monkeypatch) -> None:
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        monkeypatch.setenv("GITLAB_DEFAULT_LABELS", "platform,infra")
        with patch("alaya.tools.gitlab.run_glab", return_value=GLAB_CREATE_OUTPUT) as mock_glab:
            create_issue("Some task", vault=vault)
        args = " ".join(mock_glab.call_args[0][0])
        assert "platform" in args

    def test_not_configured_returns_error(self, vault: Path, monkeypatch) -> None:
        monkeypatch.delenv("GITLAB_PROJECT", raising=False)
        result = create_issue("Some task", vault=vault)
        assert result == GITLAB_NOT_CONFIGURED


class TestGetIssues:
    def test_returns_list_of_issues(self, monkeypatch) -> None:
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        with patch("alaya.tools.gitlab.run_glab", return_value=SAMPLE_ISSUE_LIST):
            issues = get_issues()
        assert len(issues) == 2
        assert issues[0]["iid"] == 42

    def test_issue_has_required_fields(self, monkeypatch) -> None:
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        with patch("alaya.tools.gitlab.run_glab", return_value=SAMPLE_ISSUE_LIST):
            issues = get_issues()
        issue = issues[0]
        assert "iid" in issue
        assert "title" in issue
        assert "web_url" in issue
        assert "labels" in issue

    def test_label_filter_passed_to_glab(self, monkeypatch) -> None:
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        with patch("alaya.tools.gitlab.run_glab", return_value=SAMPLE_ISSUE_LIST) as mock_glab:
            get_issues(label="platform")
        args = " ".join(mock_glab.call_args[0][0])
        assert "platform" in args

    def test_not_configured_returns_error(self, monkeypatch) -> None:
        monkeypatch.delenv("GITLAB_PROJECT", raising=False)
        result = get_issues()
        assert result == GITLAB_NOT_CONFIGURED


class TestCloseIssue:
    def test_closes_issue_via_glab(self, monkeypatch) -> None:
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        with patch("alaya.tools.gitlab.run_glab") as mock_glab:
            close_issue(42, confirm=True)
        calls = [" ".join(c[0][0]) for c in mock_glab.call_args_list]
        assert any("close" in c and "42" in c for c in calls)

    def test_requires_confirm(self, monkeypatch) -> None:
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        with patch("alaya.tools.gitlab.run_glab") as mock_glab:
            result = close_issue(42, confirm=False)
        mock_glab.assert_not_called()
        assert "confirm" in result.lower()

    def test_comment_posted_before_close(self, monkeypatch) -> None:
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        call_order = []
        def fake_glab(args, *a, **kw):
            call_order.append(args)
            return ""
        with patch("alaya.tools.gitlab.run_glab", side_effect=fake_glab):
            close_issue(42, confirm=True, comment="Resolved in deploy v2.")
        # note command should come before close
        joined = [" ".join(c) for c in call_order]
        note_idx = next(i for i, c in enumerate(joined) if "note" in c)
        close_idx = next(i for i, c in enumerate(joined) if "close" in c)
        assert note_idx < close_idx

    def test_not_configured_returns_error(self, monkeypatch) -> None:
        monkeypatch.delenv("GITLAB_PROJECT", raising=False)
        result = close_issue(42, confirm=True)
        assert result == GITLAB_NOT_CONFIGURED


class TestIssueToNote:
    def test_creates_note_in_projects(self, vault: Path, monkeypatch) -> None:
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        issue_json = json.dumps({
            "iid": 42,
            "title": "Add health check to api chart",
            "description": "The API chart is missing a liveness probe.",
            "labels": ["platform"],
            "state": "opened",
            "web_url": "https://gitlab.example.com/team/platform/-/issues/42",
        })
        with patch("alaya.tools.gitlab.run_glab", return_value=issue_json):
            path = issue_to_note(42, vault=vault)
        assert (vault / path).exists()
        assert "projects" in path

    def test_note_contains_issue_url(self, vault: Path, monkeypatch) -> None:
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        issue_json = json.dumps({
            "iid": 42,
            "title": "Add health check",
            "description": "Details here.",
            "labels": [],
            "state": "opened",
            "web_url": "https://gitlab.example.com/team/platform/-/issues/42",
        })
        with patch("alaya.tools.gitlab.run_glab", return_value=issue_json):
            path = issue_to_note(42, vault=vault)
        content = (vault / path).read_text()
        assert "issues/42" in content

    def test_idempotent_no_duplicate(self, vault: Path, monkeypatch) -> None:
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        issue_json = json.dumps({
            "iid": 42,
            "title": "Add health check",
            "description": "Details.",
            "labels": [],
            "state": "opened",
            "web_url": "https://gitlab.example.com/team/platform/-/issues/42",
        })
        with patch("alaya.tools.gitlab.run_glab", return_value=issue_json):
            path1 = issue_to_note(42, vault=vault)
            path2 = issue_to_note(42, vault=vault)
        assert path1 == path2

    def test_not_configured_returns_error(self, vault: Path, monkeypatch) -> None:
        monkeypatch.delenv("GITLAB_PROJECT", raising=False)
        result = issue_to_note(42, vault=vault)
        assert result == GITLAB_NOT_CONFIGURED
