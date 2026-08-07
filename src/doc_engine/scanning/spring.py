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


def detect_build_command(repo_path: str) -> Optional[str]:
    """Return a reasonable default build command for a Java project.

    Prefers native wrappers (``gradlew.bat`` / ``gradlew`` / ``mvnw``) over a
    Git-Bash prefix so validation stays exact-basename. A Bash-wrapped
    ``gradlew`` is only emitted when the Unix wrapper exists and native
    execution is unavailable on Windows.
    """
    repo_path = os.path.abspath(repo_path)
    if os.path.exists(os.path.join(repo_path, "gradlew.bat")):
        gradlew = os.path.join(repo_path, "gradlew.bat")
        return f'"{gradlew}" --no-daemon clean compileJava compileTestJava'
    if os.path.exists(os.path.join(repo_path, "gradlew")):
        gradlew = os.path.join(repo_path, "gradlew")
        return f'"{gradlew}" --no-daemon clean compileJava compileTestJava'
    if os.path.exists(os.path.join(repo_path, "build.gradle")) or \
       os.path.exists(os.path.join(repo_path, "build.gradle.kts")):
        gradle = shutil.which("gradle") or shutil.which("gradle.bat")
        if gradle:
            return f'"{gradle}" --no-daemon clean compileJava compileTestJava'
    if os.path.exists(os.path.join(repo_path, "mvnw.cmd")):
        mvnw = os.path.join(repo_path, "mvnw.cmd")
        return f'"{mvnw}" --no-daemon clean compile test-compile'
    if os.path.exists(os.path.join(repo_path, "mvnw")):
        mvnw = os.path.join(repo_path, "mvnw")
        return f'"{mvnw}" --no-daemon clean compile test-compile'
    if os.path.exists(os.path.join(repo_path, "pom.xml")):
        mvn = shutil.which("mvn") or shutil.which("mvn.cmd")
        if mvn:
            return f'"{mvn}" --no-daemon clean compile test-compile'
    return None


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

    if "codeql" in scanner_names and build_command is None:
        build_command = detect_build_command(repo_path)
    if "codeql" in scanner_names and build_command is None:
        raise CodeQLScannerError(
            "Could not detect a Java build command for this repository. "
            "Pass --build-command, e.g. 'gradlew clean compileJava'."
        )
    if "codeql" in scanner_names and build_command is not None:
        try:
            build_command = validate_build_command(build_command)
        except BuildCommandError as exc:
            raise CodeQLScannerError(str(exc)) from exc

    try:
        scan_kwargs: Dict[str, Any] = {
            "sql_dialect": sql_dialect,
            "respect_gitignore": respect_gitignore,
            "build_command": build_command,
            "db_path": db_path,
        }
        if scan_context is not None:
            scan_kwargs["scan_context"] = scan_context
        return run_scan(
            repo_path,
            scanner_instances,
            SpringSignalMerger(),
            SpringLineageResolver(),
            **scan_kwargs,
        )
    except CodeQLError as exc:
        if isinstance(exc, CodeQLNotFoundError):
            raise CodeQLNotFoundError(str(exc)) from exc
        raise CodeQLScannerError(str(exc)) from exc
    except CoveringProofError:
        raise
    except PermissionError as exc:
        raise CodeQLScannerError(str(exc)) from exc
