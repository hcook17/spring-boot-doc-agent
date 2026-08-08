"""Unit coverage for remaining ``stf`` CLI subcommands."""

from __future__ import annotations

from pathlib import Path

import pytest

from stf.__main__ import main as stf_main
from tests.stf.conftest import write_spec_and_tasks_into


def test_plan_gate_exception_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_spec_and_tasks_into(tmp_path)

    def boom(*_args, **_kwargs):
        raise RuntimeError("plan exploded")

    monkeypatch.setattr("stf.__main__.plan_gate", boom)
    assert stf_main(["plan-gate", "--target-dir", str(tmp_path)]) == 1


def test_reviewer_token_mark_done_and_forged(tmp_path: Path) -> None:
    write_spec_and_tasks_into(tmp_path)
    assert stf_main(["reviewer-token", "--target-dir", str(tmp_path)]) == 0
    assert stf_main(["mark-done", "--target-dir", str(tmp_path), "--token", "forged"]) == 1

    # Re-issue after forged attempt still works.
    from stf.runners.store import TasksStore

    token = TasksStore(tmp_path).issue_validation_token()
    assert stf_main(["mark-done", "--target-dir", str(tmp_path), "--token", token]) == 0


def test_handoff_checklist_and_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_spec_and_tasks_into(tmp_path)
    checklist = tmp_path / "HANDOFF.md"
    assert (
        stf_main(
            [
                "handoff-gh",
                "--target-dir",
                str(tmp_path),
                "--checklist",
                str(checklist),
            ]
        )
        == 0
    )
    assert checklist.is_file()

    monkeypatch.setattr(
        "stf.__main__.handoff_gh",
        lambda tasks, dry_run=True: {"dry_run": dry_run, "issues": 1},
    )
    assert stf_main(["handoff-gh", "--target-dir", str(tmp_path)]) == 0


def test_constitution_and_mutate(tmp_path: Path) -> None:
    write_spec_and_tasks_into(tmp_path)
    out = tmp_path / "constitution.md"
    assert (
        stf_main(
            [
                "constitution",
                "--repo-root",
                str(Path.cwd()),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    assert out.is_file()
    assert out.stat().st_size > 0

    # Mutants are expected to fail lint → CLI returns 0 when lint_ok is False.
    assert stf_main(["mutate", "--target-dir", str(tmp_path), "--mode", "no-acceptance"]) == 0


def test_verify_gate_success_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "stf.__main__.verify_gate",
        lambda verify_commands=None: {"ok": True, "cmds": verify_commands or []},
    )
    assert stf_main(["verify-gate"]) == 0

    def boom(*, verify_commands=None):
        raise RuntimeError("verify failed")

    monkeypatch.setattr("stf.__main__.verify_gate", boom)
    assert stf_main(["verify-gate", "--cmd", "true"]) == 1


def test_implement_with_mocked_waves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_spec_and_tasks_into(tmp_path)
    monkeypatch.setattr(
        "stf.__main__.run_waves",
        lambda store, start_wave=0: {"waves": 1, "start_wave": start_wave},
    )
    monkeypatch.setattr("stf.__main__.plan_gate", lambda *_args, **_kwargs: {"waves": []})
    assert (
        stf_main(
            [
                "implement",
                "--target-dir",
                str(tmp_path),
                "--plan-gate",
                "--resume-wave",
                "0",
            ]
        )
        == 0
    )
