"""Unit coverage for in-process gate runners (no subprocess tooling required)."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from doc_engine.pipeline import gates


class FakeRunner:
    """Minimal stand-in for local_runner.Runner used by gate helpers."""

    def __init__(self, *, aborted: bool = False, keep_going: bool = False) -> None:
        self.aborted = aborted
        self.keep_going = keep_going
        self.records: list[tuple[str, str, float, str]] = []
        self.gate_records: list[tuple[str, str, str, str]] = []
        self.logs: list[str] = []

    def log(self, message: str) -> None:
        self.logs.append(message)

    def record(self, label: str, status: str, elapsed: float, detail: str) -> None:
        self.records.append((label, status, elapsed, detail))

    def _record_gate(self, gate_id: str, label: str, status: str, detail: str) -> None:
        self.gate_records.append((gate_id, label, status, detail))


def test_run_pipeline_validators_joins_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gates, "run_stage5_gate", lambda *_args, **_kwargs: ["a", "b"])
    code, body = gates.run_pipeline_validators("arts", "repo")
    assert code == 1
    assert body == "a\nb"


def test_run_pipeline_validators_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gates, "run_stage5_gate", lambda *_args, **_kwargs: [])
    assert gates.run_pipeline_validators("arts", "repo") == (0, "OK")


def test_run_subprocess_gate_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["x"], timeout=1)

    monkeypatch.setattr(gates.subprocess, "run", boom)
    monkeypatch.setattr(
        "doc_engine.core.timeouts.tool_timeout_seconds",
        lambda: 1,
    )
    code, body = gates.run_subprocess_gate(["python", "-c", "pass"])
    assert code == 124
    assert "timed out" in body


def test_run_gate_via_runner_skips_when_aborted() -> None:
    runner = FakeRunner(aborted=True)
    gates.run_gate_via_runner(runner, "g", lambda: (0, "OK"), gate=True, gate_id="g1")
    assert runner.records == [("g", "SKIPPED", 0.0, "aborted earlier")]
    assert runner.gate_records == []


def test_run_gate_via_runner_records_error_and_aborts() -> None:
    runner = FakeRunner(keep_going=False)

    def boom() -> tuple[int, str]:
        raise RuntimeError("nope")

    gates.run_gate_via_runner(
        runner, "g", boom, gate=True, gate_id="g1", critical=True,
    )
    assert runner.aborted is True
    assert runner.records[0][1] == "ERROR"
    assert runner.gate_records[0][:3] == ("g1", "g", "ERROR")


def test_run_gate_via_runner_fail_vs_nonzero() -> None:
    runner = FakeRunner()
    gates.run_gate_via_runner(runner, "gatey", lambda: (2, "bad"), gate=True, gate_id="gid")
    assert runner.records[0][1] == "FAIL"
    assert runner.gate_records[0][2] == "FAIL"

    soft_runner = FakeRunner()
    gates.run_gate_via_runner(soft_runner, "soft", lambda: (3, "bad"), gate=False)
    assert soft_runner.records[0][1] == "NONZERO"
    assert soft_runner.gate_records == []


def test_run_gate_via_runner_ok_path() -> None:
    runner = FakeRunner()
    gates.run_gate_via_runner(
        runner, "okgate", lambda: (0, "line1\nline2"), gate=True, gate_id="id",
    )
    assert runner.records[0][1] == "OK"
    assert any("| line1" in line for line in runner.logs)
