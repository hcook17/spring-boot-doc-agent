"""Single-pass repository walk and file signature helpers."""

import hashlib
import os
from typing import Any, Iterator, Optional

from doc_engine.core.excludes import DEFAULT_EXCLUDED_DIRS

JAVA_EXT = {".java"}


def dfs_walk(root: str, gitignore_spec: Optional[Any] = None) -> Iterator[str]:
    """Yield absolute file paths under root, excluding standard build dirs."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in DEFAULT_EXCLUDED_DIRS and not d.startswith(".")
        )
        if gitignore_spec is not None:
            dirnames[:] = [
                d for d in dirnames
                if not gitignore_spec.match_file(
                    os.path.relpath(os.path.join(dirpath, d), root).replace("\\", "/") + "/"
                )
            ]
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if gitignore_spec is not None and gitignore_spec.match_file(
                os.path.relpath(full, root).replace("\\", "/")
            ):
                continue
            yield full


def compute_file_signature(path: str) -> str:
    """Return sha256 hex digest of a file's raw bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
