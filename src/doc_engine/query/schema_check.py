"""Optional JSON-Schema validation for query / context_packet envelopes (E4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from doc_engine.paths import repo_root
from doc_engine.query.load import QueryError

_SCHEMA_DIR = repo_root() / "scripts" / "schemas"

ENVELOPE_SCHEMAS = {
    "query_result": "query_result.schema.json",
    "context_packet": "context_packet.schema.json",
}


def schema_path(kind: str) -> Path:
    name = ENVELOPE_SCHEMAS.get(kind)
    if not name:
        raise QueryError(f"unknown envelope schema kind: {kind!r}")
    path = _SCHEMA_DIR / name
    if not path.is_file():
        raise QueryError(f"schema missing: {path}")
    return path


def load_schema(kind: str) -> dict[str, Any]:
    return json.loads(schema_path(kind).read_text(encoding="utf-8"))


def _require_keys(kind: str, data: Mapping[str, Any], required: list[Any]) -> None:
    missing = [k for k in required if k not in data]
    if missing:
        raise QueryError(f"{kind} envelope missing keys: {missing}")


def _check_kind_specific(kind: str, data: Mapping[str, Any]) -> None:
    if kind == "context_packet" and data.get("kind") != "context-packet":
        raise QueryError("context_packet kind must be 'context-packet'")
    if kind == "query_result" and "rows" in data and not isinstance(data["rows"], list):
        raise QueryError("query_result.rows must be a list")


def validate_envelope(kind: str, data: Mapping[str, Any]) -> None:
    """Lightweight required-key check (no jsonschema dependency required).

    Full Draft-2020-12 validation can be added when ``jsonschema`` is a pinned
    optional dep; CI hermetic bar uses this closed required-set check.
    """
    schema = load_schema(kind)
    _require_keys(kind, data, schema.get("required") or [])
    _check_kind_specific(kind, data)
