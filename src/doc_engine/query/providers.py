"""PacketProvider strategies over Stage-0 handlers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from doc_engine.query.handlers import dependents, entity, evidence, route_trace


def _item(
    *,
    provider: str,
    path: str | None,
    line: Any,
    match: str | None,
    bucket: str | None,
    reason: str,
    payload: dict[str, Any],
    contested: bool = False,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "path": path,
        "line": line,
        "match": match,
        "bucket": bucket,
        "reason": reason,
        "payload": payload,
        "contested": contested,
    }


class EvidenceProvider:
    name = "evidence"

    def provide(
        self,
        request: str,
        *,
        signals: Mapping[str, Any],
        facts_rows: list[Mapping[str, Any]],
        run_dir: Path,
        limit: int,
    ) -> list[dict[str, Any]]:
        del facts_rows, run_dir, request
        rows = evidence.query_evidence(signals)
        # Prefer security / api when request mentions them; else all buckets capped
        out: list[dict[str, Any]] = []
        for row in rows[: max(limit * 3, limit)]:
            out.append(
                _item(
                    provider=self.name,
                    path=row.get("file"),
                    line=row.get("line"),
                    match=row.get("match"),
                    bucket=str(row.get("bucket") or ""),
                    reason="stage-0 evidence hit",
                    payload=dict(row),
                )
            )
        return out


class FactsProvider:
    name = "facts"

    def provide(
        self,
        request: str,
        *,
        signals: Mapping[str, Any],
        facts_rows: list[Mapping[str, Any]],
        run_dir: Path,
        limit: int,
    ) -> list[dict[str, Any]]:
        del signals, run_dir, request
        out: list[dict[str, Any]] = []
        for row in facts_rows:
            pred = str(row.get("predicate") or "")
            quals = row.get("qualifiers") or {}
            contested = False
            if isinstance(quals, Mapping):
                contested = str(quals.get("status") or "") == "contested"
            if pred not in ("MAPS_TO", "UNPROVEN") and not contested:
                continue
            out.append(
                _item(
                    provider=self.name,
                    path=row.get("file") if isinstance(row.get("file"), str) else None,
                    line=row.get("line"),
                    match=str(row.get("object") or pred),
                    bucket="facts",
                    reason=f"fact {pred}",
                    payload=dict(row),
                    contested=contested or pred == "MAPS_TO",
                )
            )
            if len(out) >= limit * 2:
                break
        return out


class EntityProvider:
    name = "entity"

    def provide(
        self,
        request: str,
        *,
        signals: Mapping[str, Any],
        facts_rows: list[Mapping[str, Any]],
        run_dir: Path,
        limit: int,
    ) -> list[dict[str, Any]]:
        del facts_rows, run_dir, request
        rows = entity.query_entity(signals)
        out: list[dict[str, Any]] = []
        for row in rows[:limit]:
            contested = str(row.get("status") or "") == "contested"
            out.append(
                _item(
                    provider=self.name,
                    path=row.get("file"),
                    line=None,
                    match=str(row.get("table") or row.get("class_name") or ""),
                    bucket="entity",
                    reason="entity_table_map",
                    payload=dict(row),
                    contested=contested,
                )
            )
        return out


class DependentsProvider:
    name = "dependents"

    def provide(
        self,
        request: str,
        *,
        signals: Mapping[str, Any],
        facts_rows: list[Mapping[str, Any]],
        run_dir: Path,
        limit: int,
    ) -> list[dict[str, Any]]:
        del facts_rows, run_dir, request
        rows = dependents.query_dependents(signals)
        out: list[dict[str, Any]] = []
        for row in rows[:limit]:
            out.append(
                _item(
                    provider=self.name,
                    path=row.get("from"),
                    line=None,
                    match=str(row.get("via") or ""),
                    bucket="dependents",
                    reason="import arc",
                    payload=dict(row),
                )
            )
        return out


class RouteTraceProvider:
    name = "route-trace"

    def provide(
        self,
        request: str,
        *,
        signals: Mapping[str, Any],
        facts_rows: list[Mapping[str, Any]],
        run_dir: Path,
        limit: int,
    ) -> list[dict[str, Any]]:
        del facts_rows, run_dir, request
        rows = route_trace.query_route_trace(signals)
        out: list[dict[str, Any]] = []
        for row in rows[:limit]:
            out.append(
                _item(
                    provider=self.name,
                    path=row.get("file"),
                    line=row.get("line"),
                    match=row.get("match"),
                    bucket="route-trace",
                    reason="api_surface × security",
                    payload=dict(row),
                )
            )
        return out


def _hit_row(rel_path: str, hit: Any) -> Mapping[str, Any]:
    if isinstance(hit, Mapping):
        row = dict(hit)
        row.setdefault("file", rel_path)
        return row
    return {"file": rel_path, "reason": str(hit)}


def _rows_from_hit_list(rel_path: str, hits: list[Any]) -> list[Mapping[str, Any]]:
    return [_hit_row(rel_path, hit) for hit in hits]


def _rows_from_zone_hits(rel_path: str, hits: Any) -> list[Mapping[str, Any]]:
    if isinstance(hits, list):
        return _rows_from_hit_list(rel_path, hits)
    return [{"file": rel_path, "reason": "redaction_zone"}]


def _rows_from_zone_mapping(zones: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for rel_path, hits in zones.items():
        rows.extend(_rows_from_zone_hits(str(rel_path), hits))
    return rows


def _rows_from_zone_list(zones: list[Any]) -> list[Mapping[str, Any]]:
    return [row for row in zones if isinstance(row, Mapping)]


def _normalize_redaction_zones(zones: Any) -> list[Mapping[str, Any]]:
    """Production shape: {rel_path: [hits…]} ; also accept list fixtures."""
    if isinstance(zones, Mapping):
        return _rows_from_zone_mapping(zones)
    if isinstance(zones, list):
        return _rows_from_zone_list(zones)
    return []


def _redaction_match(row: Mapping[str, Any]) -> str:
    return str(row.get("reason") or row.get("heuristic") or "redaction_zone")


def _redaction_path(row: Mapping[str, Any]) -> str | None:
    path = row.get("file")
    if isinstance(path, str):
        return path
    return None


def _redaction_item(row: Mapping[str, Any], provider: str) -> dict[str, Any]:
    return _item(
        provider=provider,
        path=_redaction_path(row),
        line=row.get("line"),
        match=_redaction_match(row),
        bucket="redaction",
        reason="redaction_zones risk",
        payload=dict(row),
    )


class RedactionProvider:
    name = "redaction"

    def provide(
        self,
        request: str,
        *,
        signals: Mapping[str, Any],
        facts_rows: list[Mapping[str, Any]],
        run_dir: Path,
        limit: int,
    ) -> list[dict[str, Any]]:
        del facts_rows, run_dir, request
        rows = _normalize_redaction_zones(signals.get("redaction_zones") or [])
        return [_redaction_item(row, self.name) for row in rows[:limit]]


DEFAULT_PROVIDERS = (
    EvidenceProvider(),
    FactsProvider(),
    EntityProvider(),
    DependentsProvider(),
    RouteTraceProvider(),
    RedactionProvider(),
)
