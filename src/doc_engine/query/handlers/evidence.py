"""Evidence bucket filters over spring_signals.json."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from doc_engine.query.load import QueryError


def _match_text(row: Mapping[str, Any], needle: str | None) -> bool:
    if not needle:
        return True
    return needle in str(row.get("match") or "")


def _file_match(row: Mapping[str, Any], needle: str | None) -> bool:
    if not needle:
        return True
    path = str(row.get("file") or "").replace("\\", "/")
    return needle.replace("\\", "/") in path


def _resolve_buckets(evidence: Mapping[str, Any], bucket: str | None) -> Sequence[str]:
    known = sorted(str(bucket_name) for bucket_name in evidence.keys())
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
    return _match_text(row, match_contains)


def _normalize_bucket_row(raw: Mapping[str, Any], name: str) -> dict[str, Any]:
    row = dict(raw)
    row.setdefault("bucket", name)
    return row


def _maybe_bucket_row(
    raw: Any,
    name: str,
    *,
    rule_id: str | None,
    file_contains: str | None,
    match_contains: str | None,
) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    row = _normalize_bucket_row(raw, name)
    if not _row_passes(
        row,
        rule_id=rule_id,
        file_contains=file_contains,
        match_contains=match_contains,
    ):
        return None
    return row


def _filter_bucket(
    evidence: Mapping[str, Any],
    name: str,
    *,
    rule_id: str | None,
    file_contains: str | None,
    match_contains: str | None,
) -> list[dict[str, Any]]:
    entries = evidence.get(name) or []
    if not isinstance(entries, list):
        return []
    rows: list[dict[str, Any]] = []
    for raw in entries:
        row = _maybe_bucket_row(
            raw,
            name,
            rule_id=rule_id,
            file_contains=file_contains,
            match_contains=match_contains,
        )
        if row is not None:
            rows.append(row)
    return rows


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
    rows: list[dict[str, Any]] = []
    for name in _resolve_buckets(evidence, bucket):
        rows.extend(
            _filter_bucket(
                evidence,
                name,
                rule_id=rule_id,
                file_contains=file_contains,
                match_contains=match_contains,
            )
        )
    return rows
