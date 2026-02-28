"""Generic external bridge: pull_external, push_external."""
from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP


def pull_external(
    source: str,
    directory: str,
    tags: list[str],
    vault: Path,
) -> str:
    """Pull an external item into the vault as a note.

    source: a URL (https://gitlab.com/..., https://github.com/...) or
            a provider shorthand (gitlab:open, github:assigned, github:label=bug).

    Returns the relative path of the created/updated note, or an error string.
    """
    from alaya.tools.providers import detect_provider, get_provider

    provider_name = detect_provider(source)
    if not provider_name:
        return f"[error] Unsupported source: {source!r}. Supported providers: gitlab, github."

    try:
        provider = get_provider(provider_name)
    except ValueError as e:
        return f"[error] {e}"

    try:
        # URL fetch (single item)
        if source.startswith("http"):
            item = provider.fetch_item(source)
            items = [item]
        else:
            # shorthand like "gitlab:open"
            items = provider.fetch_items(source)
    except Exception as e:
        return f"[error] Failed to fetch from {provider_name}: {e}"

    if not items:
        return "No items found."

    from alaya.tools.write import create_note

    created_paths = []
    for item in items:
        # idempotency: check if a note referencing this URL already exists
        existing = _find_note_by_url(item.url, vault)
        if existing:
            created_paths.append(existing)
            continue

        label_str = ", ".join(item.labels) if item.labels else "none"
        body = (
            f"## Item\n"
            f"**URL:** {item.url}\n"
            f"**State:** {item.state}\n"
            f"**Labels:** {label_str}\n\n"
            f"## Description\n"
            f"{item.body or ''}\n"
        )
        note_tags = [provider_name] + [lbl.replace(" ", "-") for lbl in item.labels] + tags

        try:
            path = create_note(
                title=item.title,
                directory=directory,
                tags=note_tags,
                body=body,
                vault=vault,
            )
            created_paths.append(path)
        except FileExistsError:
            # slug collision — return the existing path
            from alaya.vault import resolve_note_path
            from alaya.tools.write import _slugify
            slug = _slugify(item.title)
            fallback = f"{directory}/{slug}.md"
            created_paths.append(fallback)

    if len(created_paths) == 1:
        return created_paths[0]
    return "\n".join(created_paths)


def push_external(
    note_path: str,
    target: str,
    vault: Path,
    title: str = "",
    labels: list[str] | None = None,
) -> str:
    """Push a vault note to an external provider as an issue.

    Returns the URL of the created item, or an error string.
    """
    from alaya.tools.providers import get_provider

    path = vault / note_path
    if not path.exists():
        return f"[error] Note not found: {note_path}"

    try:
        provider = get_provider(target)
    except ValueError as e:
        return f"[error] {e}"

    content = path.read_text()
    from alaya.vault import parse_note
    note = parse_note(content)

    issue_title = title or note.title or path.stem
    issue_body = note.body.strip()

    try:
        url = provider.create_item(issue_title, issue_body, labels or [])
    except Exception as e:
        return f"[error] Failed to create item in {target}: {e}"

    # append a back-reference to the vault note
    from alaya.tools.write import append_to_note
    try:
        append_to_note(note_path, f"**{target.capitalize()}:** {url}", vault)
    except Exception:
        pass  # back-reference is nice to have, not critical

    return url


def _find_note_by_url(url: str, vault: Path) -> str | None:
    """Return the relative path of the first note containing the URL, or None."""
    for md_file in vault.rglob("*.md"):
        if ".zk" in md_file.parts:
            continue
        try:
            if url in md_file.read_text():
                return str(md_file.relative_to(vault))
        except OSError:
            continue
    return None


# --- FastMCP tool registration ---

def _register(mcp: FastMCP, vault: Path) -> None:
    @mcp.tool()
    def pull_external_tool(
        source: str,
        directory: str = "projects",
        tags: list[str] | None = None,
    ) -> str:
        """Pull an external item (GitLab/GitHub issue) into the vault as a note.

        source: URL or shorthand (gitlab:open, github:assigned, github:label=bug).
        """
        return pull_external(source, directory, tags or [], vault)

    @mcp.tool()
    def push_external_tool(
        note_path: str,
        target: str,
        title: str = "",
        labels: list[str] | None = None,
    ) -> str:
        """Push a vault note to an external provider (gitlab, github) as an issue.

        Returns the created item's URL.
        """
        return push_external(note_path, target, vault, title=title, labels=labels or [])
