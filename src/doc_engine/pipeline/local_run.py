"""Local end-to-end pipeline orchestration for the doc-engine CLI."""

from __future__ import annotations

from typing import Sequence

from doc_engine.pipeline.local_runner import add_run_arguments, main, run_pipeline


def run(argv: Sequence[str] | None = None) -> int:
    """Parse argv and run the local pipeline (default: sys.argv)."""
    return main(list(argv) if argv is not None else None)
