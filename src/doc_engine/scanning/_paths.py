"""Repository path helpers for the scanning package — re-export kernel paths."""

from doc_engine.paths import (
    ast_grep_rules_path,
    codeql_dir,
    codeql_pack_dir,
    repo_root,
    scripts_dir,
)

__all__ = [
    "repo_root",
    "scripts_dir",
    "ast_grep_rules_path",
    "codeql_dir",
    "codeql_pack_dir",
]
