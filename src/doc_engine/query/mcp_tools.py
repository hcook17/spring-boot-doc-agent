"""MCP tool dispatch — library side (adapter is a thin stdio shell)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from doc_engine.core.walk import is_path_inside_root
from doc_engine.query.kinds import list_mcp_tool_names
from doc_engine.query.load import QueryError, QueryPathError, require_server_root
from doc_engine.query.packet import run_context_packet
from doc_engine.query.registry import run_query

TOOL_NAMES = list_mcp_tool_names()


def _server_root() -> Path:
    return require_server_root()


def _pin_path(raw: str | Path, *, root: Path) -> Path:
    p = Path(raw)
    try:
        resolved = p.resolve()
    except OSError as exc:
        raise QueryPathError(f"cannot resolve path: {p}") from exc
    if not is_path_inside_root(str(resolved), str(root)):
        raise QueryPathError(f"path escapes server root: {p}")
    return resolved


def _dispatch_help() -> dict[str, Any]:
    return {
        "tools": TOOL_NAMES,
        "notes": [
            "All tools are read-only over Stage-0 run artifacts.",
            "FS root is server-derived (DOC_ENGINE_ROOT / DOC_ENGINE_RUN_DIR).",
            "Prefer context_packet for vague tasks; specialized query_* for filters.",
            "Ast-grep remains required for live structural [Evidenced] citations.",
        ],
    }


def _dispatch_context_packet(args: dict[str, Any], root: Path) -> dict[str, Any]:
    run_dir = args.get("run_dir") or args.get("runDir")
    if not run_dir:
        raise QueryError("context_packet requires run_dir")
    run_path = _pin_path(str(run_dir), root=root)
    return run_context_packet(
        str(args.get("request") or args.get("query") or ""),
        run_dir=run_path,
        budget_tokens=args.get("budget_tokens") or args.get("budgetTokens"),
        root=root,
        repo_path=_pin_path(str(args["repo_path"]), root=root) if args.get("repo_path") else None,
        drift_report_path=(
            _pin_path(str(args["drift_report"]), root=root) if args.get("drift_report") else None
        ),
    )


def _query_evidence(args: dict[str, Any], root: Path) -> dict[str, Any]:
    return run_query(
        "evidence",
        signals_path=_pin_path(args["signals"], root=root),
        root=root,
        limit=args.get("limit"),
        bucket=args.get("bucket"),
        rule_id=args.get("rule_id"),
        file_contains=args.get("file"),
        match_contains=args.get("match"),
    )


def _query_facts(args: dict[str, Any], root: Path) -> dict[str, Any]:
    return run_query(
        "facts",
        facts_path=_pin_path(args["facts"], root=root),
        root=root,
        limit=args.get("limit"),
        predicate=args.get("predicate"),
        file_contains=args.get("file"),
        fqcn=args.get("fqcn"),
        subject_contains=args.get("subject_contains"),
    )


def _query_entity(args: dict[str, Any], root: Path) -> dict[str, Any]:
    return run_query(
        "entity",
        signals_path=_pin_path(args["signals"], root=root),
        root=root,
        limit=args.get("limit"),
        class_name=args.get("class") or args.get("class_name"),
        table=args.get("table"),
        fqcn=args.get("fqcn"),
    )


def _query_dependents(args: dict[str, Any], root: Path) -> dict[str, Any]:
    return run_query(
        "dependents",
        signals_path=_pin_path(args["signals"], root=root),
        edges_path=_pin_path(args["edges"], root=root) if args.get("edges") else None,
        root=root,
        limit=args.get("limit"),
        target_file=args.get("file"),
        target_type=args.get("type"),
        group_id=args.get("group"),
    )


def _query_routes(args: dict[str, Any], root: Path) -> dict[str, Any]:
    return run_query(
        "routes",
        signals_path=_pin_path(args["signals"], root=root),
        root=root,
        limit=args.get("limit"),
        path_contains=args.get("path_contains"),
        rule_id=args.get("rule_id"),
        file_contains=args.get("file"),
    )


def _query_route_trace(args: dict[str, Any], root: Path) -> dict[str, Any]:
    return run_query(
        "route-trace",
        signals_path=_pin_path(args["signals"], root=root),
        root=root,
        limit=args.get("limit"),
        path_contains=args.get("path_contains"),
        file_contains=args.get("file"),
    )


_TOOL_DISPATCH: dict[str, Callable[[dict[str, Any], Path], dict[str, Any]]] = {
    "query_evidence": _query_evidence,
    "query_facts": _query_facts,
    "query_entity": _query_entity,
    "query_dependents": _query_dependents,
    "query_routes": _query_routes,
    "query_route_trace": _query_route_trace,
}


def dispatch_tool(name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
    args = dict(arguments or {})
    # Never honor caller-supplied root (confused deputy).
    args.pop("root", None)

    if name == "doc_engine_help":
        return _dispatch_help()

    root = _server_root()

    if name == "context_packet":
        return _dispatch_context_packet(args, root)

    runner = _TOOL_DISPATCH.get(name)
    if runner is None:
        raise QueryError(f"unknown MCP tool: {name}")
    return runner(args, root)
