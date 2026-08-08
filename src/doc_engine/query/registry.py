"""Thin factory / dispatch for query kinds — delegates to QueryKindSpec registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from doc_engine.query.envelope import QueryResult, apply_limit
from doc_engine.query.kinds import QUERY_KIND_SPECS, get_query_kind_spec
from doc_engine.query.load import QueryError, QueryMissingError, load_json, load_jsonl
from doc_engine.query.rank import truncate_nested_lists_that_exceed_cap
from doc_engine.query.schema_check import validate_envelope

Handler = Callable[..., list[dict[str, Any]]]

# Backward-compatible handler map derived from single registry (OCP).
_HANDLERS: dict[str, Handler] = {k: s.handler for k, s in QUERY_KIND_SPECS.items()}


def get_query_handler(kind: str) -> Handler:
    return get_query_kind_spec(kind).handler


def _cap_nested_fanout_in_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    any_truncated = False
    capped_rows: list[dict[str, Any]] = []
    for row in rows:
        capped, did = truncate_nested_lists_that_exceed_cap(row)
        any_truncated = any_truncated or did
        capped_rows.append(capped if isinstance(capped, dict) else row)
    return capped_rows, any_truncated


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
    validate: bool = True,
    **filters: Any,
) -> dict[str, Any]:
    """Load artifacts as needed, run the strategy handler, apply limit envelope."""
    spec = get_query_kind_spec(kind)
    root_path = Path(root) if root else None
    sig = signals
    if sig is None and signals_path is not None:
        loaded = load_json(signals_path, root=root_path)
        if not isinstance(loaded, Mapping):
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

    handler = spec.handler
    if spec.requires_signals:
        if sig is None:
            raise QueryMissingError("signals required for this query kind")
        if spec.accepts_edges:
            rows = handler(sig, edges=ed, **filters)
        else:
            rows = handler(sig, **filters)
    elif spec.requires_facts:
        if fr is None:
            raise QueryMissingError("facts required for facts query")
        rows = handler(fr, **filters)
    else:
        rows = handler(**filters)

    rows, nested_truncated = _cap_nested_fanout_in_rows(rows)
    capped, truncated = apply_limit(rows, limit)
    truncated = truncated or nested_truncated
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
    if nested_truncated:
        extras["nested_truncated"] = True
    result = QueryResult(
        kind=kind.replace("_", "-"),
        rows=capped,
        truncated=truncated,
        extras=extras,
    )
    if validate:
        validate_envelope("query_result", result)
    return result
