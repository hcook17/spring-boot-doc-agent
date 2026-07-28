"""Portable path resolution for the doc-engine kernel.

Kernel code uses these helpers instead of CLAUDE_PLUGIN_ROOT. Adapters may
still use CLAUDE_PLUGIN_ROOT for agent prompt paths only.
"""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Repository root in editable installs (src/doc_engine/paths.py → parents[2])."""
    return Path(__file__).resolve().parents[2]


def scripts_dir() -> Path:
    return repo_root() / "scripts"


def codeql_dir() -> Path:
    return repo_root() / "codeql"


def schemas_dir() -> Path:
    return scripts_dir() / "schemas"


def codeql_pack_dir() -> Path:
    return codeql_dir() / "spring-signals"


def ast_grep_rules_path() -> Path:
    packaged = (
        Path(__file__).resolve().parent
        / "scanning"
        / "resources"
        / "spring_ast_grep_rules.yml"
    )
    if packaged.is_file():
        return packaged
    return repo_root() / "scripts" / "spring_ast_grep_rules.yml"
