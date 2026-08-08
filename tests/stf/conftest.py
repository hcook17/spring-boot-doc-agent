"""Spoken-language helpers shared across STF TDD suites."""

from __future__ import annotations

from pathlib import Path

import pytest

from stf.schemas.spec import DataSourceRow, SpecDocument
from stf.schemas.tasks import TaskBlock, TasksDocument


def build_minimal_valid_spec(*, target: str = "demo") -> SpecDocument:
    return SpecDocument(
        target=target,
        goal="demonstrate remediation packing",
        inventory=[
            DataSourceRow(
                id="INV-C1",
                data_need="mandatory containment root",
                origin="src/doc_engine/query/load.py",
            )
        ],
        finding_ids=["C1"],
        critical_assumptions=["MCP root is server-derived"],
        input_kind="review_remediation",
    )


def build_minimal_valid_tasks(*, target: str = "demo") -> TasksDocument:
    return TasksDocument(
        target=target,
        source_spec=f"specs/{target}/SPEC.md",
        why_this_order="T0 probes first; T1 remediates containment after probes pass",
        tasks=[
            TaskBlock(
                id="T0",
                title="probe containment",
                goal="reproduce C1 fail-closed behavior",
                inputs=[{"origin": "new", "datum": "probe harness"}],
                depends=[],
                tests="assert QueryPathError without root",
                verify="python -m pytest tests/doc_engine/query_tdd -q -k containment",
                acceptance="missing root raises QueryPathError",
                implement="n/a — probe",
                locate="n/a",
                data_modeling="n/a",
            ),
            TaskBlock(
                id="T1",
                title="fix containment",
                goal="pin server-derived root",
                inputs=[{"origin": "INV-C1", "datum": "containment"}],
                depends=["T0"],
                tests="dispatch_tool without root fails closed",
                verify="python -m pytest tests/doc_engine/query_tdd -q -k mcp_root",
                acceptance="C1 closed",
                implement="require_server_root in mcp_tools",
                locate="src/doc_engine/query/load.py",
                data_modeling="n/a",
            ),
        ],
    )


def write_spec_and_tasks_into(directory: Path) -> Path:
    from stf.runners.store import SpecStore, TasksStore

    directory.mkdir(parents=True, exist_ok=True)
    SpecStore(directory).write_spec(build_minimal_valid_spec(target=directory.name))
    TasksStore(directory).write_tasks(build_minimal_valid_tasks(target=directory.name))
    return directory


@pytest.fixture
def minimal_spec() -> SpecDocument:
    return build_minimal_valid_spec()


@pytest.fixture
def minimal_tasks() -> TasksDocument:
    return build_minimal_valid_tasks()
