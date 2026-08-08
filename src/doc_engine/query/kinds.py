"""QueryKindSpec — single registry driving CLI/MCP/dispatch (OCP)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from doc_engine.query.handlers import dependents, entity, evidence, facts, route_trace, routes

Handler = Callable[..., list[dict[str, Any]]]


@dataclass(frozen=True)
class QueryKindSpec:
    """One place to declare a query kind (open for extension, closed for modification)."""

    kind: str
    handler: Handler
    requires_signals: bool = True
    requires_facts: bool = False
    accepts_edges: bool = False
    mcp_tool_name: str | None = None
    filter_keys: tuple[str, ...] = ()
    description: str = ""

    def mcp_input_properties(self) -> dict[str, Any]:
        props: dict[str, Any] = {}
        if self.requires_signals:
            props["signals"] = {"type": "string"}
        if self.requires_facts:
            props["facts"] = {"type": "string"}
        if self.accepts_edges:
            props["edges"] = {"type": "string"}
        for key in self.filter_keys:
            props[key] = {"type": "string"}
        props["limit"] = {"type": "integer"}
        return props


def build_default_query_kind_specs() -> dict[str, QueryKindSpec]:
    specs = [
        QueryKindSpec(
            kind="evidence",
            handler=evidence.query_evidence,
            mcp_tool_name="query_evidence",
            filter_keys=("bucket", "rule_id", "file", "match"),
            description="filter spring_signals evidence buckets",
        ),
        QueryKindSpec(
            kind="routes",
            handler=routes.query_routes,
            mcp_tool_name="query_routes",
            filter_keys=("path_contains", "rule_id", "file"),
            description="api_surface evidence filter",
        ),
        QueryKindSpec(
            kind="facts",
            handler=facts.query_facts,
            requires_signals=False,
            requires_facts=True,
            mcp_tool_name="query_facts",
            filter_keys=("predicate", "file", "fqcn", "subject_contains"),
            description="filter facts.jsonl",
        ),
        QueryKindSpec(
            kind="entity",
            handler=entity.query_entity,
            mcp_tool_name="query_entity",
            filter_keys=("class", "table", "fqcn"),
            description="entity_table_map lookup",
        ),
        QueryKindSpec(
            kind="dependents",
            handler=dependents.query_dependents,
            accepts_edges=True,
            mcp_tool_name="query_dependents",
            filter_keys=("file", "type", "group"),
            description="import dependents",
        ),
        QueryKindSpec(
            kind="route-trace",
            handler=route_trace.query_route_trace,
            mcp_tool_name="query_route_trace",
            filter_keys=("path_contains", "file"),
            description="api_surface × same-file security",
        ),
    ]
    by_kind = {s.kind: s for s in specs}
    by_kind["route_trace"] = by_kind["route-trace"]
    return by_kind


QUERY_KIND_SPECS: dict[str, QueryKindSpec] = build_default_query_kind_specs()


def list_mcp_tool_names() -> list[str]:
    names = ["doc_engine_help", "context_packet"]
    for spec in QUERY_KIND_SPECS.values():
        if spec.mcp_tool_name and spec.mcp_tool_name not in names:
            names.append(spec.mcp_tool_name)
    return names


def get_query_kind_spec(kind: str) -> QueryKindSpec:
    try:
        return QUERY_KIND_SPECS[kind]
    except KeyError as exc:
        raise KeyError(f"unknown query kind: {kind!r}; known={sorted(set(QUERY_KIND_SPECS))}") from exc
