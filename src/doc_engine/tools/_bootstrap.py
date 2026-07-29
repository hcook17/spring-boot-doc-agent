"""Legacy no-op — product tools live under doc_engine.tools; do not sys.path-hack scripts/."""

from __future__ import annotations


def ensure_scripts_importable() -> None:
    """Deprecated. Kept so transitional callers do not break; does nothing."""
    return
