"""Run the whole document-spring-repo pipeline locally,
end to end, against one target repo, with every stage's real command line and
real output on screen and in a log file.

A+C hybrid: Claude skills call ``doc-engine pipeline run`` / ``pipeline gates``
(not plugin-local scripts). Stage graph SoT is ``build_stage_specs()``; use
``--until STAGE`` to truncate. Product tools live under ``doc_engine.tools``
(``python -m``); prefer in-process ``gates.py`` where already lifted.

WHY THIS EXISTS
The pipeline is normally driven by a live Claude Code session. Stage 0's
scripts are ordinary subprocesses, but Stages 1–4 are subagent fan-outs that
cannot be dispatched from a plain Python process — that is exactly why
test_pipeline_stages.py defaults to synthetic data, and why CI runs only unit
tests. So there was nothing a person could run by hand to answer the practical
question: "what does this pipeline actually do, in what order, reading what,
writing what, and what do its gates say about the result?"

This script is that. It runs every deterministic stage for real, and stands in
for the four LLM stages with mock artifacts written in the exact documented
shapes — so the real gates and checkers downstream have real input and print
real output.

WHAT IS REAL AND WHAT IS MOCK — read this before trusting any output.

  Real (actual scripts, actual results):
    run_manifest.py            init / start-stage / end-stage / finalize / summary
    spring_signal_scan.py      Stage 0 ast-grep evidence extraction
    partition_repo.py          Stage 0 adaptive grouping
    build_cross_group_edges.py Stage 0 cross-group join
    capacity_preflight.py      pre-run scale estimate
    spring_drift_check.py      post-run drift re-verification
    check_pipeline_output.py   Stage 4 gate
    citation_coverage.py       missing / mis-anchored citation worklist
    check_no_secrets_leaked.py confidentiality re-check
    test_pipeline_stages.py    opt-in real-artifacts structural pass

  Mock (this script writes them; no model is involved):
    Stage 1  summaries_group_<id>.json, summaries.json
    Stage 2  arch_fragment_<id>.md, architecture_merged.md
    Stage 3  gap_questions.json, interview_answers.json
    Stage 4  docs/<fourteen>.md

The mock artifacts are shape-faithful and citation-faithful: every
[Evidenced — path:line] tag they emit is a real file and a real line taken
from this run's own signal scan, so the gates pass honestly rather than being
handed something that could not fail. They are deliberately NOT
content-faithful — the prose is templated from annotation matches, and no
document this script writes is documentation of anything. The point is the
wiring, the artifact inventory, and the gate output, not the text.

Usage:
    doc-engine pipeline run /abs/path/to/spring-repo
    python -m doc_engine.pipeline.local_runner /abs/path/to/spring-repo

    # write the fourteen docs into the target repo's own docs/ (as a real run
    # does), which also enables check_pipeline_output's stray-write check:
    python -m doc_engine.pipeline.local_runner /abs/path/to/repo --docs-in-target-repo

    # compare drift against a real earlier scan instead of this run's own:
    python -m doc_engine.pipeline.local_runner /abs/path/to/repo --prior-signals old_signals.json

    # deterministic stages only (scan through capacity preflight; no mock LLM stages):
    python -m doc_engine.pipeline.local_runner /abs/path/to/repo --deterministic-only

    # reuse an existing spring_signals.json and skip signal_scan:
    python -m doc_engine.pipeline.local_runner /abs/path/to/repo --deterministic-only \\
        --signals-file /path/to/spring_signals.json

Artifacts and run.log land in --out-dir (default: ./local-runs/<repo>-<stamp>/),
never in the target repo, unless --docs-in-target-repo is passed.

Exit code is 0 only if every gate passed. See the STEP RESULTS table it prints
at the end for which one didn't.

Phase modules live under ``doc_engine.pipeline.local_runner_phases``; this
module remains the stable public facade (CLI args, ``run_pipeline``, re-exports).
"""

from __future__ import annotations

import argparse
import sys

