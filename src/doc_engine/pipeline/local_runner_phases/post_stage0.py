"""Phase 4: post-stage0 evidence pool + SCAN_ONLY early return."""

from __future__ import annotations

import os
from typing import Optional

from doc_engine.pipeline import gates
from doc_engine.pipeline.compliance import ComplianceProfile
from doc_engine.pipeline.local_runner_phases.state import LocalRunState
from doc_engine.pipeline.local_runner_phases.support import (
    _artifact_inventory,
    _write_certification_and_finish,
)
from doc_engine.pipeline.mock_stages import _read_json, load_citations


def _load_signals_if_needed(state: LocalRunState) -> None:
    ctx = state.pipeline_ctx
    assert ctx is not None
    if ctx.signals is None and os.path.isfile(state.signals_path):
        ctx.signals = _read_json(state.signals_path)


def _log_evidence_pool(state: LocalRunState) -> None:
    ctx = state.pipeline_ctx
    assert ctx is not None
    pool = load_citations(ctx.signals, state.repo_path)
    ctx.pool = pool
    resolvable = sum(len(bucket) for bucket in pool.values())
    non_empty_buckets = sum(1 for bucket in pool.values() if bucket)
    state.log("")
    state.log(
        f"  evidence pool: {resolvable} resolvable citation(s) across "
        f"{non_empty_buckets} non-empty bucket(s)"
    )
    if ctx.groups:
        state.log(
            f"  groups: {ctx.groups['num_groups']} covering "
            f"{ctx.groups['total_files_considered']} file(s)"
        )


def _finish_scan_only(state: LocalRunState) -> int:
    log = state.log
    runner = state.runner
    log.rule("GATES (scan-only)")
    gates.run_gate_via_runner(
        runner,
        "validate_artifacts.py spring_signals (scan-only gate)",
        lambda: (gates.run_validate_spring_signals(state.signals_path), "OK"),
        gate=True,
        gate_id="validate_artifacts_spring_signals",
    )
    _artifact_inventory(log, state.out_dir)
    return _write_certification_and_finish(
        log,
        runner,
        state.profile,
        state.repo_path,
        state.out_dir,
        "none",
        allow_mock=state.allow_mock,
        success_lines=["RESULT: scan-only profile complete."],
    )


def phase_post_stage0(state: LocalRunState) -> Optional[int]:
    """Load evidence pool; finish early when profile is SCAN_ONLY."""
    assert state.pipeline_ctx is not None
    _load_signals_if_needed(state)
    if state.profile != ComplianceProfile.SCAN_ONLY:
        _log_evidence_pool(state)
        return None
    return _finish_scan_only(state)
