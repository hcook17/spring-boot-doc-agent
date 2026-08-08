"""Spring Boot Stage 0 scan entry point."""

import hashlib
import os
import shutil
from typing import Any, Dict, List, Optional

from doc_engine.core.context import ScanContext
from doc_engine.core.protocols import Scanner
from doc_engine.scanning._merge_signals import SpringSignalMerger
from doc_engine.scanning._orchestrator import CoveringProofError, run_scan
from doc_engine.scanning._resolve_lineage import (
    SpringLineageResolver,
)
from doc_engine.scanning._scanner_registry import get_scanner, resolve_scanner_names
from doc_engine.scanning.build_command import BuildCommandError, validate_build_command
from doc_engine.scanning.support._codeql_runner import CodeQLError, CodeQLNotFoundError


class CodeQLScannerError(RuntimeError):
    """Any CodeQL-based scanner failure that should not kill the test process."""


class AstGrepError(RuntimeError):
    """Raised when the ast-grep subprocess fails or returns unparseable output."""


class AstGrepNotFoundError(AstGrepError):
    """Raised when the ast-grep binary cannot be found."""


def _wrapper_command(repo_path: str, name: str, goals: str) -> Optional[str]:
    path = os.path.join(repo_path, name)
    if not os.path.exists(path):
        return None
    return f'"{path}" {goals}'


def _tool_on_path(*names: str) -> Optional[str]:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _first_wrapper_command(
    repo_path: str, wrappers: tuple[str, ...], goals: str,
) -> Optional[str]:
    for wrapper in wrappers:
        command = _wrapper_command(repo_path, wrapper, goals)
        if command is not None:
            return command
    return None


def _gradle_tool_command(repo_path: str, goals: str) -> Optional[str]:
    if not (
        os.path.exists(os.path.join(repo_path, "build.gradle"))
        or os.path.exists(os.path.join(repo_path, "build.gradle.kts"))
    ):
        return None
    gradle = _tool_on_path("gradle", "gradle.bat")
    if not gradle:
        return None
    return f'"{gradle}" {goals}'


def _maven_tool_command(repo_path: str, goals: str) -> Optional[str]:
    if not os.path.exists(os.path.join(repo_path, "pom.xml")):
        return None
    mvn = _tool_on_path("mvn", "mvn.cmd")
    if not mvn:
        return None
    return f'"{mvn}" {goals}'


def detect_build_command(repo_path: str) -> Optional[str]:
    """Return a reasonable default build command for a Java project.

    Prefers native wrappers (``gradlew.bat`` / ``gradlew`` / ``mvnw``) over a
    Git-Bash prefix so validation stays exact-basename. A Bash-wrapped
    ``gradlew`` is only emitted when the Unix wrapper exists and native
    execution is unavailable on Windows.
    """
    repo_path = os.path.abspath(repo_path)
    gradle_goals = "--no-daemon clean compileJava compileTestJava"
    maven_goals = "--no-daemon clean compile test-compile"
    return (
        _first_wrapper_command(repo_path, ("gradlew.bat", "gradlew"), gradle_goals)
        or _gradle_tool_command(repo_path, gradle_goals)
        or _first_wrapper_command(repo_path, ("mvnw.cmd", "mvnw"), maven_goals)
        or _maven_tool_command(repo_path, maven_goals)
    )


def _combined_hash(scanners: List[Scanner]) -> str:
    hh = hashlib.sha256()
    for scanner in scanners:
        hh.update(f"{scanner.name}:{scanner.version_hash()}".encode())
    return hh.hexdigest()[:16]


def scanner_version(scanners: Optional[List[str]] = None) -> str:
    """Return the combined version hash of the given scanners (default: all)."""
    scanner_names = resolve_scanner_names(scanners)
    scanner_instances = [get_scanner(name) for name in scanner_names]
    return _combined_hash(scanner_instances)


def scan(
    repo_path: str,
    sql_dialect: str = "ansi",
    respect_gitignore: bool = False,
    build_command: Optional[str] = None,
    db_path: Optional[str] = None,
    scanners: Optional[List[str]] = None,
    scan_context: Optional[ScanContext] = None,
    allow_codeql_build: bool = False,
) -> Dict[str, Any]:
    """Scan a Spring Boot repository and return a canonical spring_signals.json dict.

    CodeQL build mode is refused unless ``allow_codeql_build`` is True — the
    build runs inside the target tree and cannot be made safe by basename
    allowlisting alone.
    """
    from doc_engine.config.repo_trust import (
        codeql_build_policy_from_flag,
        require_codeql_build_allowed,
    )

    repo_path = os.path.abspath(repo_path)
    scanner_names = resolve_scanner_names(scanners)
    require_codeql_build_allowed(
        scanner_names,
        codeql_build_policy_from_flag(allow_codeql_build),
    )
    scanner_instances: List[Scanner] = [get_scanner(name) for name in scanner_names]
    build_command = _prepare_codeql_build_command(scanner_names, repo_path, build_command)
    return _run_spring_scan(
        repo_path,
        scanner_instances,
        sql_dialect=sql_dialect,
        respect_gitignore=respect_gitignore,
        build_command=build_command,
        db_path=db_path,
        scan_context=scan_context,
    )


def _prepare_codeql_build_command(
    scanner_names: List[str],
    repo_path: str,
    build_command: Optional[str],
) -> Optional[str]:
    if "codeql" not in scanner_names:
        return build_command
    if build_command is None:
        build_command = detect_build_command(repo_path)
    if build_command is None:
        raise CodeQLScannerError(
            "Could not detect a Java build command for this repository. "
            "Pass --build-command, e.g. 'gradlew clean compileJava'."
        )
    try:
        return validate_build_command(build_command)
    except BuildCommandError as exc:
        raise CodeQLScannerError(str(exc)) from exc


def _spring_scan_kwargs(
    *,
    sql_dialect: str,
    respect_gitignore: bool,
    build_command: Optional[str],
    db_path: Optional[str],
    scan_context: Optional[ScanContext],
) -> Dict[str, Any]:
    scan_kwargs: Dict[str, Any] = {
        "sql_dialect": sql_dialect,
        "respect_gitignore": respect_gitignore,
        "build_command": build_command,
        "db_path": db_path,
    }
    if scan_context is not None:
        scan_kwargs["scan_context"] = scan_context
    return scan_kwargs


def _reraise_scan_error(exc: BaseException) -> None:
    if isinstance(exc, CoveringProofError):
        raise
    if isinstance(exc, CodeQLNotFoundError):
        raise CodeQLNotFoundError(str(exc)) from exc
    if isinstance(exc, (CodeQLError, PermissionError)):
        raise CodeQLScannerError(str(exc)) from exc
    raise


def _run_spring_scan(
    repo_path: str,
    scanner_instances: List[Scanner],
    *,
    sql_dialect: str,
    respect_gitignore: bool,
    build_command: Optional[str],
    db_path: Optional[str],
    scan_context: Optional[ScanContext],
) -> Dict[str, Any]:
    try:
        return run_scan(
            repo_path,
            scanner_instances,
            SpringSignalMerger(),
            SpringLineageResolver(),
            **_spring_scan_kwargs(
                sql_dialect=sql_dialect,
                respect_gitignore=respect_gitignore,
                build_command=build_command,
                db_path=db_path,
                scan_context=scan_context,
            ),
        )
    except (CodeQLError, CoveringProofError, PermissionError) as exc:
        _reraise_scan_error(exc)
        raise  # pragma: no cover — _reraise_scan_error always raises
