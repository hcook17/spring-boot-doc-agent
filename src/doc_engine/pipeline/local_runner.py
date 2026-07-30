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
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from doc_engine.paths import repo_root

REPO_ROOT = str(repo_root())

from doc_engine.config.loader import load_repo_config  # noqa: E402
from doc_engine.pipeline import gates  # noqa: E402
from doc_engine.pipeline.compliance import (  # noqa: E402
    ComplianceProfile,
    build_certification_report,
    resolve_compliance_profile,
    stage_records_from_runner_results,
    stages_for_profile,
    write_certification_json,
)
from doc_engine.pipeline.context import PipelineContext, StageKind  # noqa: E402
from doc_engine.pipeline.executor import MockStageExecutor  # noqa: E402
from doc_engine.pipeline.mock_stages import (  # noqa: E402
    _read_json,
    _write_json,
    find_existing_readme,
    load_citations,
    mock_architecture,
    mock_docs,
    mock_file_summaries,
    mock_gap_and_interview,
    sweep_todos,
)
from doc_engine.pipeline.runner import PipelineRunner  # noqa: E402
from doc_engine.pipeline.stages import build_stage_specs  # noqa: E402


class Log:
    """Tee to stdout and run.log.

    Everything this script prints goes to both, so the log file is a complete
    transcript rather than a summary — the user asked to see the logs, and a
    log that omits what scrolled past is worse than no log.
    """

    def __init__(self, path):
        self.path = path
        self.fh = open(path, "w", encoding="utf-8")
        # Console encoding on Windows is frequently cp1252, which cannot
        # represent the em dash the tag grammar requires. Replace on the
        # console rather than crash; the log file is UTF-8 and keeps it.
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8", errors="replace")
                except (ValueError, OSError):
                    pass

    def __call__(self, msg=""):
        text = str(msg)
        print(text)
        self.fh.write(text + "\n")
        self.fh.flush()

    def rule(self, title):
        self("")
        self("=" * 78)
        self(title)
        self("=" * 78)

    def close(self):
        self.fh.close()


