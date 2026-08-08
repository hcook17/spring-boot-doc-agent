"""Read-only typed queries over Stage-0 artifacts (signals / facts / edges).

SoR stays on disk; this package returns capped derived views for agents.
"""

from doc_engine.query.envelope import (
    QUERY_RESULT_SCHEMA_VERSION,
    QueryResult,
    apply_limit,
    build_query_result,
)
from doc_engine.query.packet import CONTEXT_PACKET_SCHEMA_VERSION, run_context_packet
from doc_engine.query.registry import get_query_handler, run_query

__all__ = [
    "CONTEXT_PACKET_SCHEMA_VERSION",
    "QUERY_RESULT_SCHEMA_VERSION",
    "QueryResult",
    "apply_limit",
    "build_query_result",
    "get_query_handler",
    "run_context_packet",
    "run_query",
]
