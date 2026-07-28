#!/usr/bin/env python3
"""Generic Stage 0 orchestrator.

This module knows nothing about Java, Spring, or the fourteen-file taxonomy. It
only knows the Scanner, Merger, and LineageResolver protocols and wires them
together to produce a final Signal dict.
"""

import hashlib
from typing import Any, Dict, List

from doc_engine.core.context import ScanContext
from doc_engine.core.protocols import LineageResolver, Merger, Scanner


def _combined_scanner_version(scanners: List[Scanner]) -> str:
    """Hash the active scanner names and their individual version hashes."""
    h = hashlib.sha256()
    for scanner in scanners:
        h.update(f"{scanner.name}:{scanner.version_hash()}".encode("utf-8"))
    return h.hexdigest()[:16]


def run_scan(
    repo_path: str,
    scanners: List[Scanner],
    merger: Merger,
    lineage_resolver: LineageResolver,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Run all scanners, merge their partial signals, and resolve lineage.

    Args:
        repo_path: absolute path to the target repository.
        scanners: list of instantiated Scanner backends to run.
        merger: a Merger implementation.
        lineage_resolver: a LineageResolver implementation.
        **kwargs: extra arguments passed to each scanner's scan() method.
            scan_context: optional pre-built ScanContext (one walk for all consumers).

    Returns:
        A complete Signal dict (for the Spring implementation, a spring_signals.json).
    """
    if kwargs.get("scan_context") is None:
        respect_gitignore = bool(kwargs.get("respect_gitignore", False))
        kwargs = {
            **kwargs,
            "scan_context": ScanContext.build(repo_path, respect_gitignore=respect_gitignore),
        }

    scanner_version = _combined_scanner_version(scanners)

    partials = []
    for scanner in scanners:
        partial = scanner.scan(repo_path, **kwargs)
        partials.append(partial)

    scanner_names = [s.name for s in scanners]
    merged = merger.merge(partials, repo_path, scanner_version, scanner_names=scanner_names)
    return lineage_resolver.resolve(merged, **kwargs)
