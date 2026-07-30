"""Tests for doc_engine.paths."""

from pathlib import Path

from doc_engine.paths import (
    ast_grep_rules_path,
    codeql_dir,
    repo_root,
    schemas_dir,
    scripts_dir,
)


def test_repo_root_contains_pyproject():
    root = repo_root()
    assert (root / "pyproject.toml").is_file()


def test_scripts_dir_under_repo_root():
    root = repo_root()
    scripts = scripts_dir()
    assert scripts.is_dir()
    assert scripts.parent == root


def test_schemas_dir_exists():
    assert schemas_dir().is_dir()


def test_ast_grep_rules_path_exists():
    assert ast_grep_rules_path().is_file()


def test_codeql_dir_exists():
    assert codeql_dir().is_dir()
