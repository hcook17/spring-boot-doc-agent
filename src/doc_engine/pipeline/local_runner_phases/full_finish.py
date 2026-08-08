"""Phase 7: full gates + post-run checks + finalize + drift + certification."""

from __future__ import annotations

import os

from doc_engine.paths import repo_root
from doc_engine.pipeline import gates
from doc_engine.pipeline.local_runner_phases.state import LocalRunState
from doc_engine.pipeline.local_runner_phases.support import (
    _artifact_inventory,
    _py_mod,
    _run_drift_check,
    _write_certification_and_finish,
)

REPO_ROOT = str(repo_root())


def phase_full_finish(state: LocalRunState) -> int:
    """Run certified-profile gates, finalize, drift, and write certification."""
    log = state.log
    runner = state.runner
    args = state.args
    repo_path = state.repo_path
    out_dir = state.out_dir
    docs_dir = state.docs_dir
    py = state.py

    log.rule("GATES AND POST-RUN CHECKS (real)")

    gates.run_gate_via_runner(
        runner,
        "validate_artifacts.py --all (B contract gate)",
        lambda: (gates.run_validate_all_artifacts(out_dir), "OK"),
        gate=True,
        gate_id="validate_artifacts_all",
    )

    gates.run_gate_via_runner(
        runner,
        "pipeline_validators.py (summaries + gap_questions gate)",
        lambda: gates.run_pipeline_validators(out_dir, repo_path),
        gate=True,
        gate_id="pipeline_validators",
    )

    gate_argv = _py_mod(
        "doc_engine.tools.check_pipeline_output",
        docs_dir,
        "--target-repo",
        repo_path,
    )
    if not args.docs_in_target_repo:
        gate_argv.append("--no-write-check")
        log("")
        log("  note: --no-write-check is passed because the docs were written outside")
        log("        the target repo. Re-run with --docs-in-target-repo to exercise")
        log("        the stray-write check for real.")
    runner.run(
        "check_pipeline_output (Stage 4 GATE)",
        gate_argv,
        gate=True,
        gate_id="check_pipeline_output",
    )

    cc_argv = _py_mod(
        "doc_engine.tools.citation_coverage",
        docs_dir,
        "--target-repo",
        repo_path,
    )
    if state.strict_citations_effective:
        cc_argv.append("--strict")
    runner.run(
        "citation_coverage",
        cc_argv,
        gate=state.strict_citations_effective,
        gate_id="citation_coverage",
    )

    runner.run(
        "check_no_secrets_leaked",
        _py_mod(
            "doc_engine.tools.check_no_secrets_leaked",
            os.path.join(out_dir, "summaries.json"),
            docs_dir,
        ),
        gate=True,
        gate_id="check_no_secrets_leaked",
    )

    env = dict(os.environ)
    env["PIPELINE_ARTIFACTS_DIR"] = out_dir
    env["PIPELINE_ARTIFACTS_TARGET_REPO"] = repo_path
    if docs_dir != os.path.join(out_dir, "docs"):
        log("")
        log("  note: test_pipeline_stages.py's real-artifacts pass looks for docs/ inside")
        log("        PIPELINE_ARTIFACTS_DIR. With --docs-in-target-repo the docs are")
        log("        elsewhere, so its docs subtest will skip; summaries and gap")
        log("        questions are still validated.")
    runner.run(
        "pytest tests/doc_engine/test_pipeline_stages.py -v (real suite vs. mock artifacts)",
        [
            py,
            "-m",
            "pytest",
            os.path.join(REPO_ROOT, "tests", "doc_engine", "test_pipeline_stages.py"),
            "-v",
        ],
        gate=True,
        gate_id="test_pipeline_stages",
        env=env,
    )

    log.rule("FINALIZE (real)")
    runner.run(
        "run_manifest finalize",
        _py_mod(
            "doc_engine.tools.run_manifest",
            "finalize",
            state.manifest,
            "--signals-file",
            state.signals_path,
            "--docs-dir",
            docs_dir,
            "--interview-file",
            os.path.join(out_dir, "interview_answers.json"),
            "--preflight-file",
            state.preflight_path,
        ),
    )
    runner.run(
        "run_manifest summary",
        _py_mod("doc_engine.tools.run_manifest", "summary", state.manifest),
    )

    _run_drift_check(
        log, runner, repo_path, state.manifest, out_dir, args, state.signals_path
    )

    _artifact_inventory(log, out_dir)
    if args.docs_in_target_repo:
        log("")
        log(f"  plus the fourteen docs written into {docs_dir}")

    return _write_certification_and_finish(
        log,
        runner,
        state.profile,
        repo_path,
        out_dir,
        "mock",
        allow_mock=state.allow_mock,
        success_lines=[
            "RESULT: every gate passed. Remember Stages 1-4 were mocked: this says the "
            "wiring and the checks work, not that any document is correct.",
        ],
    )
