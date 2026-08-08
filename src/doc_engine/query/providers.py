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
        zones = signals.get("redaction_zones") or []
        rows = _normalize_redaction_zones(zones)
        out: list[dict[str, Any]] = []
        for row in rows[:limit]:
            out.append(
                _item(
                    provider=self.name,
                    path=row.get("file") if isinstance(row.get("file"), str) else None,
                    line=row.get("line"),
                    match=str(
                        row.get("reason") or row.get("heuristic") or "redaction_zone"
                    ),
                    bucket="redaction",
                    reason="redaction_zones risk",
                    payload=dict(row),
                )
            )
        return out


def _normalize_redaction_zones(zones: Any) -> list[Mapping[str, Any]]:
    """Production shape: {rel_path: [hits…]} ; also accept list fixtures."""
    rows: list[Mapping[str, Any]] = []
    if isinstance(zones, Mapping):
        for rel, hits in zones.items():
            rows.extend(_rows_from_zone_hits(str(rel), hits))
    elif isinstance(zones, list):
        for row in zones:
            if isinstance(row, Mapping):
                rows.append(row)
    return rows


def _rows_from_zone_hits(rel: str, hits: Any) -> list[Mapping[str, Any]]:
    if isinstance(hits, list):
        out: list[Mapping[str, Any]] = []
        for hit in hits:
            if isinstance(hit, Mapping):
                row = dict(hit)
                row.setdefault("file", rel)
                out.append(row)
            else:
                out.append({"file": rel, "reason": str(hit)})
        return out
    return [{"file": rel, "reason": "redaction_zone"}]


DEFAULT_PROVIDERS = (
    EvidenceProvider(),
    FactsProvider(),
    EntityProvider(),
    DependentsProvider(),
    RouteTraceProvider(),
    RedactionProvider(),
)
