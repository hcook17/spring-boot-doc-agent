#!/usr/bin/env python3
"""Explicit registry of Stage 0 scanner backends."""

from doc_engine.core.protocols import Scanner
from doc_engine.scanning._scanner_astgrep import AstGrepBackend
from doc_engine.scanning._scanner_codeql import CodeQLBackend
from doc_engine.scanning._scanner_filesystem import FilesystemBackend

SCANNERS = {
    "filesystem": FilesystemBackend,
    "codeql": CodeQLBackend,
    "ast-grep": AstGrepBackend,
}


def get_scanner(name: str) -> Scanner:
    """Return an instantiated scanner backend by name."""
    if name not in SCANNERS:
        raise ValueError(
            f"unknown scanner '{name}'. Known scanners: {', '.join(sorted(SCANNERS))}"
        )
    return SCANNERS[name]()


def resolve_scanner_names(names: list) -> list:
    """Validate and return a list of scanner names, defaulting to filesystem+codeql."""
    if not names:
        return ["filesystem", "codeql"]
    seen = set()
    result = []
    for name in names:
        if name not in SCANNERS:
            raise ValueError(f"unknown scanner '{name}'")
        if name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result
