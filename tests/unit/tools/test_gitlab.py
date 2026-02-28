"""Unit tests for the GitLab provider — glab subprocess is mocked throughout."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from alaya.tools.providers.gitlab import GitLabProvider, GitLabError

SAMPLE_ISSUE = {
    "iid": 42,
    "title": "Add health check to api chart",
    "description": "The API chart is missing a liveness probe.",
    "labels": ["platform", "infra"],
    "state": "opened",
    "web_url": "https://gitlab.com/team/platform/-/issues/42",
}

GLAB_CREATE_OUTPUT = "https://gitlab.com/team/platform/-/issues/44\nIssue #44 created.\n"


class TestGitLabProviderFetchItem:
    def test_fetch_item_returns_external_item(self):
        provider = GitLabProvider()
        with patch("alaya.tools.providers.gitlab._run_glab", return_value=json.dumps(SAMPLE_ISSUE)):
            item = provider.fetch_item("https://gitlab.com/team/platform/-/issues/42")

        assert item.title == "Add health check to api chart"
        assert item.url == "https://gitlab.com/team/platform/-/issues/42"
        assert item.labels == ["platform", "infra"]
        assert item.state == "opened"
        assert item.provider == "gitlab"

    def test_fetch_item_passes_correct_args(self):
        provider = GitLabProvider()
        with patch("alaya.tools.providers.gitlab._run_glab", return_value=json.dumps(SAMPLE_ISSUE)) as mock_glab:
            provider.fetch_item("https://gitlab.com/team/platform/-/issues/42")

        args = mock_glab.call_args[0][0]
        assert "issue" in args
        assert "view" in args
        assert "42" in args
        assert "team/platform" in args

    def test_fetch_item_invalid_url_raises(self):
        provider = GitLabProvider()
        with pytest.raises(GitLabError, match="Cannot parse"):
            provider.fetch_item("https://not-gitlab.com/something")


class TestGitLabProviderFetchItems:
    def test_fetch_items_returns_list(self, monkeypatch):
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        provider = GitLabProvider()
        issues = [SAMPLE_ISSUE]
        with patch("alaya.tools.providers.gitlab._run_glab", return_value=json.dumps(issues)):
            items = provider.fetch_items("gitlab:open")

        assert len(items) == 1
        assert items[0].title == "Add health check to api chart"

    def test_fetch_items_no_project_raises(self, monkeypatch):
        monkeypatch.delenv("GITLAB_PROJECT", raising=False)
        provider = GitLabProvider()
        with pytest.raises(GitLabError, match="GITLAB_PROJECT"):
            provider.fetch_items("gitlab:open")


class TestGitLabProviderCreateItem:
    def test_create_item_returns_url(self, monkeypatch):
        monkeypatch.setenv("GITLAB_PROJECT", "team/platform")
        provider = GitLabProvider()
        with patch("alaya.tools.providers.gitlab._run_glab", return_value=GLAB_CREATE_OUTPUT):
            url = provider.create_item("New issue", "Body.", [])

        assert "issues/44" in url

    def test_create_item_no_project_raises(self, monkeypatch):
        monkeypatch.delenv("GITLAB_PROJECT", raising=False)
        provider = GitLabProvider()
        with pytest.raises(GitLabError, match="GITLAB_PROJECT"):
            provider.create_item("Title", "Body", [])
