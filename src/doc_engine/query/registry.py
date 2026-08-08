"""Thin factory / dispatch for query kinds."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from doc_engine.query.envelope import QueryResult, apply_limit
from doc_engine.query.handlers import dependents, entity, evidence, facts, route_trace, routes
from doc_engine.query.load import load_json, load_jsonl

Handler = Callable[..., list[dict[str, Any]]]

_HANDLERS: dict[str, Handler] = {
    "evidence": evidence.query_evidence,
    "routes": routes.query_routes,
    "facts": facts.query_facts,
    "entity": entity.query_entity,
    "dependents": dependents.query_dependents,
    "route-trace": route_trace.query_route_trace,
    "route_trace": route_trace.query_route_trace,
}


def get_query_handler(kind: str) -> Handler:
    try:
        return _HANDLERS[kind]
    except KeyError as exc:
        raise KeyError(f"unknown query kind: {kind!r}") from exc


def run_query(
    kind: str,
    *,
    signals: Mapping[str, Any] | None = None,
    signals_path: Path | str | None = None,
    facts_rows: list[Mapping[str, Any]] | None = None,
    facts_path: Path | str | None = None,
    edges: Mapping[str, Any] | None = None,
    edges_path: Path | str | None = None,
    root: Path | str | None = None,
    limit: int | None = None,
    **filters: Any,
) -> dict[str, Any]:
    """Load artifacts as needed, run the strategy handler, apply limit envelope."""
    root_path = Path(root) if root else None
    sig = signals
    if sig is None and signals_path is not None:
        loaded = load_json(signals_path, root=root_path)
        if not isinstance(loaded, Mapping):
            from doc_engine.query.load import QueryError

            raise QueryError("signals artifact must be a JSON object")
        sig = loaded

    fr = facts_rows
    if fr is None and facts_path is not None:
        fr = load_jsonl(facts_path, root=root_path)

    ed = edges
    if ed is None and edges_path is not None:
        loaded_e = load_json(edges_path, root=root_path)
        if isinstance(loaded_e, Mapping):
            ed = loaded_e

    handler = get_query_handler(kind)
    if kind in ("evidence", "routes", "entity", "dependents", "route-trace", "route_trace"):
        if sig is None:
            from doc_engine.query.load import QueryMissingError

            raise QueryMissingError("signals required for this query kind")
        if kind == "dependents":
            rows = handler(sig, edges=ed, **filters)
        else:
            rows = handler(sig, **filters)
    elif kind == "facts":
        if fr is None:
            from doc_engine.query.load import QueryMissingError

            raise QueryMissingError("facts required for facts query")
        rows = handler(fr, **filters)
    else:
        rows = handler(**filters)

    capped, truncated = apply_limit(rows, limit)
    extras: dict[str, Any] = {}
    if kind == "dependents":
        extras["hard_stops"] = [
            "import/package text only",
            "no interface-mediated DI (@Autowired → implementer)",
            "wildcard imports may be package-fanout",
        ]
    if kind in ("route-trace", "route_trace"):
        extras["hard_stops"] = [
            "guards are same-file security evidence only",
            "not full SecurityFilterChain path matching",
        ]
    return QueryResult(kind=kind.replace("_", "-"), rows=capped, truncated=truncated, extras=extras)
