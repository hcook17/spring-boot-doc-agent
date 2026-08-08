"""Local pipeline run phases (setup → stage0 → gates → finish).

Phase modules own one pipeline segment; ``local_runner`` sequences them.
``LocalRunState`` is the shared run-state DTO across phases.
"""

from __future__ import annotations

from doc_engine.pipeline.local_runner_phases.context import phase_build_context
from doc_engine.pipeline.local_runner_phases.deterministic import phase_deterministic_only
from doc_engine.pipeline.local_runner_phases.full_finish import phase_full_finish
from doc_engine.pipeline.local_runner_phases.generative import phase_generative
from doc_engine.pipeline.local_runner_phases.post_stage0 import phase_post_stage0
from doc_engine.pipeline.local_runner_phases.setup import phase_setup
from doc_engine.pipeline.local_runner_phases.stage0 import phase_stage0
from doc_engine.pipeline.local_runner_phases.state import LocalRunState
from doc_engine.pipeline.local_runner_phases.support import (
    Log,
    Runner,
    _artifact_inventory,
    _py_mod,
    _quote,
    _run_drift_check,
    _write_certification_and_finish,
)

__all__ = [
    "LocalRunState",
    "Log",
    "Runner",
    "_artifact_inventory",
    "_py_mod",
    "_quote",
    "_run_drift_check",
    "_write_certification_and_finish",
    "phase_build_context",
    "phase_deterministic_only",
    "phase_full_finish",
    "phase_generative",
    "phase_post_stage0",
    "phase_setup",
    "phase_stage0",
]
