"""route_trace — join api_surface mappings with co-located security evidence."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from doc_engine.query.handlers.evidence import query_evidence


def _security_by_file(signals: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in query_evidence(signals, bucket="security"):
        path = str(row.get("file") or "").replace("\\", "/")
        by_file[path].append(dict(row))
    return by_file


def _mapping_row_kept(raw: Mapping[str, Any], path_contains: str | None) -> bool:
    if not path_contains:
        return True
    rule = str(raw.get("rule_id") or "")
    if "mapping" in rule or "endpoint" in rule:
        return True
    return path_contains in str(raw.get("match") or "")


def _route_packet(
    raw: Mapping[str, Any], by_file: Mapping[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    file_path = str(raw.get("file") or "").replace("\\", "/")
    return {
        "file": raw.get("file"),
        "line": raw.get("line"),
        "match": raw.get("match"),
        "rule_id": raw.get("rule_id"),
        "guards": list(by_file.get(file_path, [])),
    }


def query_route_trace(
    signals: Mapping[str, Any],
    *,
    path_contains: str | None = None,
    file_contains: str | None = None,
) -> list[dict[str, Any]]:
    """Bounded (path, method?, file, line, guards[]) packets.

    Guards are security evidence rows on the **same file** as the mapping.
    This is not full SecurityFilterChain DSL matching — see maturation plan.
    """
    mappings = query_evidence(
        signals,
        bucket="api_surface",
        file_contains=file_contains,
        match_contains=path_contains,
    )
    by_file = _security_by_file(signals)
    return [
        _route_packet(raw, by_file)
        for raw in mappings
        if _mapping_row_kept(raw, path_contains)
    ]
