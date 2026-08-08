#!/usr/bin/env python3
"""Read-only typed queries over Stage-0 artifacts.

Run with: python -m doc_engine.tools.query_artifacts <kind> …

Kinds: evidence | routes | facts | entity | dependents | route-trace | context-packet
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from doc_engine.query.envelope import DEFAULT_LIMIT
from doc_engine.query.load import QueryError, require_server_root
from doc_engine.query.registry import run_query


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root",
        default=None,
        help="containment root (default: parent of artifact path, or DOC_ENGINE_ROOT)",
    )
    common.add_argument(
        "--unsafe-no-root",
        action="store_true",
        help="CLI-only escape hatch — refuse on MCP; not recommended",
    )
    common.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"max rows (default {DEFAULT_LIMIT}; hard-clamped)",
    )

    p = argparse.ArgumentParser(
        description="Query Stage-0 artifacts (capped typed read views).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="kind", required=True)

    ev = sub.add_parser(
        "evidence",
        parents=[common],
        help="filter spring_signals evidence buckets",
    )
    ev.add_argument("--signals", required=True)
    ev.add_argument("--bucket", default=None)
    ev.add_argument("--rule-id", default=None)
    ev.add_argument("--file", dest="file_contains", default=None)
    ev.add_argument("--match", dest="match_contains", default=None)

    rt = sub.add_parser("routes", parents=[common], help="api_surface evidence filter")
    rt.add_argument("--signals", required=True)
    rt.add_argument("--path-contains", default=None)
    rt.add_argument("--rule-id", default=None)
    rt.add_argument("--file", dest="file_contains", default=None)

    fa = sub.add_parser("facts", parents=[common], help="filter facts.jsonl")
    fa.add_argument("--facts", required=True)
    fa.add_argument("--predicate", default=None)
    fa.add_argument("--file", dest="file_contains", default=None)
    fa.add_argument("--fqcn", default=None)
    fa.add_argument("--subject-contains", default=None)

    en = sub.add_parser("entity", parents=[common], help="entity_table_map lookup")
    en.add_argument("--signals", required=True)
    en.add_argument("--class", dest="class_name", default=None)
    en.add_argument("--table", default=None)
    en.add_argument("--fqcn", default=None)

    dep = sub.add_parser(
        "dependents",
        parents=[common],
        help="import dependents / importers",
    )
    dep.add_argument("--signals", required=True)
    dep.add_argument("--file", dest="target_file", default=None)
    dep.add_argument("--type", dest="target_type", default=None)
    dep.add_argument("--edges", default=None, help="optional cross_group_edges.json")
    dep.add_argument("--group", dest="group_id", default=None)

    tr = sub.add_parser(
        "route-trace",
        parents=[common],
        help="api_surface × same-file security",
    )
    tr.add_argument("--signals", required=True)
    tr.add_argument("--path-contains", default=None)
    tr.add_argument("--file", dest="file_contains", default=None)

    cp = sub.add_parser(
        "context-packet",
        parents=[common],
        help="ranked Mako-class packet over a Stage-0 run dir",
    )
    cp.add_argument("--run-dir", required=True, help="directory with spring_signals.json")
    cp.add_argument("--request", required=True, help="natural-language or keyword request")
    cp.add_argument(
        "--budget-tokens",
        type=int,
        default=None,
        help="token budget (chars/4 proxy; default 4000, hard-clamped)",
    )
    cp.add_argument("--repo", dest="repo_path", default=None, help="optional target repo for freshness")
    cp.add_argument("--drift-report", default=None, help="optional drift_report.json")

    return p


def _resolve_cli_root(args: argparse.Namespace) -> Path:
    """Pick containment root for a CLI invocation."""
    if getattr(args, "unsafe_no_root", False):
        # Explicit CLI-only; still need a root for _resolve — use artifact parent later
        return Path.cwd()
    if getattr(args, "root", None):
        return Path(args.root)
    if os.environ.get("DOC_ENGINE_ROOT") or os.environ.get("DOC_ENGINE_RUN_DIR"):
        return require_server_root()
    # Default: parent of primary artifact / run-dir
    artifact = (
        getattr(args, "signals", None)
        or getattr(args, "facts", None)
        or getattr(args, "run_dir", None)
    )
    if artifact:
        return Path(artifact).resolve().parent
    return Path.cwd()


def _execute_kind(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    """Dispatch a parsed CLI kind to the matching query handler."""
    if args.kind == "evidence":
        return run_query(
            "evidence",
            signals_path=args.signals,
            root=root,
            limit=args.limit,
            bucket=args.bucket,
            rule_id=args.rule_id,
            file_contains=args.file_contains,
            match_contains=args.match_contains,
        )
    if args.kind == "routes":
        return run_query(
            "routes",
            signals_path=args.signals,
            root=root,
            limit=args.limit,
            path_contains=args.path_contains,
            rule_id=args.rule_id,
            file_contains=args.file_contains,
        )
    if args.kind == "facts":
        return run_query(
            "facts",
            facts_path=args.facts,
            root=root,
            limit=args.limit,
            predicate=args.predicate,
            file_contains=args.file_contains,
            fqcn=args.fqcn,
            subject_contains=args.subject_contains,
        )
    if args.kind == "entity":
        return run_query(
            "entity",
            signals_path=args.signals,
            root=root,
            limit=args.limit,
            class_name=args.class_name,
            table=args.table,
            fqcn=args.fqcn,
        )
    if args.kind == "dependents":
        return run_query(
            "dependents",
            signals_path=args.signals,
            edges_path=args.edges,
            root=root,
            limit=args.limit,
            target_file=args.target_file,
            target_type=args.target_type,
            group_id=args.group_id,
        )
    if args.kind == "route-trace":
        return run_query(
            "route-trace",
            signals_path=args.signals,
            root=root,
            limit=args.limit,
            path_contains=args.path_contains,
            file_contains=args.file_contains,
        )
    if args.kind == "context-packet":
        from doc_engine.query.packet import run_context_packet

        return run_context_packet(
            args.request,
            run_dir=args.run_dir,
            budget_tokens=args.budget_tokens,
            root=root,
            repo_path=args.repo_path,
            drift_report_path=args.drift_report,
        )
    raise QueryError(f"unknown kind {args.kind}")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    root = _resolve_cli_root(args)
    try:
        result = _execute_kind(args, root)
    except QueryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
