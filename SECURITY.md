# Security Policy

## Supported Versions

Only the latest release on the `main` branch receives security fixes.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, report them privately via [GitHub Security Advisories](../../security/advisories/new).

Include:
- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- Any suggested mitigations

You can expect an acknowledgement within 3 business days and a fix or
workaround within 14 days for confirmed issues.

## Threat Model

alaya runs as a local MCP server. The primary trust boundary is the local
filesystem and the MCP client (e.g. Claude Desktop).

### In scope

| Threat | Mitigation |
|--------|------------|
| Path traversal via note paths supplied by MCP client | All note paths are resolved against vault root and checked to stay within it |
| LanceDB filter injection via user-supplied query strings | All values interpolated into filter strings pass through `_sq()` / `_sq_like()` escaping helpers |
| Subprocess injection via vault path or tool arguments | `zk` is invoked with a fixed argument list; user-controlled values are never shell-interpolated |
| Dependency CVEs | `pip-audit` runs on every CI push; weekly Semgrep scan covers known vuln patterns |

### Out of scope

- Attacks that require local root / physical access to the machine
- Attacks against the MCP transport layer itself (handled by fastmcp)
- Denial-of-service via large vaults (alaya is a local personal tool)

## CI Security Checks

| Check | Tool | Trigger |
|-------|------|---------|
| Unit tests | pytest | push / PR |
| Dependency CVE scan | pip-audit | push / PR |
| SAST | Semgrep (`p/python`, `p/owasp-top-ten`, `p/secrets`, custom rules) | push / PR / weekly |
