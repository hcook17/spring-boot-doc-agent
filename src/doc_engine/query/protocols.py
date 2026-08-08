"""Protocols earned by ≥2 implementations (packet providers, freshness)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class PacketProvider(Protocol):
    """Strategy: produce unscored context items for a request."""

    name: str

    def provide(
        self,
        request: str,
        *,
        signals: Mapping[str, Any],
        facts_rows: list[Mapping[str, Any]],
        run_dir: Path,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return items with keys path/line/match/bucket/reason/payload (pre-score)."""
        ...


@runtime_checkable
class FreshnessPolicy(Protocol):
    """Label a repo-relative path for currency (DDIA: truth vs freshness)."""

    def freshness_for(self, rel_path: str | None) -> str:
        """Return live | fresh_indexed | stale | unknown."""
        ...
