"""Evidence bucket filters over spring_signals.json."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from doc_engine.query.load import QueryError


def _match_text(row: Mapping[str, Any], needle: str | None) -> bool:
    if not needle:
        return True
    hay = str(row.get("match") or "")
    return needle in hay


def _file_match(row: Mapping[str, Any], needle: str | None) -> bool:
    if not needle:
        return True
    path = str(row.get("file") or "").replace("\\", "/")
    return needle.replace("\\", "/") in path


def _resolve_buckets(evidence: Mapping[str, Any], bucket: str | None) -> Sequence[str]:
    known = sorted(str(k) for k in evidence.keys())
    if not bucket:
        return known
    if bucket not in evidence:
        raise QueryError(f"unknown evidence bucket {bucket!r}; valid={known}")
    return [bucket]


def _row_passes(
    row: Mapping[str, Any],
    *,
    rule_id: str | None,
    file_contains: str | None,
    match_contains: str | None,
) -> bool:
    if rule_id and row.get("rule_id") != rule_id:
        return False
    if not _file_match(row, file_contains):
        return False
    if not _match_text(row, match_contains):
        return False
    return True


def query_evidence(
    signals: Mapping[str, Any],
    *,
    bucket: str | None = None,
    rule_id: str | None = None,
    file_contains: str | None = None,
    match_contains: str | None = None,
) -> list[dict[str, Any]]:
    evidence = signals.get("evidence") or {}
    if not isinstance(evidence, Mapping):
        return []
    buckets = _resolve_buckets(evidence, bucket)

    rows: list[dict[str, Any]] = []
    for name in buckets:
        entries = evidence.get(name) or []
        if not isinstance(entries, list):
            continue
        for raw in entries:
            if not isinstance(raw, Mapping):
                continue
            row = dict(raw)
            row.setdefault("bucket", name)
            if not _row_passes(
                row,
                rule_id=rule_id,
                file_contains=file_contains,
                match_contains=match_contains,
            ):
                continue
            rows.append(row)
    return rows
