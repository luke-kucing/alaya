"""Tests for the generic external bridge (pull_external, push_external)."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestPullExternal:
    def test_pull_gitlab_url_creates_note(self, tmp_path):
        from alaya.tools.external import pull_external

        item = MagicMock()
        item.url = "https://gitlab.com/org/repo/-/issues/42"
        item.title = "Fix the thing"
        item.body = "Description of the issue."
        item.labels = ["bug"]
        item.state = "opened"
        item.provider = "gitlab"

        with patch("alaya.tools.providers.gitlab.GitLabProvider.fetch_item", return_value=item):
            result = pull_external(
                source="https://gitlab.com/org/repo/-/issues/42",
                directory="projects",
                tags=[],
                vault=tmp_path,
            )

        assert "projects/" in result
        note_path = tmp_path / result
        assert note_path.exists()
        assert "Fix the thing" in note_path.read_text()

    def test_pull_github_url_creates_note(self, tmp_path):
        from alaya.tools.external import pull_external

        item = MagicMock()
        item.url = "https://github.com/org/repo/issues/7"
        item.title = "GitHub issue"
        item.body = "A GitHub issue body."
        item.labels = []
        item.state = "open"
        item.provider = "github"

        with patch("alaya.tools.providers.github.GitHubProvider.fetch_item", return_value=item):
            result = pull_external(
                source="https://github.com/org/repo/issues/7",
                directory="projects",
                tags=[],
                vault=tmp_path,
            )

        assert "projects/" in result

    def test_pull_idempotent_returns_existing(self, tmp_path):
        from alaya.tools.external import pull_external

        # pre-create a note that references the URL
        proj_dir = tmp_path / "projects"
        proj_dir.mkdir()
        note = proj_dir / "existing.md"
        url = "https://gitlab.com/org/repo/-/issues/99"
        note.write_text(f"---\ntitle: Existing\n---\nURL: {url}\n")

        item = MagicMock()
        item.url = url
        item.title = "Existing"
        item.body = "Body."
        item.labels = []
        item.state = "opened"
        item.provider = "gitlab"

        with patch("alaya.tools.providers.gitlab.GitLabProvider.fetch_item", return_value=item):
            result = pull_external(source=url, directory="projects", tags=[], vault=tmp_path)

        assert "existing.md" in result

    def test_unknown_provider_returns_error(self, tmp_path):
        from alaya.tools.external import pull_external

        result = pull_external(
            source="https://unknown-provider.io/item/1",
            directory="projects",
            tags=[],
            vault=tmp_path,
        )
        assert "Unsupported" in result or "unsupported" in result or "error" in result.lower()


class TestPushExternal:
    def test_push_to_gitlab_calls_provider(self, tmp_path):
        from alaya.tools.external import push_external

        note_path = tmp_path / "projects" / "my-idea.md"
        note_path.parent.mkdir(parents=True)
        note_path.write_text("---\ntitle: My Idea\n---\nGreat idea.\n")

        with patch("alaya.tools.providers.gitlab.GitLabProvider.create_item", return_value="https://gitlab.com/org/repo/-/issues/50") as mock_create:
            result = push_external(
                note_path="projects/my-idea.md",
                target="gitlab",
                vault=tmp_path,
                labels=[],
            )

        mock_create.assert_called_once()
        assert "https://gitlab.com" in result

    def test_push_to_github_calls_provider(self, tmp_path):
        from alaya.tools.external import push_external

        note_path = tmp_path / "projects" / "my-feature.md"
        note_path.parent.mkdir(parents=True)
        note_path.write_text("---\ntitle: My Feature\n---\nFeature body.\n")

        with patch("alaya.tools.providers.github.GitHubProvider.create_item", return_value="https://github.com/org/repo/issues/12") as mock_create:
            result = push_external(
                note_path="projects/my-feature.md",
                target="github",
                vault=tmp_path,
                labels=[],
            )

        mock_create.assert_called_once()
        assert "https://github.com" in result

    def test_push_unknown_target_returns_error(self, tmp_path):
        from alaya.tools.external import push_external

        note_path = tmp_path / "notes" / "thing.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text("---\ntitle: Thing\n---\n")

        result = push_external(
            note_path="notes/thing.md",
            target="unknown_provider",
            vault=tmp_path,
            labels=[],
        )
        assert "Unsupported" in result or "unsupported" in result or "error" in result.lower()

    def test_push_nonexistent_note_returns_error(self, tmp_path):
        from alaya.tools.external import push_external

        result = push_external(
            note_path="notes/missing.md",
            target="gitlab",
            vault=tmp_path,
            labels=[],
        )
        assert "not found" in result.lower() or "error" in result.lower()
