"""Shared scan context: one repository walk, many consumers.

Avoids N+1 file walks when filesystem scanning, drift tier-1 hashing, and
future incremental scanners all need the same file inventory and signatures.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from doc_engine.core.excludes import load_gitignore_spec
from doc_engine.core.walk import (
    JAVA_EXT,
    compute_file_signature,
    dfs_walk,
    is_path_inside_root,
    warn_skipped_escape,
)


@dataclass(frozen=True)
class FileEntry:
    """One file discovered during the shared repository walk."""

    full_path: str
    rel_path: str
    name: str
    ext: str


def _record_file_signature(ctx: ScanContext, rel: str, full: str) -> None:
    try:
        ctx.file_signatures[rel] = compute_file_signature(full)
    except OSError as exc:
        print(
            f"warning: could not read '{rel}' to compute its content signature: {exc}",
            file=sys.stderr,
        )


def _bucket_file_entry(ctx: ScanContext, entry: FileEntry) -> None:
    if entry.ext in JAVA_EXT:
        ctx.java_files.append(entry)
    else:
        ctx.non_java_files.append(entry)


def _ingest_walked_file(ctx: ScanContext, full: str, repo_path: str) -> None:
    rel = os.path.relpath(full, repo_path).replace("\\", "/")
    if not is_path_inside_root(full, repo_path):
        warn_skipped_escape(rel, full)
        return
    name = os.path.basename(full)
    _, ext = os.path.splitext(name)
    entry = FileEntry(full_path=full, rel_path=rel, name=name, ext=ext)
    _record_file_signature(ctx, rel, full)
    _bucket_file_entry(ctx, entry)


@dataclass
class ScanContext:
    """Result of a single deterministic pass over a repository."""

    repo_path: str
    file_signatures: Dict[str, str] = field(default_factory=dict)
    java_files: List[FileEntry] = field(default_factory=list)
    non_java_files: List[FileEntry] = field(default_factory=list)
    gitignore_spec: Optional[Any] = None

    @classmethod
    def build(cls, repo_path: str, respect_gitignore: bool = False) -> ScanContext:
        """Walk the repo once and collect signatures and file entries."""
        repo_path = os.path.abspath(repo_path)
        gitignore_spec = load_gitignore_spec(repo_path) if respect_gitignore else None
        ctx = cls(repo_path=repo_path, gitignore_spec=gitignore_spec)
        for full in dfs_walk(repo_path, gitignore_spec=gitignore_spec):
            _ingest_walked_file(ctx, full, repo_path)
        return ctx
