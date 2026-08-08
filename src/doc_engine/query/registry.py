"""Thin factory / dispatch for query kinds — delegates to QueryKindSpec registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from doc_engine.query.envelope import apply_limit, build_query_result
from doc_engine.query.kinds import QUERY_KIND_SPECS, get_query_kind_spec
from doc_engine.query.load import QueryError, QueryMissingError, load_json, load_jsonl
from doc_engine.query.rank import truncate_nested_lists_that_exceed_cap
from doc_engine.query.schema_check import validate_envelope

Handler = Callable[..., list[dict[str, Any]]]

# Backward-compatible handler map derived from single registry (OCP).
_HANDLERS: dict[str, Handler] = {
    kind: spec.handler for kind, spec in QUERY_KIND_SPECS.items()
}


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


def _load_signals(
    signals: Mapping[str, Any] | None,
    signals_path: Path | str | None,
    root_path: Path | None,
) -> Mapping[str, Any] | None:
    if signals is not None or signals_path is None:
        return signals
    loaded = load_json(signals_path, root=root_path)
    if not isinstance(loaded, Mapping):
        raise QueryError("signals artifact must be a JSON object")
    return loaded


def _load_facts(
    facts_rows: list[Mapping[str, Any]] | None,
    facts_path: Path | str | None,
    root_path: Path | None,
) -> list[Mapping[str, Any]] | None:
    if facts_rows is not None or facts_path is None:
        return facts_rows
    return load_jsonl(facts_path, root=root_path)


def _load_edges(
    edges: Mapping[str, Any] | None,
    edges_path: Path | str | None,
    root_path: Path | None,
) -> Mapping[str, Any] | None:
    if edges is not None or edges_path is None:
        return edges
    loaded_e = load_json(edges_path, root=root_path)
    if isinstance(loaded_e, Mapping):
        return loaded_e
    return edges


def _invoke_signals_handler(
    handler: Handler,
    *,
    accepts_edges: bool,
    sig: Mapping[str, Any] | None,
    ed: Mapping[str, Any] | None,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    if sig is None:
        raise QueryMissingError("signals required for this query kind")
    if accepts_edges:
        return handler(sig, edges=ed, **filters)
    return handler(sig, **filters)


def _invoke_facts_handler(
    handler: Handler,
    fr: list[Mapping[str, Any]] | None,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    if fr is None:
        raise QueryMissingError("facts required for facts query")
    return handler(fr, **filters)


def _invoke_handler(
    spec: Any,
    *,
    sig: Mapping[str, Any] | None,
    fr: list[Mapping[str, Any]] | None,
    ed: Mapping[str, Any] | None,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    handler = spec.handler
    if spec.requires_signals:
        return _invoke_signals_handler(
            handler,
            accepts_edges=spec.accepts_edges,
            sig=sig,
            ed=ed,
            filters=filters,
        )
    if spec.requires_facts:
        return _invoke_facts_handler(handler, fr, filters)
    return handler(**filters)


def _extras_for_kind(kind: str, nested_truncated: bool) -> dict[str, Any]:
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
    return extras


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
    sig = _load_signals(signals, signals_path, root_path)
    fr = _load_facts(facts_rows, facts_path, root_path)
    ed = _load_edges(edges, edges_path, root_path)
    rows = _invoke_handler(spec, sig=sig, fr=fr, ed=ed, filters=filters)
    rows, nested_truncated = _cap_nested_fanout_in_rows(rows)
    capped, truncated = apply_limit(rows, limit)
    truncated = truncated or nested_truncated
    result = build_query_result(
        kind=kind.replace("_", "-"),
        rows=capped,
        truncated=truncated,
        extras=_extras_for_kind(kind, nested_truncated),
    )
    if validate:
        validate_envelope("query_result", result)
    return result
