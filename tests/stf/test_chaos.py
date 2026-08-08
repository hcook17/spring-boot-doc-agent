"""Chaos / poison / mid-write consistency."""

from __future__ import annotations

from pathlib import Path

import pytest

from stf.runners.store import TasksStore
from stf.schemas.tasks import TaskBlock, TasksDocument
from stf.validators.lint_tasks import lint_summary, lint_tasks_document


def test_poison_json_fails_closed(tmp_path: Path):
    from pydantic import ValidationError

    p = tmp_path / "TASKS.json"
    p.write_text("{not json", encoding="utf-8")
    store = TasksStore(tmp_path)
    with pytest.raises(ValidationError):
        store.load_tasks()


def test_mid_write_atomic_replace(tmp_path: Path):
    store = TasksStore(tmp_path)
    doc = TasksDocument(
        target="x",
        source_spec="s",
        why_this_order="because",
        tasks=[
            TaskBlock(
                id="T0",
                title="t",
                goal="g",
                acceptance="a",
                tests="t",
                verify="v",
                implement="i",
            )
        ],
    )
    store.write_tasks(doc)
    assert not list(tmp_path.glob("*.tmp"))
    assert store.load_tasks().target == "x"


def test_open_blocker_reentry_checkpoint(tmp_path: Path):
    from stf.runners.implement import append_blocker
    from stf.schemas.blockers import BlockerClass
    from stf.schemas.tasks import LedgerState

    store = TasksStore(tmp_path)
    store.write_tasks(
        TasksDocument(
            target="x",
            source_spec="s",
            why_this_order="order",
            tasks=[
                TaskBlock(id="T0", title="t0", goal="g", acceptance="a", tests="t", verify="v", implement="i"),
                TaskBlock(
                    id="T1",
                    title="t1",
                    goal="g",
                    acceptance="a",
                    tests="t",
                    verify="v",
                    implement="i",
                    depends=["T0"],
                    inputs=[{"origin": "T0", "datum": "x"}],
                ),
            ],
            resume_wave=1,
        )
    )
    b = append_blocker(
        store,
        title="drift",
        falsified="inventory",
        evidence="probe",
        class_=BlockerClass.INVENTORY_DRIFT,
        falsified_tasks=["T0"],
    )
    cp = store.checkpoint()
    assert b.id in [x.id for x in store.load_tasks().open_blockers()]
    assert cp["ledger"] == LedgerState.STALL.value
    assert "T1" in b.blast_radius_tasks
