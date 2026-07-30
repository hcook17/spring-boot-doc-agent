#!/usr/bin/env python3
"""Suite layout contract: one SoT in pyproject.toml, many consumers.

Gates and hooks must not sniff ci.yml for ``pytest tests/`` or assume
``scripts/test_*.py`` wrappers. Pytest already declares the roots:

    [tool.pytest.ini_options]
    testpaths = ["tests"]

This module is the only reader of that fact for meta tooling.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover — CI is 3.11; local 3.10 needs tomli if present
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

DEFAULT_SUITE_ROOTS = ("tests",)


def suite_roots(root: Path) -> List[str]:
    """Return pytest testpaths relative to *root* (never empty)."""
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file() or tomllib is None:
        return list(DEFAULT_SUITE_ROOTS)
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    paths = (
        data.get("tool", {})
        .get("pytest", {})
        .get("ini_options", {})
        .get("testpaths")
    )
    if not paths:
        return list(DEFAULT_SUITE_ROOTS)
    if isinstance(paths, str):
        return [paths]
    return [str(p) for p in paths]


def uses_pytest_discovery(root: Path) -> bool:
    """True only when pyproject.toml explicitly sets testpaths."""
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file() or tomllib is None:
        return False
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    paths = (
        data.get("tool", {})
        .get("pytest", {})
        .get("ini_options", {})
        .get("testpaths")
    )
    return paths is not None


def suite_paths(root: Path) -> List[Path]:
    """All ``test_*.py`` files under declared suite roots (recursive).

    Suites live in taxonomy subdirs (``tests/ci/``, ``tests/doc_engine/``, …);
    non-recursive ``glob`` would silently under-count after that layout.
    """
    found: List[Path] = []
    for rel in suite_roots(root):
        directory = root / rel
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("test_*.py")):
            if "__pycache__" in path.parts:
                continue
            found.append(path)
    return found


def suite_file_for_module(root: Path, module_filename: str) -> Path | None:
    """Path to ``test_<module>`` under a declared root, if it exists.

    Leading-underscore modules historically drop the underscore in the suite
    name (``_ast_signature.py`` → ``test_ast_signature.py``). Search is
    recursive so a suite in ``tests/ratchets/`` still pairs with
    ``scripts/ratchets/set_delta.py``.
    """
    candidates = [f"test_{module_filename}"]
    if module_filename.startswith("_"):
        candidates.append(f"test_{module_filename.lstrip('_')}")
    for rel in suite_roots(root):
        directory = root / rel
        if not directory.is_dir():
            continue
        for name in candidates:
            direct = directory / name
            if direct.is_file():
                return direct
            hits = sorted(
                p for p in directory.rglob(name)
                if "__pycache__" not in p.parts
            )
            if hits:
                return hits[0]
    return None
