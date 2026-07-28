#!/usr/bin/env python3
"""Filesystem scanner backend for spring_signal_scan.py.

This scanner does not parse Java source. It walks the repository, computes
file signatures, classifies non-Java files by name, and extracts build/config
signals and redaction zones. It implements the generic Scanner protocol.
"""

import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from doc_engine.core.context import ScanContext
from doc_engine.core.walk import compute_file_signature, dfs_walk
from doc_engine.scanning._scanner_base import ScannerBackend
from doc_engine.scanning.support._build_signal_extract import extract_build_signals
from doc_engine.scanning.support._config_keys import extract_config_keys
from doc_engine.scanning.support._secret_heuristics import scan_text_for_secrets
BUILD_FILE_NAMES = {"pom.xml", "build.xml"}
BUILD_EXTS = {".gradle", ".groovy"}
CONFIG_NAME_PATTERNS = [
    re.compile(r"^application(-[\w.-]+)?\.(ya?ml|properties)$"),
    re.compile(r"^bootstrap(-[\w.-]+)?\.(ya?ml|properties)$"),
    re.compile(r"^gradle\.properties$"),
    re.compile(r"^gradle-wrapper\.properties$"),
    re.compile(r"^build\.properties$"),
]
LOGGING_CONFIG_NAMES = {"logback.xml", "logback-spring.xml", "log4j2.xml", "log4j2-spring.xml"}
MIGRATION_DIR_HINTS = ("db/migration", "db/changelog", "migrations")


def _is_build_file(name: str, ext: str) -> bool:
    return (
        name in BUILD_FILE_NAMES
        or ext in BUILD_EXTS
        or name.endswith(".gradle.kts")
    )


def _process_config_deployment_file(
    full: str, rel: str, redaction_zones: Dict[str, List[Dict[str, Any]]], config_key_sets: Dict[str, List[str]]
) -> None:
    """Run secret redaction and config-key extraction on a config/deployment file."""
    try:
        with open(full, encoding="utf-8-sig", errors="ignore") as f:
            text = f.read()
    except OSError:
        return

    hits = scan_text_for_secrets(text)
    if hits:
        redaction_zones[rel] = hits

    keys = extract_config_keys(text, os.path.basename(rel))
    if keys:
        config_key_sets[rel] = keys


def _classify_non_java_file(
    full: str,
    rel: str,
    name: str,
    ext: str,
    buckets: Dict[str, List[Dict[str, Any]]],
    files_scanned: Dict[str, int],
    redaction_zones: Dict[str, List[Dict[str, Any]]],
    config_key_sets: Dict[str, List[str]],
) -> None:
    """Classify a non-Java file into the appropriate evidence bucket."""
    if any(p.match(name) for p in CONFIG_NAME_PATTERNS):
        files_scanned["config"] += 1
        buckets["configuration"].append({"file": rel, "match": "config file"})
        _process_config_deployment_file(full, rel, redaction_zones, config_key_sets)
        return

    if _is_build_file(name, ext) or name == "libs.versions.toml":
        files_scanned["deployment"] += 1
        if name == "libs.versions.toml":
            buckets["deployment"].append({"file": rel, "match": "version catalog"})
        else:
            buckets["deployment"].append({"file": rel, "match": "build script"})
        try:
            with open(full, encoding="utf-8-sig", errors="replace") as fh:
                build_text = fh.read()
        except OSError as e:
            build_text = ""
            print(f"warning: could not read build file '{rel}' for signal extraction: {e}", file=sys.stderr)
        for row in extract_build_signals(rel, build_text):
            buckets["deployment"].append(row)
        _process_config_deployment_file(full, rel, redaction_zones, config_key_sets)
        return

    if name in LOGGING_CONFIG_NAMES:
        files_scanned["other_relevant"] += 1
        buckets["observability"].append({"file": rel, "match": "logging config file"})
        return

    if name.startswith("Dockerfile") or re.match(r"docker-compose.*\.ya?ml$", name):
        files_scanned["deployment"] += 1
        buckets["deployment"].append({"file": rel, "match": "container/compose file"})
        _process_config_deployment_file(full, rel, redaction_zones, config_key_sets)
        return

    if ext in (".yml", ".yaml") and any(
        seg in rel.replace("\\", "/").split("/") for seg in ("k8s", "helm", "charts", "deploy", "deployment", ".github")
    ):
        files_scanned["deployment"] += 1
        buckets["deployment"].append({"file": rel, "match": "deployment manifest"})
        _process_config_deployment_file(full, rel, redaction_zones, config_key_sets)
        return

    rel_posix = rel.replace("\\", "/")
    if any(hint in rel_posix for hint in MIGRATION_DIR_HINTS):
        files_scanned["other_relevant"] += 1
        buckets["persistence"].append({"file": rel, "match": "migration script"})
        return


class FilesystemBackend(ScannerBackend):
    """Scanner backend for filename-based and heuristic signal extraction."""

    @property
    def name(self) -> str:
        return "filesystem"

    def version_hash(self) -> str:
        import hashlib
        h = hashlib.sha256()
        paths = [
            Path(__file__).resolve(),
            Path(__file__).resolve().parent / "support" / "_build_signal_extract.py",
            Path(__file__).resolve().parent / "support" / "_config_keys.py",
            Path(__file__).resolve().parent / "support" / "_secret_heuristics.py",
        ]
        for p in sorted(paths):
            try:
                with open(p, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 20), b""):
                        h.update(chunk)
            except OSError:
                pass
        return h.hexdigest()[:16]

    def scan(
        self,
        repo_path: str,
        respect_gitignore: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        repo_path = os.path.abspath(repo_path)
        scan_context: Optional[ScanContext] = kwargs.get("scan_context")
        if scan_context is None:
            scan_context = ScanContext.build(repo_path, respect_gitignore=respect_gitignore)

        buckets = {
            "api_surface": [], "outbound_clients": [], "messaging": [],
            "persistence": [], "raw_queries": [], "security": [],
            "configuration": [], "error_handling": [], "observability": [],
            "deployment": [], "testing": [], "references": [],
        }
        files_scanned = {"java": 0, "config": 0, "deployment": 0, "other_relevant": 0}
        file_signatures = dict(scan_context.file_signatures)
        redaction_zones = {}
        config_key_sets = {}

        files_scanned["java"] = len(scan_context.java_files)
        for entry in scan_context.non_java_files:
            _classify_non_java_file(
                entry.full_path,
                entry.rel_path,
                entry.name,
                entry.ext,
                buckets,
                files_scanned,
                redaction_zones,
                config_key_sets,
            )

        for bucket in buckets.values():
            bucket.sort(key=lambda e: (e["file"], e.get("line", 0)))

        return {
            "evidence": buckets,
            "files_scanned": files_scanned,
            "file_signatures": file_signatures,
            "redaction_zones": redaction_zones,
            "config_key_sets": config_key_sets,
        }
