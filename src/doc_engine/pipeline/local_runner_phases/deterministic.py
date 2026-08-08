"""Phase 5: DETERMINISTIC_ONLY / no-generative early return."""

from __future__ import annotations

from typing import Optional

from doc_engine.pipeline import gates
from doc_engine.pipeline.compliance import ComplianceProfile
from doc_engine.pipeline.local_runner_phases.state import LocalRunState
from doc_engine.pipeline.local_runner_phases.support import (
    _artifact_inventory,
    _py_mod,
    _run_drift_check,
    _write_certification_and_finish,
)


def phase_deterministic_only(state: LocalRunState) -> Optional[int]:
    """Validate + finalize when generative stages are out of scope."""
    profile = state.profile
    if profile != ComplianceProfile.DETERMINISTIC_ONLY and state.generative_specs:
        return None

    log = state.log
    runner = state.runner
    args = state.args

    log.rule("GATES (deterministic artifacts)")
    gates.run_gate_via_runner(
        runner,
        "validate_artifacts.py --all (B contract gate)",
        lambda: (gates.run_validate_all_artifacts(state.out_dir), "OK"),
        gate=True,
        gate_id="validate_artifacts_all",
    )

    log.rule("FINALIZE (real)")
    fin_argv = _py_mod(
        "doc_engine.tools.run_manifest",
        "finalize",
        state.manifest,
        "--signals-file",
        state.signals_path,
        "--preflight-file",
        state.preflight_path,
    )
    runner.run("run_manifest finalize", fin_argv)
    runner.run(
        "run_manifest summary",
        _py_mod("doc_engine.tools.run_manifest", "summary", state.manifest),
    )

    _run_drift_check(
        log,
        runner,
        state.repo_path,
        state.manifest,
        state.out_dir,
        args,
        state.signals_path,
    )
    _artifact_inventory(log, state.out_dir)

    until_note = (
        f" Stopped after --until {state.until_stage}."
        if state.until_stage and profile == ComplianceProfile.CERTIFIED
        else ""
    )
    return _write_certification_and_finish(
        log,
        runner,
        profile,
        state.repo_path,
        state.out_dir,
        "none",
        allow_mock=state.allow_mock,
        success_lines=[
            "RESULT: deterministic stages complete. Run generative stages via "
            "Claude Code + document-spring-repo skill for real docs."
            + until_note,
        ],
    )
