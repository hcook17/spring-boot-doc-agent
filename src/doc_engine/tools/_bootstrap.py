"""Single sanctioned sys.path bootstrap for legacy scripts/ imports."""

from __future__ import annotations

import sys

from doc_engine.paths import repo_root, scripts_dir


def ensure_scripts_importable() -> None:
    """Insert scripts/ and src/ so legacy script modules can be imported."""
    scripts = scripts_dir()
    src = repo_root() / "src"
    for entry in (str(scripts), str(src)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
