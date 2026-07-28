#!/usr/bin/env python3
"""Base class and types for scanner backends.

A scanner backend is a pluggable source of evidence for spring_signal_scan.py.
Each backend produces a partial spring_signals.json-shaped dict. The orchestrator
runs one or more backends and merges their outputs deterministically.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class ScannerBackend(ABC):
    """Abstract base class for a Stage 0 scanner backend.

    Backends must be deterministic and must return a dict that matches the
    canonical spring_signals.json schema at the top level. They may omit fields
    they do not produce; the merge step fills in defaults.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique, stable identifier for this backend (e.g. 'codeql', 'ast-grep')."""
        ...

    @abstractmethod
    def version_hash(self) -> str:
        """Return a stable hash of this backend's code and rule files.

        The orchestrator combines backend version hashes into the overall
        scanner_version. Any change that could alter output must change this
        hash.
        """
        ...

    @abstractmethod
    def scan(self, repo_path: str, **kwargs: Any) -> Dict[str, Any]:
        """Scan the repository and return a partial spring_signals.json dict.

        The returned dict should contain the top-level keys the backend
        produces, typically including some of:
          - evidence
          - entity_table_map
          - redaction_zones
          - config_key_sets
          - file_signatures
          - files_scanned

        All file paths must be relative to repo_path with forward slashes.
        Evidence rows must be sorted by (file, line) for determinism.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name})"
