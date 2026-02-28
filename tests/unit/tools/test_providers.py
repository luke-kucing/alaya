"""Unit tests for GitHub and GitLab providers — subprocesses are mocked throughout."""
import json
from unittest.mock import patch

import pytest

from alaya.tools.providers.gitlab import GitLabProvider, GitLabError
from alaya.tools.providers.github import GitHubProvider, GitHubError

# --- fixtures ---

GITLAB_ISSUE = {
    "iid": 42,
    "title": "Add health check to api chart",
    "description": "The API chart is missing a liveness probe.",
    "labels": ["platform", "infra"],
    "state": "opened",
    "web_url": "https://gitlab.com/team/platform/-/issues/42",
}

GLAB_CREATE_OUTPUT = "https://gitlab.com/team/platform/-/issues/44\nIssue #44 created.\n"

GITHUB_ISSUE = {
    "title": "Improve search ranking",
    "body": "Keyword boost is too aggressive.",
    "labels": [{"name": "enhancement"}],
    "state": "OPEN",
    "url": "https://github.com/org/repo/issues/7",
}

GH_CREATE_OUTPUT = "https://github.com/org/repo/issues/8\n"


# --- GitLab ---

class TestGitLabProviderFetchItem:
    def test_fetch_item_returns_external_item(self):
        provider = GitLabProvider()
        with patch("alaya.tools.providers.gitlab._run_glab", return_value=json.dumps(GITLAB_ISSUE)):
            item = provider.fetch_item("https://gitlab.com/team/platform/-/issues/42")

        assert item.title == "Add health check to api chart"
        assert item.url == "https://gitlab.com/team/platform/-/issues/42"
        assert item.labels == ["platform", "infra"]
        assert item.state == "opened"
        assert item.provider == "gitlab"

    def test_fetch_item_passes_correct_args(self):
        provider = GitLabProvider()
        with patch("alaya.tools.providers.gitlab._run_glab", return_value=json.dumps(GITLAB_ISSUE)) as mock_glab:
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
        with patch("alaya.tools.providers.gitlab._run_glab", return_value=json.dumps([GITLAB_ISSUE])):
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


class TestGlabCliNotFound:
    def test_missing_glab_raises_helpful_error(self):
        from alaya.tools.providers.gitlab import _run_glab
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(GitLabError) as exc_info:
                _run_glab(["issue", "list"])
        assert "glab CLI not found" in str(exc_info.value)
        assert "brew install glab" in str(exc_info.value)

    def test_missing_glab_surfaces_in_pull_external(self, tmp_path):
        from alaya.tools.external import pull_external
        (tmp_path / "projects").mkdir()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = pull_external(
                "https://gitlab.com/org/repo/-/issues/1",
                directory="projects",
                tags=[],
                vault=tmp_path,
            )
        assert "[error]" in result
        assert "glab CLI not found" in result


# --- GitHub ---

class TestGitHubProviderFetchItem:
    def test_fetch_item_returns_external_item(self):
        provider = GitHubProvider()
        with patch("alaya.tools.providers.github._run_gh", return_value=json.dumps(GITHUB_ISSUE)):
            item = provider.fetch_item("https://github.com/org/repo/issues/7")

        assert item.title == "Improve search ranking"
        assert item.url == "https://github.com/org/repo/issues/7"
        assert item.labels == ["enhancement"]
        assert item.state == "open"
        assert item.provider == "github"

    def test_fetch_item_invalid_url_raises(self):
        provider = GitHubProvider()
        with pytest.raises(GitHubError, match="Cannot parse"):
            provider.fetch_item("https://not-github.com/something")


class TestGitHubProviderCreateItem:
    def test_create_item_returns_url(self, monkeypatch):
        monkeypatch.setenv("GITHUB_REPO", "org/repo")
        provider = GitHubProvider()
        with patch("alaya.tools.providers.github._run_gh", return_value=GH_CREATE_OUTPUT):
            url = provider.create_item("New issue", "Body.", [])

        assert "issues/8" in url

    def test_create_item_no_repo_raises(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPO", raising=False)
        provider = GitHubProvider()
        with pytest.raises(GitHubError, match="GITHUB_REPO"):
            provider.create_item("Title", "Body", [])


class TestGhCliNotFound:
    def test_missing_gh_raises_helpful_error(self):
        from alaya.tools.providers.github import _run_gh
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(GitHubError) as exc_info:
                _run_gh(["issue", "list"])
        assert "gh CLI not found" in str(exc_info.value)
        assert "brew install gh" in str(exc_info.value)

    def test_missing_gh_surfaces_in_pull_external(self, tmp_path):
        from alaya.tools.external import pull_external
        (tmp_path / "projects").mkdir()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = pull_external(
                "https://github.com/org/repo/issues/1",
                directory="projects",
                tags=[],
                vault=tmp_path,
            )
        assert "[error]" in result
        assert "gh CLI not found" in result
