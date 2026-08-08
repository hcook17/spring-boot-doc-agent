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


def _validate_predicate(predicate: str | None, rows: Sequence[Mapping[str, Any]]) -> None:
    if not predicate or predicate in KNOWN_PREDICATES:
        return
    present = set()
    for row in rows:
        if isinstance(row, Mapping):
            present.add(str(row.get("predicate")))
    if predicate not in present:
        raise QueryError(
            f"unknown facts predicate {predicate!r}; valid={sorted(KNOWN_PREDICATES | present)}"
        )


def _fqcn_of(row: Mapping[str, Any]) -> str:
    quals = row.get("qualifiers") or {}
    if isinstance(quals, Mapping):
        return str(quals.get("fqcn") or "")
    return ""


def _fact_passes(
    row: Mapping[str, Any],
    *,
    predicate: str | None,
    file_contains: str | None,
    fqcn: str | None,
    subject_contains: str | None,
) -> bool:
    if predicate and row.get("predicate") != predicate:
        return False
    if file_contains:
        path = str(row.get("file") or "").replace("\\", "/")
        if file_contains.replace("\\", "/") not in path:
            return False
    if subject_contains and subject_contains not in str(row.get("subject") or ""):
        return False
    if fqcn and _fqcn_of(row) != fqcn:
        return False
    return True


def query_facts(
    rows: Sequence[Mapping[str, Any]],
    *,
    predicate: str | None = None,
    file_contains: str | None = None,
    fqcn: str | None = None,
    subject_contains: str | None = None,
) -> list[dict[str, Any]]:
    _validate_predicate(predicate, rows)
    out: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        if _fact_passes(
            row,
            predicate=predicate,
            file_contains=file_contains,
            fqcn=fqcn,
            subject_contains=subject_contains,
        ):
            out.append(row)
    return out
