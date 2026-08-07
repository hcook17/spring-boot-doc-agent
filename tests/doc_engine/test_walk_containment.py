"""Symlink containment for untrusted repository walks."""

import os
from pathlib import Path

import pytest

from doc_engine.core.context import ScanContext
from doc_engine.core.walk import is_path_inside_root


def test_is_path_inside_root_accepts_nested_file(tmp_path: Path):
    nested = tmp_path / "src" / "A.java"
    nested.parent.mkdir()
    nested.write_text("class A {}", encoding="utf-8")
    assert is_path_inside_root(str(nested), str(tmp_path)) is True


def test_is_path_inside_root_rejects_sibling(tmp_path: Path):
    outside = tmp_path / "secret.env"
    outside.write_text("AWS_SECRET=1\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    assert is_path_inside_root(str(outside), str(repo)) is False


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_scan_context_skips_escaping_file_symlink(tmp_path: Path):
    outside = tmp_path / "outside.env"
    outside.write_text("password=hunter2\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ok.txt").write_text("ok\n", encoding="utf-8")
    link = repo / "leaked.env"
    try:
        os.symlink(outside, link)
    except OSError as exc:
        pytest.skip(f"symlink creation failed: {exc}")

    ctx = ScanContext.build(str(repo))
    assert "ok.txt" in ctx.file_signatures
    assert "leaked.env" not in ctx.file_signatures
    assert all(e.rel_path != "leaked.env" for e in ctx.non_java_files)
