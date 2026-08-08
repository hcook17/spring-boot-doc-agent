"""Facts ledger filters over facts.jsonl rows."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from doc_engine.query.load import QueryError

KNOWN_PREDICATES = frozenset(
    {
        "MAPS_TO",
        "UNPROVEN",
        "REFERENCES",
        "DECLARES",
        "EXTENDS",
        "IMPLEMENTS",
        "ANNOTATED_WITH",
        "X",
    }
)


def query_facts(
    rows: Sequence[Mapping[str, Any]],
    *,
    predicate: str | None = None,
    file_contains: str | None = None,
    fqcn: str | None = None,
    subject_contains: str | None = None,
) -> list[dict[str, Any]]:
    if predicate and predicate not in KNOWN_PREDICATES:
        present = {str(r.get("predicate")) for r in rows if isinstance(r, Mapping)}
        if predicate not in present:
            valid = sorted(KNOWN_PREDICATES | present)
            raise QueryError(f"unknown facts predicate {predicate!r}; valid={valid}")
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
