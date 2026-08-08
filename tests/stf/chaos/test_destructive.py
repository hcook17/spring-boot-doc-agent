"""Chaos / destructive / concurrent — fail closed, stay consistent."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from stf.graph.dag import compute_waves
from stf.runners.implement import append_blocker, run_waves
from stf.runners.store import TasksStore
from stf.schemas.blockers import BlockerClass
from stf.schemas.tasks import LedgerState
from tests.stf.conftest import build_minimal_valid_tasks, write_spec_and_tasks_into


def test_poison_tasks_json_fails_closed(tmp_path: Path) -> None:
    from pydantic import ValidationError

    (tmp_path / "TASKS.json").write_text("{not-json", encoding="utf-8")
    store = TasksStore(tmp_path)
    with pytest.raises(ValidationError):
        store.load_tasks()


def test_atomic_write_leaves_no_tmp_files(tmp_path: Path) -> None:
    write_spec_and_tasks_into(tmp_path)
    assert list(tmp_path.glob("*.tmp")) == []


def test_open_blocker_stalls_ledger_and_records_blast_radius(tmp_path: Path) -> None:
    write_spec_and_tasks_into(tmp_path)
    store = TasksStore(tmp_path)
    blocker = append_blocker(
        store,
        title="inventory drifted",
        falsified="INV-C1 path moved",
        evidence="probe",
        class_=BlockerClass.INVENTORY_DRIFT,
        falsified_tasks=["T0"],
    )
    assert store.load_tasks().ledger == LedgerState.STALL
    assert "T1" in blocker.blast_radius_tasks


def test_concurrent_wave_computation_is_deterministic() -> None:
    graph = {"T0": [], "T1": ["T0"], "T2": ["T0"], "T3": ["T1", "T2"]}

    def _once() -> list[list[str]]:
        return compute_waves(graph)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _once(), range(32)))
    assert all(r == results[0] for r in results)


def test_run_waves_is_idempotent_when_resuming_past_end(tmp_path: Path) -> None:
    write_spec_and_tasks_into(tmp_path)
    store = TasksStore(tmp_path)
    first = run_waves(store)
    second = run_waves(store, start_wave=99)
    assert first["executed"]
    assert second["executed"] == []
