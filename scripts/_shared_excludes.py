"""Shared default excluded-directory set for the deterministic scan/partition
stage. Single source of truth for both spring_signal_scan.py and
partition_repo.py — previously each maintained its own independent copy,
which had already drifted (spring_signal_scan.py's EXCLUDED_DIRS was
missing vendor/venv/.venv/env/coverage, which meant run_ast_grep()'s
--globs exclusion list — the only thing standing between ast-grep and
those directories, since run_ast_grep's own traversal is Rust-internal and
never goes through this module's dot-guard — let a top-level vendor/ or
venv/ directory's Java get scanned and cited as if it were the repo's own
code).

This is the union of the two sets as they stood on 2026-07-23 (diffed
programmatically, not merged by eye), plus no new entries.
"""

DEFAULT_EXCLUDED_DIRS = frozenset({
    ".git", ".gradle", ".hg", ".idea", ".mvn", ".mypy_cache", ".next",
    ".nuxt", ".pytest_cache", ".svn", ".venv", ".vscode", "__pycache__",
    "bin", "build", "coverage", "dist", "env", "node_modules", "obj",
    "out", "target", "vendor", "venv",
})


def load_gitignore_spec(repo_path):
    """Return a pathspec.PathSpec built from repo_path/.gitignore, or None
    if there is no .gitignore or the pathspec library isn't installed.
    Soft dependency, same pattern as spring_signal_scan.py's existing
    sqllineage handling — a missing install degrades this one feature,
    it doesn't fail the whole scan."""
    import os
    gitignore_path = os.path.join(repo_path, ".gitignore")
    if not os.path.isfile(gitignore_path):
        return None
    try:
        import pathspec
    except ImportError:
        return None
    with open(gitignore_path) as f:
        return pathspec.PathSpec.from_lines("gitwildmatch", f)
