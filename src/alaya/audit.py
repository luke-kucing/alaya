"""Audit logging: append structured tool call entries to .zk/audit.jsonl."""
import json
import threading
import time
from pathlib import Path

_MAX_ARG_LEN = 200

_lock = threading.Lock()


def _truncate_args(args: dict) -> dict:
    """Return a copy of args with string values truncated."""
    result = {}
    for key, val in args.items():
        if isinstance(val, str) and len(val) > _MAX_ARG_LEN:
            result[key] = val[:_MAX_ARG_LEN] + "..."
        else:
            result[key] = val
    return result


def log_tool_call(
    vault: Path,
    tool_name: str,
    args: dict,
    result_summary: str,
    duration_ms: float,
) -> None:
    """Append a structured entry to .zk/audit.jsonl."""
    status = "error" if result_summary.startswith("ERROR") else "ok"

    entry = {
        "ts": time.time(),
        "tool": tool_name,
        "args": _truncate_args(args),
        "status": status,
        "duration_ms": round(duration_ms, 1),
        "summary": result_summary[:_MAX_ARG_LEN],
    }

    audit_dir = vault / ".zk"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_file = audit_dir / "audit.jsonl"

    line = json.dumps(entry, ensure_ascii=False) + "\n"

    with _lock:
        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(line)
