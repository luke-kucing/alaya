import subprocess
from pathlib import Path


class ZKError(Exception):
    pass


def run_zk(args: list[str], vault_root: Path, timeout: int = 30) -> str:
    """Run a zk CLI command and return stdout. Raises ZKError on failure."""
    cmd = ["zk"] + args
    result = subprocess.run(
        cmd,
        cwd=str(vault_root),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise ZKError(result.stderr.strip() or f"zk exited with code {result.returncode}")
    return result.stdout.strip()
