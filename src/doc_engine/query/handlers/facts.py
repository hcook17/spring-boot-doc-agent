"""Facts ledger filters over facts.jsonl rows."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def query_facts(
    rows: Sequence[Mapping[str, Any]],
    *,
    predicate: str | None = None,
    file_contains: str | None = None,
    fqcn: str | None = None,
    subject_contains: str | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        if predicate and row.get("predicate") != predicate:
            continue
        if file_contains:
            path = str(row.get("file") or "").replace("\\", "/")
            if file_contains.replace("\\", "/") not in path:
                continue
        if subject_contains and subject_contains not in str(row.get("subject") or ""):
            continue
        if fqcn:
            quals = row.get("qualifiers") or {}
            row_fqcn = ""
            if isinstance(quals, Mapping):
                row_fqcn = str(quals.get("fqcn") or "")
            if row_fqcn != fqcn:
                continue
        out.append(row)
    return out
