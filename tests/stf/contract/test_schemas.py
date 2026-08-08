"""Contract / schema tests — Pydantic SoR + envelope required keys."""

from __future__ import annotations

import json
from pathlib import Path

from stf.runners.store import SpecStore, TasksStore
from stf.schemas.findings import Finding, FindingSeverity
from tests.stf.conftest import build_minimal_valid_spec, build_minimal_valid_tasks


def test_spec_and_tasks_round_trip_preserves_schema_version(tmp_path: Path) -> None:
    SpecStore(tmp_path).write_spec(build_minimal_valid_spec())
    TasksStore(tmp_path).write_tasks(build_minimal_valid_tasks())
    spec = SpecStore(tmp_path).load_spec()
    tasks = TasksStore(tmp_path).load_tasks()
    assert spec.schema_version == 1
    assert tasks.schema_version == 1
    assert (tmp_path / "SPEC.md").is_file()


def test_finding_contract_rejects_empty_id() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Finding(id="", severity=FindingSeverity.CRITICAL, title="t", claim="c")


def test_pr94_golden_findings_fixture_is_stable_json() -> None:
    path = Path("tests/fixtures/stf/pr94/findings.json")
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) >= 10
    ids = {row["id"] for row in data}
    assert "C1" in ids
    assert "C2" in ids
