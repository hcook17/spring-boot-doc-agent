"""Load Stage-0 JSON / JSONL artifacts with fail-closed path checks."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from doc_engine.core.walk import is_path_inside_root


class QueryError(ValueError):
    """Malformed or unreadable artifact."""


class QueryMissingError(QueryError):
    """Artifact path does not exist — never treat as empty success."""


class QueryPathError(QueryError):
    """Path escapes declared root or fails containment."""


def require_server_root() -> Path:
    """Return the MCP/server containment root from the process environment.

    Requires ``DOC_ENGINE_ROOT`` or ``DOC_ENGINE_RUN_DIR``. Callers must never
    accept a client-supplied root override for the MCP surface.
    """
    raw = os.environ.get("DOC_ENGINE_ROOT") or os.environ.get("DOC_ENGINE_RUN_DIR")
    if not raw or not str(raw).strip():
        raise QueryPathError(
            "DOC_ENGINE_ROOT or DOC_ENGINE_RUN_DIR must be set for path-contained queries"
        )
    try:
        return Path(str(raw)).resolve()
    except OSError as exc:
        raise QueryPathError(f"cannot resolve server root: {raw}") from exc


def _resolve(path: Path, *, root: Path | None) -> Path:
    if root is None:
        raise QueryPathError(
            "containment root is required; pass root= or set DOC_ENGINE_ROOT / DOC_ENGINE_RUN_DIR"
        )
    try:
        resolved = path.resolve()
    except OSError as exc:
        raise QueryPathError(f"cannot resolve path: {path}") from exc
    try:
        root_resolved = root.resolve()
    except OSError as exc:
        raise QueryPathError(f"cannot resolve root: {root}") from exc
    if not is_path_inside_root(str(resolved), str(root_resolved)):
        raise QueryPathError(
            f"artifact path escapes root: {path} (resolved {resolved})"
        )
    return resolved


def load_json(path: Path | str, *, root: Path | None = None) -> Any:
    p = _resolve(Path(path), root=root)
    if not p.is_file():
        raise QueryMissingError(f"missing artifact: {p}")
    try:
        text = p.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise QueryError(f"cannot read {p}: {exc}") from exc
    if "\x00" in text:
        raise QueryError(f"NUL byte in JSON artifact: {p}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise QueryError(f"invalid JSON in {p}: {exc}") from exc


def load_jsonl(path: Path | str, *, root: Path | None = None) -> list[dict[str, Any]]:
    p = _resolve(Path(path), root=root)
    if not p.is_file():
        raise QueryMissingError(f"missing artifact: {p}")
    try:
        text = p.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise QueryError(f"cannot read {p}: {exc}") from exc
    if "\x00" in text:
        raise QueryError(f"NUL byte in JSONL artifact: {p}")
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise QueryError(f"invalid JSONL at {p}:{lineno}: {exc}") from exc
        if not isinstance(obj, dict):
            raise QueryError(f"JSONL row must be object at {p}:{lineno}")
        rows.append(obj)
    return rows
