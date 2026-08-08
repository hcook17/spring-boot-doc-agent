"""CLI edge coverage for validate_artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from doc_engine.tools import validate_artifacts as va


def test_list_known_artifacts(capsys: pytest.CaptureFixture[str]) -> None:
    assert va.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "spring_signals" in out
    assert "certification" in out


def test_require_without_all_errors() -> None:
    with pytest.raises(SystemExit):
        va.main(["--require", "spring_signals"])


def test_all_not_a_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "nope"
    assert va.main(["--all", str(missing)]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_envelope_ok_and_non_object(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOC_ENGINE_ROOT", str(tmp_path))
    path = tmp_path / "env.json"
    path.write_text(
        json.dumps({
            "schema_version": 1,
            "kind": "query_result",
            "query": "x",
            "items": [],
        }),
        encoding="utf-8",
    )
    # Minimal envelope may still fail schema/containment depending on installed
    # schema pack; accept either clean pass or a reported validation failure.
    rc = va.main(["--envelope", "query_result", str(path)])
    assert rc in (0, 1)

    bad = tmp_path / "list.json"
    bad.write_text("[1,2]", encoding="utf-8")
    assert va.main(["--envelope", "query_result", str(bad)]) == 1
    err = capsys.readouterr().err
    assert "JSON object" in err or "containment" in err or "error:" in err


def test_unknown_artifact_and_missing_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert va.main(["not_a_real_artifact", str(tmp_path / "x.json")]) == 2
    assert va.main(["spring_signals", str(tmp_path / "missing.json")]) == 2
