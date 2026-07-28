"""Local end-to-end pipeline orchestration for the doc-engine CLI.

Delegates to scripts/run_pipeline_local.py — single implementation of the
stage graph, gates, and mock generative stages until HttpLLMStageExecutor lands.
"""

from __future__ import annotations

from typing import Sequence

from doc_engine.tools._bootstrap import ensure_scripts_importable


def _ensure_script_import_path() -> None:
    ensure_scripts_importable()


def run_pipeline(args) -> int:
    """Run the local pipeline with a parsed argparse namespace."""
    _ensure_script_import_path()
    import run_pipeline_local  # noqa: WPS433 — intentional scripts/ entry

    return run_pipeline_local.run_pipeline(args)


def add_run_arguments(ap) -> None:
    """Register pipeline run flags on an ArgumentParser."""
    _ensure_script_import_path()
    import run_pipeline_local  # noqa: WPS433

    run_pipeline_local.add_run_arguments(ap)


def run(argv: Sequence[str] | None = None) -> int:
    """Parse argv and run the local pipeline (default: sys.argv)."""
    _ensure_script_import_path()
    import run_pipeline_local  # noqa: WPS433

    return run_pipeline_local.main(list(argv) if argv is not None else None)
