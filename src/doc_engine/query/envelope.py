"""Query result envelope — bounded output for agent consumers."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Sequence

QUERY_RESULT_SCHEMA_VERSION = 1
DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def apply_limit(
    rows: Sequence[Mapping[str, Any]],
    limit: int | None,
    *,
    max_limit: int = MAX_LIMIT,
) -> tuple[list[Mapping[str, Any]], bool]:
    """Return (capped_rows, truncated).

    ``limit is None`` uses DEFAULT_LIMIT. Negative or zero → empty + truncated
    if input non-empty. Values above ``max_limit`` are clamped.
    """
    if limit is None:
        cap = DEFAULT_LIMIT
    else:
        cap = int(limit)
    if cap < 0:
        cap = 0
    if cap > max_limit:
        cap = max_limit
    material = list(rows)
    if len(material) > cap:
        return material[:cap], True
    return material, False


def QueryResult(
    *,
    kind: str,
    rows: Sequence[Mapping[str, Any]],
    truncated: bool,
    extras: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the stable JSON envelope every query kind emits."""
    out: MutableMapping[str, Any] = {
        "schema_version": QUERY_RESULT_SCHEMA_VERSION,
        "kind": kind,
        "truncated": bool(truncated),
        "count": len(rows),
        "rows": list(rows),
    }
    if extras:
        out.update(dict(extras))
    return dict(out)
