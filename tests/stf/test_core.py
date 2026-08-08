"""STF unit + mutation + property-style tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stf.graph.dag import CycleError, blast_radius, compute_waves, detect_cycle
from stf.ingest.review import findings_to_spec_seed, ingest_review_markdown
from stf.runners.implement import plan_gate, run_waves
from stf.runners.store import SpecStore, TasksStore
from stf.schemas.blockers import BlockerClass
from stf.schemas.spec import DataSourceRow, SpecDocument
from stf.schemas.tasks import LedgerState, TaskBlock, TasksDocument
from stf.validators.lint_tasks import lint_summary, lint_tasks_document, mutate_tasks

MODES = ("bad-dep", "no-phase", "bad-inventory", "no-acceptance", "bad-blocker", "cycle")


def _sample_tasks() -> TasksDocument:
    return TasksDocument(
        target="demo",
        source_spec="specs/demo/SPEC.md",
        why_this_order="T0 then T1",
        tasks=[
            TaskBlock(
                id="T0",
                title="probe",
                goal="probe",
                inputs=[{"origin": "new", "datum": "x"}],
                depends=[],
                tests="baseline",
                verify="pytest -q",
                acceptance="baseline recorded",
                implement="n/a",
                locate="n/a",
            ),
            TaskBlock(
                id="T1",
                title="fix",
                goal="fix thing",
                inputs=[{"origin": "INV-C1", "datum": "containment"}],
                depends=["T0"],
                tests="test_c1",
                verify="pytest -k c1",
                acceptance="C1 closed",
                implement="pin root",
                locate="src/doc_engine/query/load.py",
            ),
        ],
    )


def _sample_spec() -> SpecDocument:
    return SpecDocument(
        target="demo",
        goal="demo",
        inventory=[DataSourceRow(id="INV-C1", data_need="root", origin="src/doc_engine/query/load.py")],
        finding_ids=["C1"],
    )


def test_compute_waves_diamond():
    waves = compute_waves({"T0": [], "T1": ["T0"], "T2": ["T0"], "T3": ["T1", "T2"]})
    assert waves[0] == ["T0"]
    assert set(waves[1]) == {"T1", "T2"}
    assert waves[2] == ["T3"]


def test_detect_cycle():
    assert detect_cycle({"A": ["B"], "B": ["A"]}) is not None
    with pytest.raises(CycleError):
        compute_waves({"A": ["B"], "B": ["A"]})


def test_blast_radius_bfs():
    radius = blast_radius(
        ["T1"],
        depends={"T0": [], "T1": ["T0"], "T2": ["T1"], "T3": ["T2"]},
        inputs_origins={"T2": ["T1"], "T3": ["T2"]},
    )
    assert radius == ["T1", "T2", "T3"]


def test_lint_passes_on_sample():
    summary = lint_summary(lint_tasks_document(_sample_tasks(), _sample_spec()))
    assert summary["ok"]


@pytest.mark.parametrize("mode", MODES)
def test_named_mutants_fail_lint(mode: str):
    mutated = mutate_tasks(_sample_tasks(), mode)
    summary = lint_summary(lint_tasks_document(mutated, _sample_spec()))
    assert not summary["ok"], f"mutant {mode} should fail lint"


def test_sod_cannot_self_approve(tmp_path: Path):
    store = TasksStore(tmp_path)
    store.write_tasks(_sample_tasks())
    with pytest.raises(PermissionError):
        store.mark_done(validation_token="wrong")
    token = store.issue_validation_token()
    store.mark_done(validation_token=token)
    assert store.load_tasks().ledger == LedgerState.DONE


def test_plan_gate_and_waves(tmp_path: Path):
    SpecStore(tmp_path).write_spec(_sample_spec())
    store = TasksStore(tmp_path)
    store.write_tasks(_sample_tasks())
    result = plan_gate(store.load_tasks(), _sample_spec())
    assert result["ok"]
    ran = run_waves(store)
    assert "T0" in ran["executed"]


def test_ingest_review_headings():
    md = """
### C1 — Arbitrary file read

**Severity: Critical**

Containment is opt-in in `src/doc_engine/query/load.py`.

### H2 — RedactionProvider dead

**Severity: High**

Dict zones in `src/doc_engine/query/providers.py`.
"""
    findings = ingest_review_markdown(md, source_doc="docs/reviews/x.md")
    ids = {f.id for f in findings}
    assert "C1" in ids
    assert "H2" in ids
    assert findings[0].links
    seed = findings_to_spec_seed(findings, target="pr-94-query-surface")
    assert seed.input_kind == "review_remediation"
    assert any(r.id.startswith("INV-C1") for r in seed.inventory)


def test_schema_roundtrip(tmp_path: Path):
    store = SpecStore(tmp_path)
    store.write_spec(_sample_spec())
    loaded = store.load_spec()
    assert loaded.target == "demo"
    assert (tmp_path / "SPEC.md").is_file()


def test_property_wave_partition_covers_all_tasks():
    # property-style without hypothesis dependency
    graphs = [
        {"T0": [], "T1": ["T0"], "T2": ["T1"]},
        {"T0": [], "T1": [], "T2": ["T0", "T1"]},
        {"A": [], "B": ["A"], "C": ["A"], "D": ["B", "C"]},
    ]
    for g in graphs:
        waves = compute_waves(g)
        flat = [t for w in waves for t in w]
        assert sorted(flat) == sorted(g)
        # within a wave, no internal depends
        for w in waves:
            for tid in w:
                assert all(d not in w for d in g[tid])
