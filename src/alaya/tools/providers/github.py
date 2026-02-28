"""GitHub provider: wraps gh CLI for fetch/create operations."""
from __future__ import annotations

import json
import re
import subprocess

from alaya.tools.providers import ExternalItem


class GitHubError(Exception):
    pass


def _run_gh(args: list[str], timeout: int = 30) -> str:
    result = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise GitHubError(result.stderr.strip() or f"gh exited with {result.returncode}")
    return result.stdout.strip()


def _repo_from_url(url: str) -> str:
    """Extract 'org/repo' from a GitHub issue URL."""
    match = re.search(r"github\.com/([^/]+/[^/]+)/issues", url)
    if not match:
        raise GitHubError(f"Cannot parse repo from URL: {url}")
    return match.group(1)


def _issue_number_from_url(url: str) -> int:
    match = re.search(r"/issues/(\d+)", url)
    if not match:
        raise GitHubError(f"Cannot parse issue number from URL: {url}")
    return int(match.group(1))


class GitHubProvider:
    def fetch_item(self, url: str) -> ExternalItem:
        repo = _repo_from_url(url)
        issue_num = _issue_number_from_url(url)
        output = _run_gh(["issue", "view", str(issue_num), "--repo", repo, "--json",
                          "title,body,labels,state,url"])
        issue = json.loads(output)
        labels = [lbl["name"] for lbl in issue.get("labels", [])]
        return ExternalItem(
            url=issue.get("url", url),
            title=issue.get("title", f"issue-{issue_num}"),
            body=issue.get("body", ""),
            labels=labels,
            state=issue.get("state", "").lower(),
            provider="github",
        )

    def fetch_items(self, query: str) -> list[ExternalItem]:
        import os
        repo = os.environ.get("GITHUB_REPO", "")
        if not repo:
            raise GitHubError("GITHUB_REPO env var required for shorthand queries")

        args = ["issue", "list", "--repo", repo, "--json", "title,body,labels,state,url"]
        if "label=" in query:
            label = query.split("label=", 1)[1]
            args += ["--label", label]
        if "assigned" in query:
            args += ["--assignee", "@me"]

        output = _run_gh(args)
        issues = json.loads(output)
        return [
            ExternalItem(
                url=i.get("url", ""),
                title=i.get("title", ""),
                body=i.get("body", ""),
                labels=[lbl["name"] for lbl in i.get("labels", [])],
                state=i.get("state", "").lower(),
                provider="github",
            )
            for i in issues
        ]

    def create_item(self, title: str, body: str, labels: list[str]) -> str:
        import os
        repo = os.environ.get("GITHUB_REPO", "")
        if not repo:
            raise GitHubError("GITHUB_REPO env var required to create issues")

        args = ["issue", "create", "--title", title, "--repo", repo, "--body", body or " "]
        for label in labels:
            args += ["--label", label]

        output = _run_gh(args)
        # gh outputs the issue URL on the last line
        return output.strip().split("\n")[-1]
