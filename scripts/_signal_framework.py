"""Backward-compatible shim — protocols live in doc_engine.core."""

from doc_engine.core.protocols import LineageResolver, Merger, Scanner, Signal  # noqa: F401

__all__ = ["Scanner", "Merger", "LineageResolver", "Signal"]
