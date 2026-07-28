"""Shared exclude rules and gitignore loading for repository walks."""

DEFAULT_EXCLUDED_DIRS = frozenset({
    ".git", ".gradle", ".hg", ".idea", ".mvn", ".mypy_cache", ".next",
    ".nuxt", ".pytest_cache", ".svn", ".venv", ".vscode", "__pycache__",
    "bin", "build", "coverage", "dist", "env", "node_modules", "obj",
    "out", "target", "vendor", "venv",
})


def load_gitignore_spec(repo_path: str):
    """Return a pathspec.PathSpec from repo_path/.gitignore, or None."""
    import os

    gitignore_path = os.path.join(repo_path, ".gitignore")
    if not os.path.isfile(gitignore_path):
        return None
    try:
        import pathspec
    except ImportError:
        return None
    with open(gitignore_path, encoding="utf-8") as f:
        return pathspec.PathSpec.from_lines("gitwildmatch", f)
