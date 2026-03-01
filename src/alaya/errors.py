"""Structured error codes for alaya tools.

Pure functions raise standard Python exceptions (FileNotFoundError, ValueError,
FileExistsError). The FastMCP registration wrappers in each tool module catch
these and return structured error strings for Claude to parse.

Error string format: "ERROR [{CODE}]: {message}"
"""
from enum import Enum


class ErrorCode(str, Enum):
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    OUTSIDE_VAULT = "OUTSIDE_VAULT"
    SECTION_NOT_FOUND = "SECTION_NOT_FOUND"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"


# Re-export bare names for backwards-compatibility with all import sites.
# Tool modules import e.g. `from alaya.errors import NOT_FOUND` — these
# assignments make that work without changing every callsite.
NOT_FOUND = ErrorCode.NOT_FOUND
ALREADY_EXISTS = ErrorCode.ALREADY_EXISTS
OUTSIDE_VAULT = ErrorCode.OUTSIDE_VAULT
SECTION_NOT_FOUND = ErrorCode.SECTION_NOT_FOUND
CONFIRMATION_REQUIRED = ErrorCode.CONFIRMATION_REQUIRED
NOT_CONFIGURED = ErrorCode.NOT_CONFIGURED
INVALID_ARGUMENT = ErrorCode.INVALID_ARGUMENT


def error(code: ErrorCode, message: str) -> str:
    """Format a structured error string for tool return values."""
    return f"ERROR [{code.value}]: {message}"
