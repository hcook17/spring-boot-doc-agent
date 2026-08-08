"""Entity / table map lookup over spring_signals.entity_table_map."""

from __future__ import annotations

from typing import Any, Mapping


def _candidate_field_matches(entry: Mapping[str, Any], field: str, want: str) -> bool:
    if str(entry.get(field) or "") == want:
        return True
    cands = entry.get("candidates") or []
    if not isinstance(cands, list):
        return False
    for candidate in cands:
        if isinstance(candidate, Mapping) and str(candidate.get(field) or "") == want:
            return True
    return False


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
        entry = dict(raw)
        entry["class_name"] = str(name)
        entry.setdefault("candidates", [])
        if _row_matches(
            entry, str(name), class_name=class_name, table=table, fqcn=fqcn
        ):
            rows.append(entry)
    return rows
