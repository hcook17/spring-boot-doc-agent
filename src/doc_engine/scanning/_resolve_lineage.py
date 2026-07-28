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


def extract_sql_lineage(query_text: str, dialect: str = "ansi") -> Dict[str, Any]:
    """Best-effort source/target table extraction for one native SQL query."""
    if not _SQLLINEAGE_AVAILABLE:
        return {"available": False, "reason": "sqllineage not installed"}
    try:
        normalized = _normalize_bind_params(query_text)
        runner = LineageRunner(normalized, dialect=dialect)
        source_tables = sorted({_clean_table_name(t) for t in runner.source_tables})
        target_tables = sorted({_clean_table_name(t) for t in runner.target_tables})
        return {
            "available": True,
            "source_tables": source_tables,
            "target_tables": target_tables,
        }
    except Exception as e:
        reason = str(e).splitlines()[0][:150] if str(e) else ""
        return {"available": False, "reason": f"{type(e).__name__}: {reason}".rstrip(": ")}


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


def resolve_jpql_to_lineage(jpql_text: str, entity_table_map: Dict[str, Any], dialect: str = "ansi") -> Dict[str, Any]:
    """Best-effort lineage for the narrow slice of JPQL this scanner can
    safely rewrite to real SQL. See spring_signal_scan.py for the full
    scope statement; this is a direct extraction of that logic.
    """
    if JPQL_JOIN_RE.search(jpql_text):
        return {
            "available": False,
            "reason": "multi-entity or unparseable FROM clause, out of scope for the bounded JPQL resolver",
        }
    matches = list(JPQL_FROM_RE.finditer(jpql_text))
    if len(matches) != 1:
        return {
            "available": False,
            "reason": "multi-entity or unparseable FROM clause, out of scope for the bounded JPQL resolver",
        }
    if JPQL_FUNCTION_RE.search(jpql_text):
        return {
            "available": False,
            "reason": "uses a JPQL-only relationship function (SIZE/KEY/VALUE/INDEX/TYPE), out of scope",
        }

    from_match = matches[0]
    entity_name, alias = from_match.group(1), from_match.group(2)

    if jpql_text[from_match.end():].lstrip().startswith(","):
        return {
            "available": False,
            "reason": "multi-entity or unparseable FROM clause, out of scope for the bounded JPQL resolver",
        }

    traversal_re = re.compile(r"\b" + re.escape(alias) + r"\.\w+\.\w+")
    if traversal_re.search(jpql_text):
        return {
            "available": False,
            "reason": "association-traversal path through the entity alias, out of scope",
        }

    map_entry = entity_table_map.get(entity_name)
    if (gated := _entity_map_lineage_gate(entity_name, map_entry)) is not None:
        return gated

    rewritten = jpql_text[:from_match.start()] + f"FROM {map_entry['table']}" + jpql_text[from_match.end():]
    alias_prefix_re = re.compile(r"\b" + re.escape(alias) + r"\.")
    rewritten = alias_prefix_re.sub("", rewritten)

    result = extract_sql_lineage(rewritten, dialect=dialect)
    if result["available"]:
        result["resolved_via_entity"] = entity_name
    return result


class SpringLineageResolver(LineageResolver):
    """Spring Boot implementation of the LineageResolver protocol."""

    def resolve(self, signal: Dict[str, Any], sql_dialect: str = "ansi", **kwargs: Any) -> Dict[str, Any]:
        entity_table_map = signal.get("entity_table_map", {})
        for entry in signal.get("evidence", {}).get("raw_queries", []):
            if entry.get("query_kind") == "native" and entry.get("query") is not None:
                entry["lineage"] = extract_sql_lineage(entry["query"], dialect=sql_dialect)
            elif entry.get("query_kind") == "jpql" and entry.get("query") is not None:
                entry["lineage"] = resolve_jpql_to_lineage(entry["query"], entity_table_map, dialect=sql_dialect)
        return signal
