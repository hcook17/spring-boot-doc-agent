#!/usr/bin/env python3
"""Spring Boot SQL/JPQL lineage resolver implementing the LineageResolver protocol.

Resolves native SQL and bounded JPQL queries to source/target table lineage
using sqllineage. This is Spring-specific because it depends on the
entity_table_map produced by the Java scanners.
"""

import re
from typing import Any, Dict

from doc_engine.core.protocols import LineageResolver

try:
    from sqllineage.runner import LineageRunner
    _SQLLINEAGE_AVAILABLE = True
except ImportError:
    _SQLLINEAGE_AVAILABLE = False

NAMED_PARAM_RE = re.compile(r"(?<![\w'\"]):(\w+)")
POSITIONAL_PARAM_RE = re.compile(r"\?\d*")
SQLLINEAGE_DEFAULT_SCHEMA_PREFIX = "<default>."
JPQL_FROM_RE = re.compile(r"\bFROM\s+(\w+)\s+(?:AS\s+)?(\w+)\b", re.IGNORECASE)
JPQL_JOIN_RE = re.compile(r"\bJOIN\b", re.IGNORECASE)
JPQL_FUNCTION_RE = re.compile(r"\b(SIZE|KEY|VALUE|INDEX|TYPE)\s*\(", re.IGNORECASE)


def _normalize_bind_params(sql: str) -> str:
    """Substitute a harmless numeric literal for every named/positional bind
    parameter so sqllineage's parser can lex the query at all."""
    sql = NAMED_PARAM_RE.sub("1", sql)
    sql = POSITIONAL_PARAM_RE.sub("1", sql)
    return sql


def _clean_table_name(table: Any) -> str:
    """Strip sqllineage's placeholder schema prefix from unqualified names."""
    s = str(table)
    if s.startswith(SQLLINEAGE_DEFAULT_SCHEMA_PREFIX):
        return s[len(SQLLINEAGE_DEFAULT_SCHEMA_PREFIX):]
    return s


def _lineage_exception_reason(exc: Exception) -> str:
    reason = str(exc).splitlines()[0][:150] if str(exc) else ""
    return f"{type(exc).__name__}: {reason}".rstrip(": ")


def _run_sqllineage(query_text: str, dialect: str) -> Dict[str, Any]:
    normalized = _normalize_bind_params(query_text)
    runner = LineageRunner(normalized, dialect=dialect)
    return {
        "available": True,
        "source_tables": sorted({_clean_table_name(t) for t in runner.source_tables}),
        "target_tables": sorted({_clean_table_name(t) for t in runner.target_tables}),
    }


def extract_sql_lineage(query_text: str, dialect: str = "ansi") -> Dict[str, Any]:
    """Best-effort source/target table extraction for one native SQL query."""
    if not _SQLLINEAGE_AVAILABLE:
        return {"available": False, "reason": "sqllineage not installed"}
    try:
        return _run_sqllineage(query_text, dialect)
    except Exception as exc:
        return {"available": False, "reason": _lineage_exception_reason(exc)}


def _entity_map_lineage_gate(entity_name: str, map_entry: Dict[str, Any]) -> Any:
    """Return an unavailable lineage dict when the entity map cannot safely
    resolve entity_name, else None."""
    if map_entry is None:
        return {
            "available": False,
            "reason": (
                f"entity '{entity_name}' not found in entity_table_map — unresolved rather than "
                "guessed (possibly an @Entity(name=...) override this scanner doesn't capture)"
            ),
        }
    if map_entry.get("status") != "contested":
        return None
    candidates = map_entry.get("candidates", [])
    n = len(candidates) if candidates else 2
    return {
        "available": False,
        "reason": (
            f"entity '{entity_name}' is contested — ambiguous simple name across packages "
            f"({n} candidates); refusing to guess a table"
        ),
    }


_MULTI_ENTITY_REASON = (
    "multi-entity or unparseable FROM clause, out of scope for the bounded JPQL resolver"
)