from doc_engine.pipeline.compliance import ComplianceProfile
from doc_engine.pipeline.local_runner_phases import (  # noqa: F401 — public re-exports
    Log,
    Runner,
    _artifact_inventory,
    _py_mod,
    _quote,
    _run_drift_check,
    _write_certification_and_finish,
)
from doc_engine.pipeline.local_runner_phases.context import phase_build_context
from doc_engine.pipeline.local_runner_phases.deterministic import phase_deterministic_only
from doc_engine.pipeline.local_runner_phases.full_finish import phase_full_finish
from doc_engine.pipeline.local_runner_phases.generative import phase_generative
from doc_engine.pipeline.local_runner_phases.post_stage0 import phase_post_stage0
from doc_engine.pipeline.local_runner_phases.setup import phase_setup
from doc_engine.pipeline.local_runner_phases.stage0 import phase_stage0


def build_arg_parser():
    ap = argparse.ArgumentParser(
        description="Run the document-spring-repo pipeline locally, end to end, "
                    "against one target repo. Deterministic stages run for real; "
                    "the four LLM stages are mocked in their documented shapes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Every stage's command line and output is echoed and also written "
               "to <out-dir>/run.log.",
    )
    add_run_arguments(ap)
    return ap


def add_run_arguments(ap: argparse.ArgumentParser) -> None:
    """Register local pipeline flags on an ArgumentParser (CLI or script entry)."""
    ap.add_argument("repo_path", help="absolute path to the target Spring Boot repo")
    ap.add_argument("--out-dir", default=None,
                    help="where artifacts and run.log go "
                         "(default: ./local-runs/<repo>-<timestamp>)")
    ap.add_argument("--max-tokens", type=int, default=120000,
                    help="partition_repo.py --max-tokens (default: 120000, the "
                         "value SKILL.md Stage 0 uses)")
    ap.add_argument("--docs-in-target-repo", action="store_true",
                    help="write the fourteen docs into <repo>/docs/ as a real run "
                         "does, which also enables check_pipeline_output.py's "
                         "stray-write check. Off by default: this script should not "
                         "modify your repo unless you ask it to.")
    ap.add_argument("--prior-signals", default=None,
                    help="a real earlier spring_signals.json to measure drift "
                         "against (default: this run's own scan, which should "
                         "report no drift)")
    ap.add_argument("--skip-drift", action="store_true",
                    help="skip spring_drift_check.py — it re-hashes every file, "
                         "which roughly doubles scan time on a large repo")
    ap.add_argument("--respect-gitignore", action="store_true",
                    help="pass --respect-gitignore to the scan and partition stages")
    ap.add_argument("--strict-citations", action="store_true",
                    help="pass --strict to citation_coverage.py, making its "
                         "heuristic findings a gate failure")
    ap.add_argument("--keep-going", action="store_true",
                    help="continue after a failed prerequisite stage instead of "
                         "stopping")
    ap.add_argument(
        "--compliance-profile",
        choices=[profile.value for profile in ComplianceProfile],
        default=None,
        help="compliance profile: scan_only, deterministic_only, or certified "
             "(default: certified, or value from .doc-engine.yml)",
    )
    ap.add_argument("--deterministic-only", action="store_true",
                    help="shorthand for --compliance-profile deterministic_only")
    ap.add_argument(
        "--allow-mock",
        action="store_true",
        help=(
            "allow CERTIFIED profile to fold certified=true when "
            "generative_executor is none/mock (local wiring runs). "
            "Live adoption gates still require verify --allow-mock or live."
        ),
    )
    ap.add_argument("--signals-file", default=None,
                    help="reuse an existing spring_signals.json; copies into "
                         "--out-dir and skips the signal_scan stage")
    ap.add_argument(
        "--until",
        default=None,
        metavar="STAGE",
        help="stop after this stage name from build_stage_specs() "
             "(e.g. signal_scan, partition, cross_group_edges). "
             "Stage graph SoT remains stages.py — this only truncates.",
    )
    ap.add_argument(
        "--trust-repo-config",
        action="store_true",
        help=(
            "honor security-sensitive keys from the target repo's "
            ".doc-engine.yml (build_command, db_path, scanners, weakened "
            "compliance_profile). Default: treat that file as untrusted."
        ),
    )


def run_pipeline(args) -> int:
    """Sequence local-runner phases; return process exit code."""
    setup = phase_setup(args)
    if isinstance(setup, int):
        return setup

    for phase in (
        phase_build_context,
        phase_stage0,
        phase_post_stage0,
        phase_deterministic_only,
        phase_generative,
    ):
        code = phase(setup)
        if code is not None:
            return code
    return phase_full_finish(setup)


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    return run_pipeline(args)


if __name__ == "__main__":
    sys.exit(main())
