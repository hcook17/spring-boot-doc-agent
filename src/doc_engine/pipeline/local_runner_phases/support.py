"""Shared runtime helpers for the local pipeline runner (Log, Runner, finish)."""

from __future__ import annotations

import os
import subprocess
import sys
import time

from doc_engine.core.timeouts import tool_timeout_seconds
from doc_engine.pipeline.compliance import (
    build_certification_report,
    stage_records_from_runner_results,
    write_certification_json,
)

_RUNNER_FAIL_STATUSES = frozenset({"FAIL", "ERROR"})


def _gate_status_from_runner_status(status: str) -> str:
    """Map Runner table status to certification gate status vocabulary."""
    if status == "OK":
        return "ok"
    if status == "SKIPPED":
        return "skipped"
    return "fail"


def _classify_subprocess_status(returncode: int, *, gate: bool) -> str:
    """Map a subprocess exit code to the Runner table status vocabulary."""
    if returncode == 0:
        return "OK"
    if gate:
        return "FAIL"
    return "NONZERO"


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

        self.gate_records.append(
            GateRecord(
                id=gate_id,
                label=label,
                status=_gate_status_from_runner_status(status),
                required=required,
                detail=detail,
            )
        )

    def _maybe_record_gate(self, gate_id, label, status, detail=""):
        if gate_id:
            self._record_gate(gate_id, label, status, detail)

    def _mark_critical_abort(self, label: str) -> None:
        if self.keep_going:
            return
        self.log("")
        self.log(
            f"  !! {label} is a prerequisite for every later stage "
            f"— stopping. Re-run with --keep-going to push past it."
        )
        self.aborted = True

    def _abort_on_critical_spawn_failure(self, *, critical: bool) -> None:
        """Abort silently on spawn failure (no prerequisite banner)."""
        if critical and not self.keep_going:
            self.aborted = True

    def _log_step_header(self, label: str, argv: list[str], *, quiet: bool) -> None:
        printable = " ".join(_quote(arg) for arg in argv)
        if quiet:
            self.log(f"  $ {printable}")
            return
        self.log("")
        self.log(f"--- {label}")
        self.log(f"  $ {printable}")

    def _record_spawn_error(
        self,
        label: str,
        elapsed: float,
        detail: str,
        *,
        gate: bool,
        gate_id: str | None,
        critical: bool,
    ) -> None:
        self.record(label, "ERROR", elapsed, detail)
        if gate:
            self._maybe_record_gate(gate_id, label, "ERROR", detail)
        self._abort_on_critical_spawn_failure(critical=critical)

    def _handle_spawn_exception(
        self,
        label: str,
        started: float,
        timeout: float,
        exc: BaseException,
        *,
        gate: bool,
        gate_id: str | None,
        critical: bool,
    ) -> None:
        elapsed = time.time() - started
        if isinstance(exc, subprocess.TimeoutExpired):
            detail = f"timed out after {timeout}s"
            self.log(f"  !! {detail}: {exc}")
        else:
            detail = str(exc)
            self.log(f"  !! could not execute: {exc}")
        self._record_spawn_error(
            label, elapsed, detail, gate=gate, gate_id=gate_id, critical=critical
        )

    def _spawn_step_process(
        self,
        label: str,
        argv: list[str],
        *,
        cwd,
        env,
        started: float,
        gate: bool,
        gate_id: str | None,
        critical: bool,
    ):
        timeout = tool_timeout_seconds()
        try:
            return subprocess.run(
                argv,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            self._handle_spawn_exception(
                label,
                started,
                timeout,
                exc,
                gate=gate,
                gate_id=gate_id,
                critical=critical,
            )
            return None

    def _echo_process_output(self, proc) -> None:
        body = (proc.stdout or "") + (proc.stderr or "")
        for line in body.rstrip("\n").splitlines():
            self.log(f"  | {line}")

    def _record_step_outcome(
        self,
        label: str,
        status: str,
        elapsed: float,
        returncode: int,
        *,
        gate: bool,
        gate_id: str | None,
    ) -> None:
        detail = f"exit {returncode}"
        self.log(f"  -> exit {returncode} in {elapsed:.2f}s")
        self.record(label, status, elapsed, detail)
        if gate:
            self._maybe_record_gate(gate_id, label, status, detail)

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

        self._log_step_header(label, argv, quiet=quiet)
        started = time.time()
        proc = self._spawn_step_process(
            label,
            argv,
            cwd=cwd,
            env=env,
            started=started,
            gate=gate,
            gate_id=gate_id,
            critical=critical,
        )
        if proc is None:
            return None

        elapsed = time.time() - started
        self._echo_process_output(proc)
        status = _classify_subprocess_status(proc.returncode, gate=gate)
        self._record_step_outcome(
            label, status, elapsed, proc.returncode, gate=gate, gate_id=gate_id
        )
        if proc.returncode != 0 and critical:
            self._mark_critical_abort(label)
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
        return [
            result for result in self.results if result[1] in _RUNNER_FAIL_STATUSES
        ]

    def table(self):
        self.log.rule("STEP RESULTS")
        width = max(len(result[0]) for result in self.results)
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


def _certification_failure_summary(runner, report) -> str:
    failed_gates = [
        gate.id
        for gate in runner.gate_records
        if gate.required and gate.status != "ok"
    ]
    failed_stages = [
        stage.name for stage in report.stages if stage.status != "ok"
    ]
    parts = []
    if failed_stages:
        parts.append(f"stages: {', '.join(failed_stages)}")
    if failed_gates:
        parts.append(f"gates: {', '.join(failed_gates)}")
    return f"RESULT: certification failed — {'; '.join(parts)}"


def _emit_log_lines(log, lines) -> None:
    if not lines:
        return
    for line in lines:
        log(line)


def _emit_certification_outcome(log, runner, report, success_lines, notice_lines) -> None:
    _emit_log_lines(log, notice_lines)
    if report.certified:
        _emit_log_lines(log, success_lines)
        return
    if not notice_lines:
        log(_certification_failure_summary(runner, report))


def _build_and_write_certification(
    runner,
    profile,
    repo_path,
    out_dir,
    generative_executor,
    *,
    allow_mock=False,
):
    report = build_certification_report(
        profile,
        repo_path,
        out_dir,
        stage_records_from_runner_results(runner.results),
        runner.gate_records,
        generative_executor=generative_executor,
        allow_mock=allow_mock,
    )
    cert_path = write_certification_json(out_dir, report)
    return report, cert_path


def _close_certification_log(log, report, cert_path, out_dir) -> None:
    log(f"  certification: {report.certified} -> {cert_path}")
    log(f"Full transcript: {os.path.join(out_dir, 'run.log')}")
    log.close()


def _write_certification_and_finish(
    log,
    runner,
    profile,
    repo_path,
    out_dir,
    generative_executor,
    *,
    allow_mock=False,
    show_table=True,
    success_lines=None,
    notice_lines=None,
):
    if show_table:
        runner.table()

    report, cert_path = _build_and_write_certification(
        runner,
        profile,
        repo_path,
        out_dir,
        generative_executor,
        allow_mock=allow_mock,
    )
    log("")
    _emit_certification_outcome(log, runner, report, success_lines, notice_lines)
    _close_certification_log(log, report, cert_path, out_dir)
    return 0 if report.certified else 1


def _run_drift_check(log, runner, repo_path, manifest, out_dir, args, signals_path):
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
