"""Query strategy handlers (one module per kind)."""

from doc_engine.query.handlers import dependents, entity, evidence, facts, route_trace, routes

__all__ = [
    "dependents",
    "entity",
    "evidence",
    "facts",
    "route_trace",
    "routes",
]
