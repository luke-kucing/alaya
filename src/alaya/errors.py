"""Structured error codes for alaya tools.

Pure functions raise standard Python exceptions (FileNotFoundError, ValueError,
FileExistsError). The FastMCP registration wrappers in each tool module catch
these and return structured error strings for Claude to parse.

Error string format: "ERROR [{CODE}]: {message}"
"""

NOT_FOUND = "NOT_FOUND"
ALREADY_EXISTS = "ALREADY_EXISTS"
OUTSIDE_VAULT = "OUTSIDE_VAULT"
SECTION_NOT_FOUND = "SECTION_NOT_FOUND"
CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
NOT_CONFIGURED = "NOT_CONFIGURED"
INVALID_ARGUMENT = "INVALID_ARGUMENT"


def error(code: str, message: str) -> str:
    """Format a structured error string for tool return values."""
    return f"ERROR [{code}]: {message}"
