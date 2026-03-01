import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class ZKError(Exception):
    pass


def _reject_flag(value: str, param_name: str) -> str:
    """Raise ValueError if *value* looks like a CLI flag (starts with '-').

    This prevents user-supplied MCP parameters from being interpreted as zk
    flags even though we use list-based subprocess (which prevents shell
    injection). Defense-in-depth: zk itself is unlikely to have dangerous
    flags, but we should never let user input bleed into the option namespace.
    """
    if value.startswith("-"):
        raise ValueError(f"Invalid {param_name} value {value!r}: must not start with '-'")
    return value


def run_zk(args: list[str], vault_root: Path, timeout: int = 30) -> str:
    """Run a zk CLI command and return stdout. Raises ZKError on failure."""
    cmd = ["zk"] + args
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=str(vault_root),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        msg = result.stderr.strip() or f"zk exited with code {result.returncode}"
        logger.warning("zk command failed: %s", msg)
        raise ZKError(msg)
    return result.stdout.strip()
