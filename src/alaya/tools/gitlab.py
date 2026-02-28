"""GitLab tools: create_issue, get_issues, close_issue, issue_to_note."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from fastmcp import FastMCP
from alaya.config import get_vault_root, get_gitlab_project, get_gitlab_default_labels

GITLAB_NOT_CONFIGURED = (
    "GITLAB_NOT_CONFIGURED: Set the GITLAB_PROJECT environment variable "
    "(e.g. 'team/platform') to enable GitLab integration."
)


class GitLabError(Exception):
    pass


def run_glab(args: list[str], timeout: int = 30) -> str:
    """Run a glab CLI command and return stdout. Raises GitLabError on failure."""
    cmd = ["glab"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise GitLabError(result.stderr.strip() or f"glab exited with code {result.returncode}")
    return result.stdout.strip()


def _require_project() -> str | None:
    """Return GITLAB_PROJECT or None if not configured."""
    return get_gitlab_project()


def create_issue(
    title: str,
    description: str = "",
    labels: list[str] | None = None,
    note_path: str | None = None,
    vault: Path | None = None,
) -> dict | str:
    """Create a GitLab issue. Returns {issue_number, url} or GITLAB_NOT_CONFIGURED."""
    project = _require_project()
    if not project:
        return GITLAB_NOT_CONFIGURED

    if vault is None:
        vault = get_vault_root()

    effective_labels = labels if labels is not None else get_gitlab_default_labels()

    args = ["issue", "create", "--title", title, "--repo", project]
    if description:
        args += ["--description", description]
    for label in effective_labels:
        args += ["--label", label]

    output = run_glab(args)

    # parse issue number and URL from output
    # glab typically outputs the URL on a line by itself
    url_match = re.search(r"https?://\S+/issues/(\d+)", output)
    if url_match:
        issue_number = int(url_match.group(1))
        url = url_match.group(0)
    else:
        # fallback: try to find #N pattern
        num_match = re.search(r"#(\d+)", output)
        issue_number = int(num_match.group(1)) if num_match else 0
        url = output.strip().split("\n")[0]

    result = {"issue_number": issue_number, "url": url}

    if note_path and vault:
        from alaya.tools.write import append_to_note
        append_to_note(note_path, f"\nGitLab issue: {url}", vault)

    return result


def get_issues(
    label: str | None = None,
    state: str = "opened",
) -> list[dict] | str:
    """Return open GitLab issues. Returns GITLAB_NOT_CONFIGURED if not set up."""
    project = _require_project()
    if not project:
        return GITLAB_NOT_CONFIGURED

    args = ["issue", "list", "--repo", project, "--output", "json", "--state", state]
    if label:
        args += ["--label", label]

    output = run_glab(args)
    return json.loads(output)


def close_issue(
    issue_number: int,
    confirm: bool = False,
    comment: str | None = None,
) -> str:
    """Close a GitLab issue. Requires confirm=True."""
    project = _require_project()
    if not project:
        return GITLAB_NOT_CONFIGURED

    if not confirm:
        return f"Closing issue #{issue_number} requires confirm=True."

    if comment:
        run_glab(["issue", "note", str(issue_number), "--repo", project, "--message", comment])

    run_glab(["issue", "close", str(issue_number), "--repo", project])
    return f"Closed issue #{issue_number}."


def issue_to_note(
    issue_number: int,
    directory: str = "projects",
    vault: Path | None = None,
) -> str:
    """Pull a GitLab issue into the vault as a snapshot note.

    Idempotent: returns existing note path if the issue URL is already referenced.
    """
    project = _require_project()
    if not project:
        return GITLAB_NOT_CONFIGURED

    if vault is None:
        vault = get_vault_root()

    output = run_glab(["issue", "view", str(issue_number), "--repo", project, "--output", "json"])
    issue = json.loads(output)

    url = issue.get("web_url", "")
    title = issue.get("title", f"issue-{issue_number}")
    description = issue.get("description", "")
    labels = issue.get("labels", [])
    state = issue.get("state", "")

    # idempotency check: scan vault for existing note referencing this URL
    if url:
        for md_file in vault.rglob("*.md"):
            if ".zk" in md_file.parts:
                continue
            if url in md_file.read_text():
                return str(md_file.relative_to(vault))

    from alaya.tools.write import create_note
    label_str = ", ".join(labels) if labels else "none"
    body = (
        f"## Issue\n"
        f"**URL:** {url}\n"
        f"**State:** {state}\n"
        f"**Labels:** {label_str}\n\n"
        f"## Description\n"
        f"{description}\n"
    )
    path = create_note(
        title=title,
        directory=directory,
        tags=["gitlab"] + [l.replace(" ", "-") for l in labels],
        body=body,
        vault=vault,
    )
    return path


# --- FastMCP tool registration ---

def _register(mcp: FastMCP) -> None:
    vault_root = get_vault_root

    @mcp.tool()
    def create_issue_tool(
        title: str,
        description: str = "",
        labels: list[str] | None = None,
        note_path: str = "",
    ) -> str:
        """Create a GitLab issue. Optionally reference it in a vault note."""
        result = create_issue(title, description, labels or None, note_path or None, vault_root())
        if isinstance(result, str):
            return result
        return f"Created issue #{result['issue_number']}: {result['url']}"

    @mcp.tool()
    def get_issues_tool(label: str = "", state: str = "opened") -> str:
        """List GitLab issues."""
        result = get_issues(label=label or None, state=state)
        if isinstance(result, str):
            return result
        if not result:
            return "No open issues found."
        lines = [f"- #{i['iid']} {i['title']} ({', '.join(i.get('labels', []))})" for i in result]
        return "\n".join(lines)

    @mcp.tool()
    def close_issue_tool(issue_number: int, comment: str = "", confirm: bool = False) -> str:
        """Close a GitLab issue. Requires confirm=True."""
        return close_issue(issue_number, confirm=confirm, comment=comment or None)

    @mcp.tool()
    def issue_to_note_tool(issue_number: int, directory: str = "projects") -> str:
        """Pull a GitLab issue into the vault as a note."""
        result = issue_to_note(issue_number, directory=directory, vault=vault_root())
        if result == GITLAB_NOT_CONFIGURED:
            return result
        return f"Issue #{issue_number} → `{result}`"

