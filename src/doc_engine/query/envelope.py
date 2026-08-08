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
    cap = DEFAULT_LIMIT if limit is None else int(limit)
    cap = max(0, min(cap, max_limit))
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
    if isinstance(obj, Mapping):
        return _cap_mapping(obj, max_list, _depth)
    if isinstance(obj, list):
        return _cap_list(obj, max_list, _depth)
    return obj, False


def _cap_mapping(
    obj: Mapping[str, Any], max_list: int, depth: int
) -> tuple[dict[str, Any], bool]:
    truncated = False
    out: dict[str, Any] = {}
    for key, value in obj.items():
        capped, hit = apply_nested_cap(value, max_list, _depth=depth + 1)
        truncated = truncated or hit
        out[str(key)] = capped
    return out, truncated


def _cap_list(obj: list[Any], max_list: int, depth: int) -> tuple[list[Any], bool]:
    truncated = False
    material = list(obj)
    if depth > 0 and len(material) > max_list:
        material = material[:max_list]
        truncated = True
    items_out: list[Any] = []
    for item in material:
        capped, hit = apply_nested_cap(item, max_list, _depth=depth + 1)
        truncated = truncated or hit
        items_out.append(capped)
    return items_out, truncated


def build_query_result(
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


# Historical PascalCase name — prefer ``build_query_result``.
QueryResult = build_query_result
