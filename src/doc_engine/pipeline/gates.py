"""In-process mechanical gate runners for local pipeline orchestration."""

from __future__ import annotations

import subprocess
from typing import Callable, Optional

from doc_engine.tools.pipeline_validators import run_stage5_gate
from doc_engine.tools.validate_artifacts import main as validate_artifacts_main


def run_validate_spring_signals(signals_path: str) -> int:
    """Validate a single spring_signals.json artifact."""
    return validate_artifacts_main(["spring_signals", signals_path])


def run_validate_all_artifacts(out_dir: str) -> int:
    """Validate every artifact in a run directory."""
    return validate_artifacts_main(["--all", out_dir])


def run_pipeline_validators(artifacts_dir: str, target_repo: str) -> tuple[int, str]:
    """Run summaries + gap_questions shape gate in-process."""
    failures = run_stage5_gate(artifacts_dir, target_repo)
    if failures:
        return 1, "\n".join(failures)
    return 0, "OK"


def run_subprocess_gate(
    argv: list[str],
    cwd: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
) -> tuple[int, str]:
    """Run a gate via subprocess argv (typically ``python -m doc_engine.tools.*``)."""
    from doc_engine.core.timeouts import tool_timeout_seconds

    timeout = tool_timeout_seconds()
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, f"subprocess timed out after {timeout}s: {exc}"
    body = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, body


def _gate_status_for_code(code: int, gate: bool) -> str:
    """Map a subprocess exit code to Runner status vocabulary."""
    if code == 0:
        return "OK"
    if gate:
        return "FAIL"
    return "NONZERO"


def _record_gate_outcome(
    runner,
    label: str,
    code: int,
    elapsed: float,
    *,
    gate: bool,
    gate_id: Optional[str],
    critical: bool,
) -> None:
    """Log, record, and optionally abort after a completed gate call."""
    status = _gate_status_for_code(code, gate)
    runner.log(f"  -> exit {code} in {elapsed:.2f}s")
    runner.record(label, status, elapsed, f"exit {code}")
    if gate and gate_id:
        runner._record_gate(gate_id, label, status, f"exit {code}")
    if code != 0 and critical and not runner.keep_going:
        runner.aborted = True


def _record_gate_exception(
    runner,
    label: str,
    exc: Exception,
    elapsed: float,
    *,
    gate: bool,
    gate_id: Optional[str],
    critical: bool,
) -> None:
    """Log and record a gate that raised instead of returning a code."""
    runner.log(f"  !! gate raised: {exc!r}")
    runner.record(label, "ERROR", elapsed, repr(exc))
    if gate and gate_id:
        runner._record_gate(gate_id, label, "ERROR", repr(exc))
    if critical and not runner.keep_going:
        runner.aborted = True


def run_gate_via_runner(
    runner,
    label: str,
    run_fn: Callable[[], tuple[int, str]],
    gate: bool = False,
    gate_id: Optional[str] = None,
    critical: bool = False,
) -> None:
    """Execute an in-process gate through local_runner.Runner bookkeeping."""
    if runner.aborted:
        runner.record(label, "SKIPPED", 0.0, "aborted earlier")
        return

    runner.log("")
    runner.log(f"--- {label}")
    import time

    started = time.time()
    try:
        code, body = run_fn()
    except Exception as exc:
        _record_gate_exception(
            runner,
            label,
            exc,
            time.time() - started,
            gate=gate,
            gate_id=gate_id,
            critical=critical,
        )
        return

    for line in body.rstrip("\n").splitlines():
        runner.log(f"  | {line}")
    _record_gate_outcome(
        runner,
        label,
        code,
        time.time() - started,
        gate=gate,
        gate_id=gate_id,
        critical=critical,
    )
