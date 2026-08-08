"""route_trace — join api_surface mappings with co-located security evidence."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from doc_engine.query.handlers.evidence import query_evidence


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
    # Prefer mapping rule rows; still include controllers if path filter empty
    security = query_evidence(signals, bucket="security")
    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in security:
        path = str(row.get("file") or "").replace("\\", "/")
        by_file[path].append(dict(row))

    rows: list[dict[str, Any]] = []
    for raw in mappings:
        rule = str(raw.get("rule_id") or "")
        # Keep mapping-ish rows when path_contains set; otherwise all api_surface
        if path_contains and "mapping" not in rule and "endpoint" not in rule:
            # still allow if match text has the path
            if path_contains not in str(raw.get("match") or ""):
                continue
        file_path = str(raw.get("file") or "").replace("\\", "/")
        packet = {
            "file": raw.get("file"),
            "line": raw.get("line"),
            "match": raw.get("match"),
            "rule_id": raw.get("rule_id"),
            "guards": list(by_file.get(file_path, [])),
        }
        rows.append(packet)
    return rows
