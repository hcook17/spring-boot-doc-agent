"""Stage 0 scanning package."""

from typing import Any, Dict, List, Optional

from doc_engine.scanning._merge_signals import SpringSignalMerger
from doc_engine.scanning._orchestrator import run_scan
from doc_engine.scanning._resolve_lineage import SpringLineageResolver
from doc_engine.scanning._scanner_registry import get_scanner, resolve_scanner_names
from doc_engine.scanning.spring import scan

__all__ = [
    "scan",
    "scan_repository",
    "run_scan",
    "get_scanner",
    "resolve_scanner_names",
    "SpringSignalMerger",
    "SpringLineageResolver",
]


def scan_repository(
    repo_path: str,
    sql_dialect: str = "ansi",
    respect_gitignore: bool = False,
    build_command: Optional[str] = None,
    db_path: Optional[str] = None,
    scanners: Optional[List[str]] = None,
    scan_context: Optional[Any] = None,
    allow_codeql_build: bool = False,
) -> Dict[str, Any]:
    """Run Stage 0 signal extraction for a Spring Boot repository."""
    return scan(
        repo_path,
        sql_dialect=sql_dialect,
        respect_gitignore=respect_gitignore,
        build_command=build_command,
        db_path=db_path,
        scanners=scanners,
        scan_context=scan_context,
        allow_codeql_build=allow_codeql_build,
    )
