"""Entity / table map lookup over spring_signals.entity_table_map."""

from __future__ import annotations

from typing import Any, Mapping


def _candidate_value_equals(candidate: Any, field: str, want: str) -> bool:
    return isinstance(candidate, Mapping) and str(candidate.get(field) or "") == want


def _candidate_field_matches(entry: Mapping[str, Any], field: str, want: str) -> bool:
    if str(entry.get(field) or "") == want:
        return True
    cands = entry.get("candidates") or []
    if not isinstance(cands, list):
        return False
    return any(_candidate_value_equals(candidate, field, want) for candidate in cands)


def _optional_field_matches(
    entry: Mapping[str, Any], field: str, want: str | None
) -> bool:
    if not want:
        return True
    return _candidate_field_matches(entry, field, want)


def _row_matches(
    entry: Mapping[str, Any],
    name: str,
    *,
    class_name: str | None,
    table: str | None,
    fqcn: str | None,
) -> bool:
    if class_name and str(name) != class_name:
        return False
    return _optional_field_matches(entry, "table", table) and _optional_field_matches(
        entry, "fqcn", fqcn
    )


def _entity_entry(name: Any, raw: Mapping[str, Any]) -> dict[str, Any]:
    entry = dict(raw)
    entry["class_name"] = str(name)
    entry.setdefault("candidates", [])
    return entry


def _maybe_entity_row(
    name: Any,
    raw: Any,
    *,
    class_name: str | None,
    table: str | None,
    fqcn: str | None,
) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    entry = _entity_entry(name, raw)
    if not _row_matches(
        entry, str(name), class_name=class_name, table=table, fqcn=fqcn
    ):
        return None
    return entry


def query_entity(
    signals: Mapping[str, Any],
    *,
    class_name: str | None = None,
    table: str | None = None,
    fqcn: str | None = None,
) -> list[dict[str, Any]]:
    etm = signals.get("entity_table_map") or {}
    if not isinstance(etm, Mapping):
        return []
    rows: list[dict[str, Any]] = []
    for name, raw in etm.items():
        entry = _maybe_entity_row(
            name, raw, class_name=class_name, table=table, fqcn=fqcn
        )
        if entry is not None:
            rows.append(entry)
    return rows
