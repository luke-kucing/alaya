"""Server-side two-phase confirmation for destructive tools.

The README's position has been that "confirmation lives in Claude, not the
server". That holds for Claude Code, which prompts before a destructive tool
call. It does not hold for an arbitrary MCP client — an agent loop will happily
call ``delete_note_tool`` with no human anywhere in the path.

So destructive tools become two-phase:

1. Called without ``confirm_token``, the tool returns a preview of what would
   change plus a token.
2. Called again with that token, it executes.

The token is an HMAC over the tool name, the normalised arguments, and an
expiry, keyed by a secret generated per process. A token therefore cannot be
replayed against different arguments, cannot outlive its expiry, and does not
survive a server restart.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import secrets
import time
from collections.abc import Callable
from enum import Enum
from hashlib import sha256

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 60

# Per-process secret: tokens are meaningless to any other process, and a
# restart invalidates every outstanding proposal.
_SECRET = secrets.token_bytes(32)


class ConfirmMode(Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    OFF = "off"


class ConfirmError(Exception):
    """Raised when a confirm_token is invalid, expired, or for other arguments."""


def get_mode() -> ConfirmMode:
    """Read the confirmation mode from ALAYA_CONFIRM_MODE (default: required)."""
    raw = (os.environ.get("ALAYA_CONFIRM_MODE") or "required").strip().lower()
    try:
        return ConfirmMode(raw)
    except ValueError:
        logger.warning(
            "Unknown ALAYA_CONFIRM_MODE %r — falling back to 'required'. "
            "Valid values: required, optional, off.",
            raw,
        )
        return ConfirmMode.REQUIRED


def get_ttl() -> int:
    """Read the token lifetime in seconds from ALAYA_CONFIRM_TTL (default: 60)."""
    raw = os.environ.get("ALAYA_CONFIRM_TTL")
    if not raw:
        return DEFAULT_TTL_SECONDS
    try:
        ttl = int(raw)
    except ValueError:
        logger.warning("Invalid ALAYA_CONFIRM_TTL %r — using %ds", raw, DEFAULT_TTL_SECONDS)
        return DEFAULT_TTL_SECONDS
    return ttl if ttl > 0 else DEFAULT_TTL_SECONDS


def _canonical_args(args: dict) -> str:
    """Serialise args stably so the same call always signs the same bytes."""
    return json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)


def _sign(tool: str, args: dict, expiry: int) -> str:
    payload = f"{tool}|{_canonical_args(args)}|{expiry}".encode()
    return hmac.new(_SECRET, payload, sha256).hexdigest()[:32]


def issue_token(tool: str, args: dict, ttl: int | None = None) -> str:
    """Return a confirm token binding *tool* and *args* until it expires."""
    expiry = int(time.time()) + (ttl if ttl is not None else get_ttl())
    return f"{expiry}.{_sign(tool, args, expiry)}"


def verify_token(tool: str, args: dict, token: str) -> None:
    """Raise ConfirmError unless *token* was issued for this call and is unexpired."""
    expiry_raw, _, signature = token.partition(".")
    if not signature:
        raise ConfirmError("Malformed confirm_token.")
    try:
        expiry = int(expiry_raw)
    except ValueError:
        raise ConfirmError("Malformed confirm_token.") from None

    if time.time() > expiry:
        raise ConfirmError(
            "confirm_token has expired. Call again without a token to get a fresh preview."
        )
    if not hmac.compare_digest(signature, _sign(tool, args, expiry)):
        raise ConfirmError(
            "confirm_token does not match these arguments. A token is only valid for "
            "the exact call it was issued for."
        )


def token_id(token: str) -> str:
    """Short id used to pair the propose and execute entries in the audit log."""
    return token.partition(".")[2][:12]


_TOKEN_IN_RESULT = re.compile(r'confirm_token="(\d+\.[0-9a-f]+)"')


def audit_id_for(args: dict, result: str) -> str | None:
    """Return the token id linking a propose and its matching execute entry.

    Reads the token from the arguments on the execute call, and out of the
    proposal text on the propose call, so both audit entries share one id.
    """
    supplied = args.get("confirm_token")
    if supplied:
        return token_id(str(supplied))
    match = _TOKEN_IN_RESULT.search(result or "")
    return token_id(match.group(1)) if match else None


def format_proposal(tool: str, args: dict, preview: str, ttl: int | None = None) -> str:
    """Render the phase-1 response: what would happen, plus the token to proceed."""
    token = issue_token(tool, args, ttl)
    seconds = ttl if ttl is not None else get_ttl()
    return (
        f"CONFIRM REQUIRED — {tool}\n\n"
        f"{preview}\n\n"
        f"Nothing has changed yet. To proceed, call {tool} again with the same arguments plus:\n"
        f"  confirm_token=\"{token}\"\n"
        f"This token is valid for {seconds}s and only for these exact arguments."
    )


def guard(
    tool: str, args: dict, confirm_token: str, preview: Callable[[], str]
) -> str | None:
    """Gate a destructive call. Returns a proposal to send back, or None to proceed.

    *preview* is a zero-argument callable so the (potentially expensive) preview
    is only built when a proposal is actually needed.
    """
    mode = get_mode()
    if mode is ConfirmMode.OFF:
        return None

    if confirm_token:
        verify_token(tool, args, confirm_token)
        return None

    if mode is ConfirmMode.OPTIONAL:
        return None

    return format_proposal(tool, args, preview())