class Runner:
    """Runs the pipeline's steps, records each one's outcome, prints a table."""

    def __init__(self, log, keep_going):
        self.log = log
        self.keep_going = keep_going
        self.results = []  # (label, status, seconds, detail)
        self.gate_records = []
        self.aborted = False

    def record(self, label, status, seconds, detail=""):
        self.results.append((label, status, seconds, detail))

    def _record_gate(self, gate_id, label, status, detail="", required=True):
        from doc_engine.pipeline.compliance import GateRecord

        gate_status = "ok" if status == "OK" else "skipped" if status == "SKIPPED" else "fail"
        self.gate_records.append(
            GateRecord(
                id=gate_id,
                label=label,
                status=gate_status,
                required=required,
                detail=detail,
            )
        )

    def run(self, label, argv, gate=False, gate_id=None, critical=False, cwd=None, env=None,
            quiet=False):
        """Run one subprocess, echoing its exact command line and full output.

        gate=True     a non-zero exit is a real failure of the run, not just
                      information — it lands in the table as FAIL and makes
                      this script's own exit code non-zero.
        critical=True a non-zero exit means nothing downstream can be
                      meaningful, so stop (unless --keep-going).
        quiet=True    for the manifest bookkeeping calls, whose one-line
                      output would otherwise drown the stages themselves.
        """
        if self.aborted:
            self.record(label, "SKIPPED", 0.0, "aborted earlier")
            return None

        printable = " ".join(_quote(a) for a in argv)
        if quiet:
            self.log(f"  $ {printable}")
        else:
            self.log("")
            self.log(f"--- {label}")
            self.log(f"  $ {printable}")

        started = time.time()
        try:
            proc = subprocess.run(
                argv, cwd=cwd, env=env, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
        except FileNotFoundError as exc:
            elapsed = time.time() - started
            self.log(f"  !! could not execute: {exc}")
            self.record(label, "ERROR", elapsed, str(exc))
            if gate and gate_id:
                self._record_gate(gate_id, label, "ERROR", str(exc))
            if critical and not self.keep_going:
                self.aborted = True
            return None

        elapsed = time.time() - started
        body = (proc.stdout or "") + (proc.stderr or "")
        for line in body.rstrip("\n").splitlines():
            self.log(f"  | {line}")

        if proc.returncode == 0:
            status = "OK"
        elif gate:
            status = "FAIL"
        else:
            status = "NONZERO"
        self.log(f"  -> exit {proc.returncode} in {elapsed:.2f}s")
        self.record(label, status, elapsed, f"exit {proc.returncode}")
        if gate and gate_id:
            self._record_gate(gate_id, label, status, f"exit {proc.returncode}")

        if proc.returncode != 0 and critical and not self.keep_going:
            self.log("")
            self.log(f"  !! {label} is a prerequisite for every later stage "
                     f"— stopping. Re-run with --keep-going to push past it.")
            self.aborted = True
        return proc

    def mock(self, label, fn):
        """Run one of the four mocked LLM stages."""
        if self.aborted:
            self.record(label, "SKIPPED", 0.0, "aborted earlier")
            return None
        self.log("")
        self.log(f"--- {label}")
        started = time.time()
        try:
            detail = fn()
        except Exception as exc:  # a broken mock shouldn't look like a gate failure
            elapsed = time.time() - started
            self.log(f"  !! mock stage raised: {exc!r}")
            self.record(label, "ERROR", elapsed, repr(exc))
            if not self.keep_going:
                self.aborted = True
            return None
        elapsed = time.time() - started
        self.record(label, "MOCK", elapsed, detail or "")
        self.log(f"  -> {detail}")
        self.log(f"  -> {elapsed:.2f}s")
        return detail

    def gates_failed(self):
        return [r for r in self.results if r[1] in ("FAIL", "ERROR")]

    def table(self):
        self.log.rule("STEP RESULTS")
        width = max(len(r[0]) for r in self.results)
        for label, status, seconds, detail in self.results:
            self.log(f"  {status:<8} {label:<{width}}  {seconds:6.2f}s  {detail}")


def _quote(arg):
    return f'"{arg}"' if " " in arg else arg


def _py_mod(module: str, *args: str) -> list[str]:
    return [sys.executable, "-m", module, *args]


def _artifact_inventory(log, out_dir):
    log.rule("ARTIFACT INVENTORY")
    for root, dirs, files in os.walk(out_dir):
        dirs.sort()
        for name in sorted(files):
            abspath = os.path.join(root, name)
            rel = os.path.relpath(abspath, out_dir).replace(os.sep, "/")
            log(f"  {os.path.getsize(abspath):>9,} B  {rel}")


def _write_certification_and_finish(
    log,
    runner,
    profile,
    repo_path,
    out_dir,
    generative_executor,
    *,
    show_table=True,
    success_lines=None,
    notice_lines=None,
):
    if show_table:
        runner.table()

    report = build_certification_report(
        profile,
        repo_path,
        out_dir,
        stage_records_from_runner_results(runner.results),
        runner.gate_records,
        generative_executor=generative_executor,
    )
    cert_path = write_certification_json(out_dir, report)

    log("")
    if notice_lines:
        for line in notice_lines:
            log(line)
    if report.certified and success_lines:
        for line in success_lines:
            log(line)
    elif not report.certified and not notice_lines:
        failed_gates = [g.id for g in runner.gate_records if g.required and g.status != "ok"]
        failed_stages = [s.name for s in report.stages if s.status != "ok"]
        parts = []
        if failed_stages:
            parts.append(f"stages: {', '.join(failed_stages)}")
        if failed_gates:
            parts.append(f"gates: {', '.join(failed_gates)}")
        log(f"RESULT: certification failed — {'; '.join(parts)}")
    log(f"  certification: {report.certified} -> {cert_path}")
    log(f"Full transcript: {os.path.join(out_dir, 'run.log')}")
    log.close()
    return 1 if not report.certified else 0


def _run_drift_check(log, runner, py, repo_path, manifest, out_dir, args, signals_path):
    if args.skip_drift:
        return
    log.rule("DRIFT CHECK (real) — pre-flight for a future re-run")
    baseline = os.path.abspath(args.prior_signals) if args.prior_signals else signals_path
    if not args.prior_signals:
        log("  note: drift is measured against this run's own scan, so 'no drift' is")
        log("        the expected result — it exercises the script, it doesn't tell")
        log("        you anything about the repo. Use --prior-signals for a real check.")
    runner.run(
        "spring_drift_check",
        _py_mod(
            "doc_engine.tools.spring_drift_check",
            repo_path,
            baseline,
            "--manifest",
            manifest,
            "--out",
            os.path.join(out_dir, "drift_report.json"),
        ),
    )


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
        choices=[p.value for p in ComplianceProfile],
        default=None,
        help="compliance profile: scan_only, deterministic_only, or certified "
             "(default: certified, or value from .doc-engine.yml)",
    )
    ap.add_argument("--deterministic-only", action="store_true",
                    help="shorthand for --compliance-profile deterministic_only")
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


