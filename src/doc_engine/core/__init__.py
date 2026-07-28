"""Core types, protocols, and shared repository indexing."""

from doc_engine.core.context import FileEntry, ScanContext
from doc_engine.core.protocols import LineageResolver, Merger, Scanner, Signal
from doc_engine.core.walk import compute_file_signature, dfs_walk

__all__ = [
    "FileEntry",
    "ScanContext",
    "Scanner",
    "Merger",
    "LineageResolver",
    "Signal",
    "dfs_walk",
    "compute_file_signature",
]
