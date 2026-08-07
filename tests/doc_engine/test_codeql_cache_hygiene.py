"""CodeQL results-cache hygiene: user-owned dir, no symlink hijack."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from doc_engine.scanning.support import _codeql_runner as runner


def test_cache_dir_under_xdg_and_chmod(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    cache = runner._cache_dir()
    assert cache == tmp_path / "xdg" / "doc-engine" / "codeql-cache"
    assert cache.is_dir()
    assert not cache.is_symlink()


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_cache_dir_refuses_symlink_root(tmp_path: Path, monkeypatch):
    real = tmp_path / "real-cache"
    real.mkdir()
    link = tmp_path / "xdg" / "doc-engine" / "codeql-cache"
    link.parent.mkdir(parents=True)
    try:
        os.symlink(real, link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation failed: {exc}")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    with pytest.raises(runner.CodeQLError, match="symlink"):
        runner._cache_dir()


def test_ensure_regular_file_rejects_symlink(tmp_path: Path):
    target = tmp_path / "payload.json"
    target.write_text("[]", encoding="utf-8")
    link = tmp_path / "cache.json"
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks unavailable")
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"symlink creation failed: {exc}")
    with pytest.raises(runner.CodeQLError, match="non-regular"):
        runner._ensure_regular_file(link)


def test_validate_cached_rows_rejects_non_list():
    with pytest.raises(runner.CodeQLError):
        runner._validate_cached_evidence_rows({"file": "a.java"})


def test_validate_cached_rows_rejects_missing_file():
    with pytest.raises(runner.CodeQLError):
        runner._validate_cached_evidence_rows([{"line": 1}])


def test_cache_key_includes_cli_version(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "A.java").write_text("class A {}", encoding="utf-8")
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "q.ql").write_text("// q", encoding="utf-8")
    k1 = runner._cache_key(repo, pack, "gradlew compileJava", codeql_cli_version="2.0.0")
    k2 = runner._cache_key(repo, pack, "gradlew compileJava", codeql_cli_version="2.1.0")
    assert k1 != k2
