"""Entity / table map lookup over spring_signals.entity_table_map."""

from __future__ import annotations

from typing import Any, Mapping


def _candidate_field_matches(entry: Mapping[str, Any], field: str, want: str) -> bool:
    if str(entry.get(field) or "") == want:
        return True
    cands = entry.get("candidates") or []
    if not isinstance(cands, list):
        return False
    return any(
        isinstance(c, Mapping) and str(c.get(field) or "") == want for c in cands
    )


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
    if table and not _candidate_field_matches(entry, "table", table):
        return False
    if fqcn and not _candidate_field_matches(entry, "fqcn", fqcn):
        return False
    return True


def _normalize_entry(name: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    entry = dict(raw)
    entry["class_name"] = str(name)
    if "candidates" not in entry:
        entry["candidates"] = []
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
        if not isinstance(raw, Mapping):
            continue
        entry = _normalize_entry(str(name), raw)
        if not _row_matches(
            entry, str(name), class_name=class_name, table=table, fqcn=fqcn
        ):
            continue
        rows.append(entry)
    return rows
