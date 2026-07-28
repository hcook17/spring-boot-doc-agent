"""Local end-to-end pipeline orchestration for the doc-engine CLI.

Delegates to scripts/run_pipeline_local.py — single implementation of the
stage graph, gates, and mock generative stages until HttpLLMStageExecutor lands.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence


def _ensure_script_import_path() -> None:
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    src = scripts.parent / "src"
    scripts_str = str(scripts)
    src_str = str(src)
    if scripts_str not in sys.path:
        sys.path.insert(0, scripts_str)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)


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
