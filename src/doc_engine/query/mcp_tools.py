"""MCP tool dispatch — library side (adapter is a thin stdio shell)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from doc_engine.query.load import QueryError
from doc_engine.query.packet import run_context_packet
from doc_engine.query.registry import run_query

TOOL_NAMES = [
    "doc_engine_help",
    "context_packet",
    "query_evidence",
    "query_facts",
    "query_entity",
    "query_dependents",
    "query_routes",
    "query_route_trace",
]


def dispatch_tool(name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
    args = dict(arguments or {})
    if name == "doc_engine_help":
        return {
            "tools": TOOL_NAMES,
            "notes": [
                "All tools are read-only over Stage-0 run artifacts.",
                "Prefer context_packet for vague tasks; specialized query_* for filters.",
                "Ast-grep remains required for live structural [Evidenced] citations.",
            ],
        }
    if name == "context_packet":
        run_dir = args.get("run_dir") or args.get("runDir")
        if not run_dir:
            raise QueryError("context_packet requires run_dir")
        return run_context_packet(
            str(args.get("request") or args.get("query") or ""),
            run_dir=Path(str(run_dir)),
            budget_tokens=args.get("budget_tokens") or args.get("budgetTokens"),
            root=Path(str(args["root"])) if args.get("root") else None,
            repo_path=Path(str(args["repo_path"])) if args.get("repo_path") else None,
            drift_report_path=Path(str(args["drift_report"])) if args.get("drift_report") else None,
        )
    if name == "query_evidence":
        return run_query(
            "evidence",
            signals_path=args["signals"],
            root=Path(str(args["root"])) if args.get("root") else None,
            limit=args.get("limit"),
            bucket=args.get("bucket"),
            rule_id=args.get("rule_id"),
            file_contains=args.get("file"),
            match_contains=args.get("match"),
        )
    if name == "query_facts":
        return run_query(
            "facts",
            facts_path=args["facts"],
            root=Path(str(args["root"])) if args.get("root") else None,
            limit=args.get("limit"),
            predicate=args.get("predicate"),
            file_contains=args.get("file"),
            fqcn=args.get("fqcn"),
            subject_contains=args.get("subject_contains"),
        )
    if name == "query_entity":
        return run_query(
            "entity",
            signals_path=args["signals"],
            root=Path(str(args["root"])) if args.get("root") else None,
            limit=args.get("limit"),
            class_name=args.get("class") or args.get("class_name"),
            table=args.get("table"),
            fqcn=args.get("fqcn"),
        )
    if name == "query_dependents":
        return run_query(
            "dependents",
            signals_path=args["signals"],
            edges_path=args.get("edges"),
            root=Path(str(args["root"])) if args.get("root") else None,
            limit=args.get("limit"),
            target_file=args.get("file"),
            target_type=args.get("type"),
            group_id=args.get("group"),
        )
    if name == "query_routes":
        return run_query(
            "routes",
            signals_path=args["signals"],
            root=Path(str(args["root"])) if args.get("root") else None,
            limit=args.get("limit"),
            path_contains=args.get("path_contains"),
            rule_id=args.get("rule_id"),
            file_contains=args.get("file"),
        )
    if name == "query_route_trace":
        return run_query(
            "route-trace",
            signals_path=args["signals"],
            root=Path(str(args["root"])) if args.get("root") else None,
            limit=args.get("limit"),
            path_contains=args.get("path_contains"),
            file_contains=args.get("file"),
        )
    raise QueryError(f"unknown MCP tool: {name}")
