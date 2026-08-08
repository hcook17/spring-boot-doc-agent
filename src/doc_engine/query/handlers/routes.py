"""Routes — specialized evidence filter over api_surface."""

from __future__ import annotations

from typing import Any, Mapping

from doc_engine.query.handlers.evidence import query_evidence


def query_routes(
    signals: Mapping[str, Any],
    *,
    path_contains: str | None = None,
    rule_id: str | None = None,
    file_contains: str | None = None,
) -> list[dict[str, Any]]:
    return query_evidence(
        signals,
        bucket="api_surface",
        rule_id=rule_id,
        file_contains=file_contains,
        match_contains=path_contains,
    )
