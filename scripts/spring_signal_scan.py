#!/usr/bin/env python3
"""spring_signal_scan.py — CLI wrapper for Spring Boot Stage 0 scanning.

Implementation lives in doc_engine.scanning. This module preserves the
historical scripts/ entry point and backward-compatible public API.

Usage:
    python3 scripts/spring_signal_scan.py <repo_path> --out spring_signals.json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List

import _src_bootstrap  # noqa: F401

from doc_engine.core.walk import compute_file_signature, dfs_walk
from doc_engine.scanning._paths import ast_grep_rules_path
from doc_engine.scanning._resolve_lineage import extract_sql_lineage, resolve_jpql_to_lineage
from doc_engine.scanning._scanner_filesystem import CONFIG_NAME_PATTERNS
from doc_engine.scanning.spring import (
    AstGrepError,
    AstGrepNotFoundError,
    CodeQLNotFoundError,
    CodeQLScannerError,
    detect_build_command,
    scan,
)
from doc_engine.scanning.spring import (
    scanner_version as _scanner_version,
)
from doc_engine.scanning.support._codeql_runner import CodeQLError

# Re-exports consumed by tests and sibling scripts that historically imported
# these symbols from this module rather than from doc_engine.
__all__ = [
    "AstGrepError",
    "AstGrepNotFoundError",
    "CONFIG_NAME_PATTERNS",
    "CodeQLError",
    "CodeQLNotFoundError",
    "CodeQLScannerError",
    "RULE_FILE",
    "SCRIPT_DIR",
    "_scanner_version",
    "compute_file_signature",
    "detect_build_command",
    "dfs_walk",
    "extract_sql_lineage",
    "main",
    "resolve_jpql_to_lineage",
    "run_ast_grep",
    "scan",
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RULE_FILE = ast_grep_rules_path()


def run_ast_grep(binary: str, repo_path: str) -> List[Dict[str, Any]]:
    """Backward-compatible ast-grep runner used by drift-check and preflight."""
    import json as _json

    if not shutil.which(binary):
        raise AstGrepNotFoundError(f"ast-grep binary is not on PATH: {binary}")

    cmd = [
        binary, "scan", "--json", "--rules", str(RULE_FILE),
        "--no-ignore", "dot", "--no-ignore", "vcs", "--no-ignore", "parent",
        "--no-ignore", "global", "--no-ignore", "exclude",
        repo_path,
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise AstGrepError(
            f"ast-grep exited with status {proc.returncode}: {proc.stderr.strip()}"
        )
    try:
        return _json.loads(proc.stdout) if proc.stdout.strip() else []
    except Exception as exc:  # noqa: BLE001
        raise AstGrepError(f"ast-grep output is not valid JSON: {exc}") from exc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo_path")
    ap.add_argument("--out", default="spring_signals.json")
    ap.add_argument("--sql-dialect", default="ansi")
    ap.add_argument("--respect-gitignore", action="store_true", default=False)
    ap.add_argument("--build-command", default=None)
    ap.add_argument("--db-path", default=None)
    ap.add_argument(
        "--scanners", default=None,
        help="Comma-separated scanner names. Default: filesystem,ast-grep.",
    )
    args = ap.parse_args()

    if not os.path.isdir(args.repo_path):
        print(f"error: not a directory: {args.repo_path}", file=sys.stderr)
        return 1

    scanners = args.scanners.split(",") if args.scanners else None

    try:
        result = scan(
            args.repo_path,
            sql_dialect=args.sql_dialect,
            respect_gitignore=args.respect_gitignore,
            build_command=args.build_command,
            db_path=args.db_path,
            scanners=scanners,
        )
    except (CodeQLScannerError, CodeQLNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    counts = {k: len(v) for k, v in result["evidence"].items()}
    redaction_hit_count = sum(len(hits) for hits in result["redaction_zones"].values())
    print(
        f"Wrote {args.out}. Files scanned: {result['files_scanned']}. "
        f"Entities found: {len(result['entity_table_map'])}. "
        f"Evidence counts: {counts}. "
        f"Redaction zones flagged: {redaction_hit_count} line(s) across "
        f"{len(result['redaction_zones'])} file(s). "
        f"Config key sets recorded for {len(result['config_key_sets'])} file(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
