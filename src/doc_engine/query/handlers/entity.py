"""Entity / table map lookup over spring_signals.entity_table_map."""

from __future__ import annotations

from typing import Any, Mapping


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
        if class_name and str(name) != class_name:
            continue
        if table and str(entry.get("table") or "") != table:
            # also check contested candidates
            cands = entry.get("candidates") or []
            if not (
                isinstance(cands, list)
                and any(
                    isinstance(c, Mapping) and str(c.get("table") or "") == table
                    for c in cands
                )
            ):
                continue
        if fqcn and str(entry.get("fqcn") or "") != fqcn:
            cands = entry.get("candidates") or []
            if not (
                isinstance(cands, list)
                and any(
                    isinstance(c, Mapping) and str(c.get("fqcn") or "") == fqcn
                    for c in cands
                )
            ):
                continue
        if "candidates" not in entry:
            entry["candidates"] = []
        rows.append(entry)
    return rows
