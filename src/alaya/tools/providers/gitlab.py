"""GitLab provider: wraps glab CLI for fetch/create operations."""
from __future__ import annotations

import json
import re
import subprocess

from alaya.tools.providers import ExternalItem


class GitLabError(Exception):
    pass


def _run_glab(args: list[str], timeout: int = 30) -> str:
    result = subprocess.run(["glab"] + args, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise GitLabError(result.stderr.strip() or f"glab exited with {result.returncode}")
    return result.stdout.strip()


def _repo_from_url(url: str) -> str:
    """Extract 'org/repo' from a GitLab URL."""
    match = re.search(r"gitlab\.com/([^/]+/[^/]+?)(?:/-|$)", url)
    if not match:
        raise GitLabError(f"Cannot parse repo from URL: {url}")
    return match.group(1)


def _issue_number_from_url(url: str) -> int:
    match = re.search(r"/issues/(\d+)", url)
    if not match:
        raise GitLabError(f"Cannot parse issue number from URL: {url}")
    return int(match.group(1))


class GitLabProvider:
    def fetch_item(self, url: str) -> ExternalItem:
        repo = _repo_from_url(url)
        issue_num = _issue_number_from_url(url)
        output = _run_glab(["issue", "view", str(issue_num), "--repo", repo, "--output", "json"])
        issue = json.loads(output)
        return ExternalItem(
            url=issue.get("web_url", url),
            title=issue.get("title", f"issue-{issue_num}"),
            body=issue.get("description", ""),
            labels=issue.get("labels", []),
            state=issue.get("state", ""),
            provider="gitlab",
        )

    def fetch_items(self, query: str) -> list[ExternalItem]:
        # query format: "gitlab:open" or "gitlab:label=bug"
        import os
        repo = os.environ.get("GITLAB_PROJECT", "")
        if not repo:
            raise GitLabError("GITLAB_PROJECT env var required for shorthand queries")

        args = ["issue", "list", "--repo", repo, "--output", "json"]
        if "label=" in query:
            label = query.split("label=", 1)[1]
            args += ["--label", label]

        output = _run_glab(args)
        issues = json.loads(output)
        return [
            ExternalItem(
                url=i.get("web_url", ""),
                title=i.get("title", ""),
                body=i.get("description", ""),
                labels=i.get("labels", []),
                state=i.get("state", ""),
                provider="gitlab",
            )
            for i in issues
        ]

    def create_item(self, title: str, body: str, labels: list[str]) -> str:
        import os
        repo = os.environ.get("GITLAB_PROJECT", "")
        if not repo:
            raise GitLabError("GITLAB_PROJECT env var required to create issues")

        args = ["issue", "create", "--title", title, "--repo", repo]
        if body:
            args += ["--description", body]
        for label in labels:
            args += ["--label", label]

        output = _run_glab(args)
        url_match = re.search(r"https?://\S+/issues/\d+", output)
        return url_match.group(0) if url_match else output.strip().split("\n")[-1]
