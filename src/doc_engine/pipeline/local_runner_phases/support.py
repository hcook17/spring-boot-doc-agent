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
        timeout = tool_timeout_seconds()
        try:
            proc = subprocess.run(
                argv, cwd=cwd, env=env, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=timeout,
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
        except subprocess.TimeoutExpired as exc:
            elapsed = time.time() - started
            detail = f"timed out after {timeout}s"
            self.log(f"  !! {detail}: {exc}")
            self.record(label, "ERROR", elapsed, detail)
            if gate and gate_id:
                self._record_gate(gate_id, label, "ERROR", detail)
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
    allow_mock=False,
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
        allow_mock=allow_mock,
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
