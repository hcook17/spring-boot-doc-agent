"""Re-export the scanner framework for SDK consumers."""

from doc_engine.core.protocols import LineageResolver, Merger, Scanner, Signal
from doc_engine.scanning import (
    SpringLineageResolver,
    SpringSignalMerger,
    get_scanner,
    resolve_scanner_names,
    run_scan,
)

__all__ = [
    "Scanner",
    "Merger",
    "LineageResolver",
    "Signal",
    "SpringSignalMerger",
    "SpringLineageResolver",
    "run_scan",
    "get_scanner",
    "resolve_scanner_names",
]
