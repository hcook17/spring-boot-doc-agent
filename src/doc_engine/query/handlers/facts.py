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


def _predicates_present(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    present: set[str] = set()
    for row in rows:
        if isinstance(row, Mapping):
            present.add(str(row.get("predicate")))
    return present


def _validate_predicate(predicate: str | None, rows: Sequence[Mapping[str, Any]]) -> None:
    if not predicate or predicate in KNOWN_PREDICATES:
        return
    present = _predicates_present(rows)
    if predicate not in present:
        raise QueryError(
            f"unknown facts predicate {predicate!r}; valid={sorted(KNOWN_PREDICATES | present)}"
        )


def _fqcn_of(row: Mapping[str, Any]) -> str:
    quals = row.get("qualifiers") or {}
    if isinstance(quals, Mapping):
        return str(quals.get("fqcn") or "")
    return ""


def _file_contains_ok(row: Mapping[str, Any], file_contains: str | None) -> bool:
    if not file_contains:
        return True
    path = str(row.get("file") or "").replace("\\", "/")
    return file_contains.replace("\\", "/") in path


def _subject_contains_ok(row: Mapping[str, Any], subject_contains: str | None) -> bool:
    if not subject_contains:
        return True
    return subject_contains in str(row.get("subject") or "")


def _fqcn_matches(row: Mapping[str, Any], fqcn: str | None) -> bool:
    if not fqcn:
        return True
    return _fqcn_of(row) == fqcn


def _predicate_matches(row: Mapping[str, Any], predicate: str | None) -> bool:
    if not predicate:
        return True
    return row.get("predicate") == predicate


def _fact_passes(
    row: Mapping[str, Any],
    *,
    predicate: str | None,
    file_contains: str | None,
    fqcn: str | None,
    subject_contains: str | None,
) -> bool:
    return (
        _predicate_matches(row, predicate)
        and _file_contains_ok(row, file_contains)
        and _subject_contains_ok(row, subject_contains)
        and _fqcn_matches(row, fqcn)
    )


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