def run_pipeline(args) -> int:
    repo_path = os.path.abspath(args.repo_path)
    if not os.path.isdir(repo_path):
        print(f"error: {repo_path} is not a directory", file=sys.stderr)
        return 2

    repo_config = load_repo_config(repo_path)
    profile = resolve_compliance_profile(repo_config, args)
    skip_signal_scan = bool(args.signals_file)
    strict_citations_effective = (
        profile == ComplianceProfile.CERTIFIED or args.strict_citations
    )

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = args.out_dir or os.path.join(
        os.getcwd(), "local-runs", f"{os.path.basename(repo_path.rstrip(os.sep))}-{stamp}")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    docs_dir = (os.path.join(repo_path, "docs") if args.docs_in_target_repo
                else os.path.join(out_dir, "docs"))
    today = datetime.date.today().isoformat()

    log = Log(os.path.join(out_dir, "run.log"))
    runner = Runner(log, args.keep_going)

    py = sys.executable
    manifest = os.path.join(out_dir, "run_manifest.json")
    signals_path = os.path.join(out_dir, "spring_signals.json")
    preflight_path = os.path.join(out_dir, "capacity_preflight_report.json")

    if args.signals_file:
        signals_src = os.path.abspath(args.signals_file)
        if not os.path.isfile(signals_src):
            print(f"error: --signals-file not found: {signals_src}", file=sys.stderr)
            return 2
        shutil.copy2(signals_src, signals_path)
        log(f"  reused signals: {signals_src} -> {signals_path}")

    log.rule("document-spring-repo — LOCAL END-TO-END RUN")
    log(f"  target repo   : {repo_path}")
    log(f"  artifacts     : {out_dir}")
    log(f"  docs output   : {docs_dir}"
        f"{'  (inside the target repo)' if args.docs_in_target_repo else '  (outside the target repo)'}")
    log(f"  python        : {py}")
    log(f"  compliance    : {profile.value}")
    if args.signals_file:
        log(f"  signals file  : {os.path.abspath(args.signals_file)} (signal_scan skipped)")
    else:
        log(f"  ast-grep      : {shutil.which('ast-grep') or 'NOT ON PATH — the signal scan will fail'}")
    log(f"  mode          : {profile.value}")
    log(f"  date          : {today}")
    log("")
    if profile == ComplianceProfile.SCAN_ONLY:
        log("  Scan-only profile — init_manifest and signal_scan only.")
    elif profile == ComplianceProfile.DETERMINISTIC_ONLY:
        log("  Deterministic stages only — no mocked LLM stages or doc gates.")
    else:
        log("  Stages 1-4 are MOCKED — no model runs. Their artifacts are")
        log("  shape-faithful and their citations resolve, but the prose is")
        log("  templated and documents nothing. Everything else is the real script.")

    pipeline_ctx = PipelineContext(
        repo_path=Path(repo_path),
        out_dir=Path(out_dir),
        manifest_path=Path(manifest),
        docs_dir=Path(docs_dir),
        python=py,
        today=today,
        respect_gitignore=args.respect_gitignore,
        max_tokens=args.max_tokens,
        existing_readme=find_existing_readme(repo_path),
        log=log,
    )

    def _ensure_pool(ctx: PipelineContext):
        if ctx.pool is None and ctx.signals:
            ctx.pool = load_citations(ctx.signals, str(ctx.repo_path))
        return ctx.pool

    def handler_file_summarize(ctx: PipelineContext):
        _ensure_pool(ctx)
        return mock_file_summaries(
            str(ctx.out_dir), ctx.groups, ctx.pool, ctx.edges, log,
        )

    def handler_architect(ctx: PipelineContext):
        _ensure_pool(ctx)
        return mock_architecture(str(ctx.out_dir), ctx.groups, ctx.pool, log)

    def handler_gap(ctx: PipelineContext):
        _ensure_pool(ctx)
        if not ctx.todos:
            hits = sweep_todos(str(ctx.repo_path))
            todo_path = ctx.out_dir / "todo_hits.json"
            _write_json(str(todo_path), hits)
            ctx.todos = hits
        return mock_gap_and_interview(
            str(ctx.out_dir), ctx.pool, ctx.todos, today, log,
        )

    def handler_doc_writer(ctx: PipelineContext):
        _ensure_pool(ctx)
        answers = _read_json(str(ctx.out_dir / "interview_answers.json"))
        readme = ctx.existing_readme or find_existing_readme(str(ctx.repo_path))
        return mock_docs(
            str(ctx.docs_dir), ctx.pool, ctx.todos, answers, today, readme, log,
        )

    mock_executor = MockStageExecutor({
        "file_summarize": handler_file_summarize,
        "architect": handler_architect,
        "gap_analysis_interview": handler_gap,
        "doc_writer": handler_doc_writer,
    })

    all_specs = build_stage_specs()
    until_stage = getattr(args, "until", None)
    try:
        selected_specs = stages_for_profile(
            profile,
            all_specs,
            skip_signal_scan=skip_signal_scan,
            until_stage=until_stage,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if until_stage:
        log(f"  until stage   : {until_stage}")
    deterministic_specs = [s for s in selected_specs if s.kind == StageKind.DETERMINISTIC]
    generative_specs = [s for s in selected_specs if s.kind == StageKind.GENERATIVE]

    log.rule("STAGE 0 — deterministic (PipelineRunner, real scripts)")
    det_runner = PipelineRunner(
        generative_executor=MockStageExecutor({}),
        stages=deterministic_specs,
    )
    det_results = det_runner.run(pipeline_ctx)
    for stage_name, stage_result in det_results:
        status = "OK" if stage_result.success else "FAIL"
        runner.record(
            f"pipeline:{stage_name}",
            status,
            0.0,
            stage_result.detail or stage_result.error or "",
        )
        if not stage_result.success:
            runner.aborted = True

    if runner.aborted:
        return _write_certification_and_finish(
            log, runner, profile, repo_path, out_dir, "none",
            notice_lines=["Run aborted before later stages — see above."],
        )

    if pipeline_ctx.signals is None and os.path.isfile(signals_path):
        pipeline_ctx.signals = _read_json(signals_path)

    if profile != ComplianceProfile.SCAN_ONLY:
        pool = load_citations(pipeline_ctx.signals, repo_path)
        pipeline_ctx.pool = pool
        resolvable = sum(len(v) for v in pool.values())
        log("")
        log(f"  evidence pool: {resolvable} resolvable citation(s) across "
            f"{sum(1 for v in pool.values() if v)} non-empty bucket(s)")
        if pipeline_ctx.groups:
            log(f"  groups: {pipeline_ctx.groups['num_groups']} covering "
                f"{pipeline_ctx.groups['total_files_considered']} file(s)")

    if profile == ComplianceProfile.SCAN_ONLY:
        log.rule("GATES (scan-only)")
        gates.run_gate_via_runner(
            runner,
            "validate_artifacts.py spring_signals (scan-only gate)",
            lambda: (gates.run_validate_spring_signals(signals_path), "OK"),
            gate=True,
            gate_id="validate_artifacts_spring_signals",
        )
        _artifact_inventory(log, out_dir)
        return _write_certification_and_finish(
            log, runner, profile, repo_path, out_dir, "none",
            success_lines=["RESULT: scan-only profile complete."],
        )

    # Deterministic-only profile, or --until truncated before any generative stage.
    if profile == ComplianceProfile.DETERMINISTIC_ONLY or not generative_specs:
        log.rule("GATES (deterministic artifacts)")
        gates.run_gate_via_runner(
            runner,
            "validate_artifacts.py --all (B contract gate)",
            lambda: (gates.run_validate_all_artifacts(out_dir), "OK"),
            gate=True,
            gate_id="validate_artifacts_all",
        )

        log.rule("FINALIZE (real)")
        fin_argv = _py_mod(
            "doc_engine.tools.run_manifest",
            "finalize",
            manifest,
            "--signals-file",
            signals_path,
            "--preflight-file",
            preflight_path,
        )
        runner.run("run_manifest finalize", fin_argv)
        runner.run(
            "run_manifest summary",
            _py_mod("doc_engine.tools.run_manifest", "summary", manifest),
        )

        _run_drift_check(log, runner, py, repo_path, manifest, out_dir, args, signals_path)
        _artifact_inventory(log, out_dir)

        until_note = (
            f" Stopped after --until {until_stage}."
            if until_stage and profile == ComplianceProfile.CERTIFIED
            else ""
        )
        return _write_certification_and_finish(
            log, runner, profile, repo_path, out_dir, "none",
            success_lines=[
                "RESULT: deterministic stages complete. Run generative stages via "
                "Claude Code + document-spring-repo skill for real docs."
                + until_note,
            ],
        )

    log.rule("STAGES 1-4 — MOCKED subagent fan-out (PipelineRunner)")
    gen_runner = PipelineRunner(generative_executor=mock_executor, stages=generative_specs)
    gen_results = gen_runner.run(pipeline_ctx)
    for stage_name, stage_result in gen_results:
        status = "MOCK" if stage_result.success else "FAIL"
        runner.record(
            f"pipeline:{stage_name}",
            status,
            0.0,
            stage_result.detail or stage_result.error or "",
        )
        if not stage_result.success:
            runner.aborted = True

    if runner.aborted:
        return _write_certification_and_finish(
            log, runner, profile, repo_path, out_dir, "mock",
            notice_lines=["Run aborted after generative stage failure — see above."],
        )

    if existing_readme := find_existing_readme(repo_path):
        log("")
        log(f"  note: {existing_readme} already exists in the target repo. A real run "
            f"never overwrites it — the generated overview goes to docs/readme.md.")

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
    if strict_citations_effective:
        cc_argv.append("--strict")
    runner.run(
        "citation_coverage",
        cc_argv,
        gate=strict_citations_effective,
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
        [py, "-m", "pytest", os.path.join(REPO_ROOT, "tests", "doc_engine", "test_pipeline_stages.py"), "-v"],
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
            manifest,
            "--signals-file",
            signals_path,
            "--docs-dir",
            docs_dir,
            "--interview-file",
            os.path.join(out_dir, "interview_answers.json"),
            "--preflight-file",
            preflight_path,
        ),
    )
    runner.run(
        "run_manifest summary",
        _py_mod("doc_engine.tools.run_manifest", "summary", manifest),
    )

    _run_drift_check(log, runner, py, repo_path, manifest, out_dir, args, signals_path)

    _artifact_inventory(log, out_dir)
    if args.docs_in_target_repo:
        log("")
        log(f"  plus the fourteen docs written into {docs_dir}")

    return _write_certification_and_finish(
        log, runner, profile, repo_path, out_dir, "mock",
        success_lines=[
            "RESULT: every gate passed. Remember Stages 1-4 were mocked: this says the "
            "wiring and the checks work, not that any document is correct.",
        ],
    )


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    return run_pipeline(args)


if __name__ == "__main__":
    sys.exit(main())
