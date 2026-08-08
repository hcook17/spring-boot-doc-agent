"""Single-pass repository walk and file signature helpers.

Untrusted target trees may contain file symlinks that resolve outside the
repo root. ``is_path_inside_root`` is the containment gate: callers must skip
escaping paths before hashing or reading content (directory symlinks are
already ignored by ``os.walk``'s default ``followlinks=False``).
"""

import hashlib
import os
import sys
from pathlib import Path
from typing import Any, Iterator, Optional

from doc_engine.core.excludes import DEFAULT_EXCLUDED_DIRS

JAVA_EXT = {".java"}


def is_path_inside_root(path: str, root: str) -> bool:
    """Return True when resolved ``path`` is under resolved ``root``."""
    try:
        resolved = Path(path).resolve()
        root_resolved = Path(root).resolve()
        resolved.relative_to(root_resolved)
        return True
    except (OSError, ValueError):
        return False


def _prune_excluded_dirnames(dirnames: list[str]) -> None:
    """Drop build/cache and hidden directories from an os.walk dirnames list."""
    dirnames[:] = sorted(
        name for name in dirnames
        if name not in DEFAULT_EXCLUDED_DIRS and not name.startswith(".")
    )


def _prune_gitignored_dirnames(
    dirpath: str,
    dirnames: list[str],
    root: str,
    gitignore_spec: Any,
) -> None:
    """Drop directories matched by *gitignore_spec* from the walk."""
    dirnames[:] = [
        name for name in dirnames
        if not gitignore_spec.match_file(
            os.path.relpath(os.path.join(dirpath, name), root).replace("\\", "/")
            + "/"
        )
    ]


def _rel_posix(path: str, root: str) -> str:
    """Return a forward-slash relative path for gitignore matching."""
    return os.path.relpath(path, root).replace("\\", "/")


def _should_yield_file(full: str, root: str, gitignore_spec: Optional[Any]) -> bool:
    """True when *full* is not gitignored (or no gitignore spec is active)."""
    if gitignore_spec is None:
        return True
    return not gitignore_spec.match_file(_rel_posix(full, root))


def _iter_dir_files(
    dirpath: str,
    filenames: list[str],
    root: str,
    gitignore_spec: Optional[Any],
) -> Iterator[str]:
    """Yield absolute paths for files in one walk directory that are not ignored."""
    for name in sorted(filenames):
        full = os.path.join(dirpath, name)
        if _should_yield_file(full, root, gitignore_spec):
            yield full


def dfs_walk(root: str, gitignore_spec: Optional[Any] = None) -> Iterator[str]:
    """Yield absolute file paths under root, excluding standard build dirs."""
    for dirpath, dirnames, filenames in os.walk(root):
        _prune_excluded_dirnames(dirnames)
        if gitignore_spec is not None:
            _prune_gitignored_dirnames(dirpath, dirnames, root, gitignore_spec)
        yield from _iter_dir_files(dirpath, filenames, root, gitignore_spec)


def compute_file_signature(path: str) -> str:
    """Return sha256 hex digest of a file's raw bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def warn_skipped_escape(rel: str, full: str) -> None:
    print(
        f"warning: skipping '{rel}' — resolved path escapes repository root "
        f"({full})",
        file=sys.stderr,
    )
