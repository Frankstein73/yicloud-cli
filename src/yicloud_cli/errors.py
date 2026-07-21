"""Safe, consistent errors for CLI commands."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .auth import ACCESS_KEY_ENV, SECRET_KEY_ENV


_SENSITIVE_NAME = re.compile(
    r"(?i)(access[_-]?key|secret(?:[_-]?(?:access[_-]?)?key)?|token|password|credential)"
)
_ASSIGNMENT = re.compile(
    r"(?i)((?:access[_-]?key(?:[_-]?id)?|secret(?:[_-]?access[_-]?key)?|token|password)\s*[=:]\s*)([^\s,;]+)"
)


@dataclass
class ApiError(Exception):
    """An expected API failure suitable for presentation to a CLI user."""

    message: str
    code: str | int | None = None
    status: int | None = None

    def __str__(self) -> str:
        return self.message


def api_error_from_sdk(error: Any) -> ApiError:
    """Convert an SDK exception to the CLI's stable error representation."""
    message = getattr(error, "message", None) or "YiCloud API request failed"
    code = getattr(error, "code", None)
    status = getattr(error, "status_code", None)
    return ApiError(
        message=str(message),
        code=code if code not in (None, 0) else None,
        status=status if status not in (None, 0) else None,
    )


def redact_sensitive(value: object, environ: Mapping[str, str]) -> str:
    """Remove known credentials and common inline secret assignments from text."""
    text = str(value)
    sensitive_names = {ACCESS_KEY_ENV, SECRET_KEY_ENV}
    sensitive_names.update(name for name in environ if _SENSITIVE_NAME.search(name))
    secrets = sorted(
        {environ.get(name, "") for name in sensitive_names if environ.get(name, "")},
        key=len,
        reverse=True,
    )
    for secret in secrets:
        text = text.replace(secret, "[REDACTED]")
    return _ASSIGNMENT.sub(r"\1[REDACTED]", text)


def format_api_error(error: ApiError, environ: Mapping[str, str]) -> str:
    """Format an API error without exposing credential values."""
    details = []
    if error.status is not None:
        details.append(f"HTTP {error.status}")
    if error.code is not None:
        details.append(f"code {error.code}")
    prefix = (
        f"API request failed ({', '.join(details)})"
        if details
        else "API request failed"
    )
    message = redact_sensitive(error.message, environ)
    return f"{prefix}: {message}"
