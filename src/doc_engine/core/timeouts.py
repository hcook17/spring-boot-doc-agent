"""Env-overridable subprocess budgets for Stage-0 and pipeline tools.

Hung CodeQL builds and wedged deterministic stages must fail closed with
``TimeoutExpired`` rather than holding certification forever.
"""

from __future__ import annotations

import os


def _env_seconds(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer number of seconds, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def tool_timeout_seconds() -> int:
    """Budget for deterministic stages, gates, and CodeQL query/decode."""
    return _env_seconds("DOC_ENGINE_TOOL_TIMEOUT", 600)


def codeql_database_timeout_seconds() -> int:
    """Budget for ``codeql database create`` (compile under instrumentation)."""
    return _env_seconds("DOC_ENGINE_CODEQL_TIMEOUT", 3600)
