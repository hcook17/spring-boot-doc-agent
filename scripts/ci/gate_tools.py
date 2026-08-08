#!/usr/bin/env python3
"""Portable resolution of quality-gate CLIs (Python + jscpd).

Usage:
    from gate_tools import jscpd_command, python_module_command, require_venv_script

Prefer ``sys.executable -m …`` for Python tools and a local ``node_modules``
jscpd install (native binary or ``run-jscpd.js``) over ``npx`` / shell wrappers.
Never use ``shell=True``.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

# scripts/ci → repo root of *this* checkout (worktree-safe; do not use
# doc_engine.paths.repo_root(), which follows the editable-install source tree).
REPO_ROOT = Path(__file__).resolve().parents[2]
JSCPD_VERSION = "5.0.14"


def require_on_path(name: str) -> str:
    """Return an absolute executable path for *name*, or exit 2.

    Checks ``PATH`` first, then the directory next to ``sys.executable`` and
    its ``Scripts/`` sibling (venv layout on Windows vs POSIX). Also accepts
    ``.exe`` / ``.cmd`` suffixes on Windows so CreateProcess can launch the
    real PE or cmd shim without ``shell=True``.
    """
    resolved = shutil.which(name)
    if resolved:
        return resolved
    sibling_dir = Path(sys.executable).resolve().parent
    names = [name]
    if os.name == "nt":
        names.extend((f"{name}.exe", f"{name}.cmd", f"{name}.bat"))
    for base in (sibling_dir, sibling_dir / "Scripts"):
        for candidate_name in names:
            candidate = base / candidate_name
            if candidate.is_file():
                return str(candidate)
    print(
        f"error: {name!r} is not on PATH (install requirements-dev.txt / Node)",
        file=sys.stderr,
    )
    raise SystemExit(2)


def python_module_command(module: str, *args: str) -> list[str]:
    """Build ``[sys.executable, '-m', module, …]`` — OS-native argv list."""
    return [sys.executable, "-m", module, *args]


def require_venv_script(name: str) -> str:
    """Resolve a pip console_script next to the active interpreter."""
    return require_on_path(name)


def _arch_token() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    return machine


def _jscpd_native_candidates() -> list[Path]:
    """Platform optional-dependency binaries shipped with jscpd@5."""
    arch = _arch_token()
    system = platform.system()
    root = REPO_ROOT / "node_modules"
    binary = "jscpd.exe" if system == "Windows" else "jscpd"
    packages: list[str] = []
    if system == "Windows" and arch == "x64":
        packages.append("jscpd-windows-x64-msvc")
    elif system == "Darwin" and arch == "arm64":
        packages.append("jscpd-darwin-arm64")
    elif system == "Darwin" and arch == "x64":
        packages.append("jscpd-darwin-x64")
    elif system == "Linux" and arch == "x64":
        packages.extend(("jscpd-linux-x64-gnu", "jscpd-linux-x64-musl"))
    elif system == "Linux" and arch == "arm64":
        packages.append("jscpd-linux-arm64-gnu")
    return [root / pkg / "bin" / binary for pkg in packages]


def jscpd_command(*args: str) -> list[str]:
    """Argv to run pinned local jscpd (no npx).

    Prefer the native binary from ``npm ci`` optionalDependencies; fall back to
    ``node node_modules/jscpd/run-jscpd.js`` (the package bin entry). Exit 2
    with an ``npm ci`` hint when neither is present.
    """
    for candidate in _jscpd_native_candidates():
        if candidate.is_file():
            return [str(candidate), *args]

    wrapper = REPO_ROOT / "node_modules" / "jscpd" / "run-jscpd.js"
    if wrapper.is_file():
        node = require_on_path("node")
        return [node, str(wrapper), *args]

    print(
        "error: jscpd is not installed locally.\n"
        f"  Run once from the repo root (Mac/Windows/Linux): npm ci\n"
        f"  Expected pin: jscpd@{JSCPD_VERSION} (see package.json).",
        file=sys.stderr,
    )
    raise SystemExit(2)
