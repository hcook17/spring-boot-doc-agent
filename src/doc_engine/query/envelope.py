"""Query result envelope — bounded output for agent consumers."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Sequence

QUERY_RESULT_SCHEMA_VERSION = 1
DEFAULT_LIMIT = 50
MAX_LIMIT = 500
DEFAULT_NESTED_LIST_CAP = 50


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


def apply_nested_cap(
    obj: Any,
    max_list: int = DEFAULT_NESTED_LIST_CAP,
    *,
    _depth: int = 0,
) -> tuple[Any, bool]:
    """Truncate nested lists (guards, candidates, …) and report whether any were cut.

    Top-level lists (query ``rows``) are walked but not length-capped here —
    ``apply_limit`` owns that. Nested lists at depth ≥ 1 are capped to
    ``max_list`` and recurse into elements.
    """
    truncated = False
    if isinstance(obj, Mapping):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            capped, hit = apply_nested_cap(value, max_list, _depth=_depth + 1)
            truncated = truncated or hit
            out[str(key)] = capped
        return out, truncated
    if isinstance(obj, list):
        if _depth == 0:
            items_out: list[Any] = []
            for item in obj:
                capped, hit = apply_nested_cap(item, max_list, _depth=_depth + 1)
                truncated = truncated or hit
                items_out.append(capped)
            return items_out, truncated
        material = list(obj)
        if len(material) > max_list:
            material = material[:max_list]
            truncated = True
        items_out = []
        for item in material:
            capped, hit = apply_nested_cap(item, max_list, _depth=_depth + 1)
            truncated = truncated or hit
            items_out.append(capped)
        return items_out, truncated
    return obj, False


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
