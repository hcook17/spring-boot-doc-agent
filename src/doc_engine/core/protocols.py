"""Language-agnostic protocols for scanners, mergers, and lineage resolvers."""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

Signal = Dict[str, Any]


@runtime_checkable
class Scanner(Protocol):
    """Structural interface for Stage 0 scanner backends (see ScannerBackend ABC)."""

    @property
    def name(self) -> str: ...

    def version_hash(self) -> str: ...

    def scan(self, repo_path: str, **kwargs: Any) -> Signal: ...


@runtime_checkable
class Merger(Protocol):
    def merge(
        self,
        partials: List[Signal],
        repo_path: str,
        scanner_version: str,
        scanner_names: Optional[List[str]] = None,
    ) -> Signal: ...


@runtime_checkable
class LineageResolver(Protocol):
    def resolve(self, signal: Signal, **kwargs: Any) -> Signal: ...
