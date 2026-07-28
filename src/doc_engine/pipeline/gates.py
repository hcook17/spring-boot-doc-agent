"""In-process mechanical gate runners for local pipeline orchestration."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
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
    """Run a gate that still lives as a scripts/ CLI entry."""
    proc = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    body = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, body


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
        elapsed = time.time() - started
        runner.log(f"  !! gate raised: {exc!r}")
        runner.record(label, "ERROR", elapsed, repr(exc))
        if gate and gate_id:
            runner._record_gate(gate_id, label, "ERROR", repr(exc))
        if critical and not runner.keep_going:
            runner.aborted = True
        return

    elapsed = time.time() - started
    for line in body.rstrip("\n").splitlines():
        runner.log(f"  | {line}")

    if code == 0:
        status = "OK"
    elif gate:
        status = "FAIL"
    else:
        status = "NONZERO"
    runner.log(f"  -> exit {code} in {elapsed:.2f}s")
    runner.record(label, status, elapsed, f"exit {code}")
    if gate and gate_id:
        runner._record_gate(gate_id, label, status, f"exit {code}")

    if code != 0 and critical and not runner.keep_going:
        runner.aborted = True