def _jpql_unavailable(reason: str) -> Dict[str, Any]:
    return {"available": False, "reason": reason}


def _jpql_from_match_or_reject(jpql_text: str) -> Any:
    """Return the sole FROM match when in scope, else an unavailable dict."""
    if JPQL_JOIN_RE.search(jpql_text):
        return _jpql_unavailable(_MULTI_ENTITY_REASON)
    matches = list(JPQL_FROM_RE.finditer(jpql_text))
    if len(matches) != 1:
        return _jpql_unavailable(_MULTI_ENTITY_REASON)
    if JPQL_FUNCTION_RE.search(jpql_text):
        return _jpql_unavailable(
            "uses a JPQL-only relationship function (SIZE/KEY/VALUE/INDEX/TYPE), out of scope"
        )
    from_match = matches[0]
    if jpql_text[from_match.end():].lstrip().startswith(","):
        return _jpql_unavailable(_MULTI_ENTITY_REASON)
    return from_match


def _jpql_alias_traversal_reject(jpql_text: str, alias: str) -> Any:
    traversal_re = re.compile(r"\b" + re.escape(alias) + r"\.\w+\.\w+")
    if traversal_re.search(jpql_text):
        return _jpql_unavailable(
            "association-traversal path through the entity alias, out of scope"
        )
    return None


def _rewrite_jpql_from_entity(jpql_text: str, from_match: Any, table: str, alias: str) -> str:
    rewritten = (
        jpql_text[:from_match.start()]
        + f"FROM {table}"
        + jpql_text[from_match.end():]
    )
    alias_prefix_re = re.compile(r"\b" + re.escape(alias) + r"\.")
    return alias_prefix_re.sub("", rewritten)


def resolve_jpql_to_lineage(jpql_text: str, entity_table_map: Dict[str, Any], dialect: str = "ansi") -> Dict[str, Any]:
    """Best-effort lineage for the narrow slice of JPQL this scanner can
    safely rewrite to real SQL. See spring_signal_scan.py for the full
    scope statement; this is a direct extraction of that logic.
    """
    scoped = _jpql_from_match_or_reject(jpql_text)
    if not hasattr(scoped, "group"):
        return scoped
    from_match = scoped
    entity_name, alias = from_match.group(1), from_match.group(2)
    traversal_reject = _jpql_alias_traversal_reject(jpql_text, alias)
    if traversal_reject is not None:
        return traversal_reject
    map_entry = entity_table_map.get(entity_name)
    if (gated := _entity_map_lineage_gate(entity_name, map_entry)) is not None:
        return gated
    rewritten = _rewrite_jpql_from_entity(
        jpql_text, from_match, map_entry["table"], alias,
    )
    result = extract_sql_lineage(rewritten, dialect=dialect)
    if result["available"]:
        result["resolved_via_entity"] = entity_name
    return result


class SpringLineageResolver(LineageResolver):
    """Spring Boot implementation of the LineageResolver protocol."""

    def _annotate_query_entry(
        self,
        entry: Dict[str, Any],
        *,
        entity_table_map: Dict[str, Any],
        sql_dialect: str,
    ) -> None:
        query = entry.get("query")
        if query is None:
            return
        kind = entry.get("query_kind")
        if kind == "native":
            entry["lineage"] = extract_sql_lineage(query, dialect=sql_dialect)
        elif kind == "jpql":
            entry["lineage"] = resolve_jpql_to_lineage(
                query, entity_table_map, dialect=sql_dialect,
            )

    def resolve(self, signal: Dict[str, Any], sql_dialect: str = "ansi", **kwargs: Any) -> Dict[str, Any]:
        entity_table_map = signal.get("entity_table_map", {})
        for entry in signal.get("evidence", {}).get("raw_queries", []):
            self._annotate_query_entry(
                entry, entity_table_map=entity_table_map, sql_dialect=sql_dialect,
            )
        return signal
