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


def _read_artifact_text(path: Path, *, kind: str) -> str:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise QueryError(f"cannot read {path}: {exc}") from exc
    if "\x00" in text:
        raise QueryError(f"NUL byte in {kind} artifact: {path}")
    return text


def load_json(path: Path | str, *, root: Path | None = None) -> Any:
    p = _resolve(Path(path), root=root)
    if not p.is_file():
        raise QueryMissingError(f"missing artifact: {p}")
    text = _read_artifact_text(p, kind="JSON")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise QueryError(f"invalid JSON in {p}: {exc}") from exc


def _parse_jsonl_object(path: Path, lineno: int, stripped: str) -> dict[str, Any]:
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise QueryError(f"invalid JSONL at {path}:{lineno}: {exc}") from exc
    if not isinstance(obj, dict):
        raise QueryError(f"JSONL row must be object at {path}:{lineno}")
    return obj


def _jsonl_rows_from_text(path: Path, text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        rows.append(_parse_jsonl_object(path, lineno, stripped))
    return rows


def load_jsonl(path: Path | str, *, root: Path | None = None) -> list[dict[str, Any]]:
    p = _resolve(Path(path), root=root)
    if not p.is_file():
        raise QueryMissingError(f"missing artifact: {p}")
    return _jsonl_rows_from_text(p, _read_artifact_text(p, kind="JSONL"))
