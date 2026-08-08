"""Security / penetration-style — containment, SoD, path escape."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from doc_engine.query.load import QueryPathError, load_json, require_server_root
from doc_engine.query.mcp_tools import dispatch_tool
from stf.runners.store import TasksStore
from tests.stf.conftest import write_spec_and_tasks_into


def test_require_server_root_fails_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOC_ENGINE_ROOT", raising=False)
    monkeypatch.delenv("DOC_ENGINE_RUN_DIR", raising=False)
    with pytest.raises(QueryPathError):
        require_server_root()


def test_dispatch_tool_never_honors_caller_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOC_ENGINE_ROOT", str(tmp_path))
    outside = tmp_path.parent / "secret.json"
    # If parent write fails, skip
    try:
        outside.write_text("{}", encoding="utf-8")
    except OSError:
        pytest.skip("cannot write outside tmp")
    with pytest.raises((QueryPathError, KeyError, Exception)):
        dispatch_tool(
            "query_facts",
            {"facts": str(outside), "root": str(tmp_path.parent)},
        )


def test_load_json_refuses_path_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "run"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(QueryPathError):
        load_json(outside, root=root)


def test_implement_cannot_self_approve_done(tmp_path: Path) -> None:
    write_spec_and_tasks_into(tmp_path)
    store = TasksStore(tmp_path)
    with pytest.raises(PermissionError):
        store.mark_done(validation_token="self-issued")
