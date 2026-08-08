"""Integration — review ingest → SPEC/TASKS → plan-gate → waves → SoD."""

from __future__ import annotations

from pathlib import Path

import pytest

from stf.adapters.gh_handoff import issues_from_tasks, write_handoff_checklist
from stf.ingest.review import findings_to_spec_seed, ingest_review_path
from stf.runners.implement import plan_gate, run_waves
from stf.runners.store import SpecStore, TasksStore, write_change_pack
from stf.schemas.tasks import LedgerState
from stf.__main__ import main as stf_main


def test_pr94_review_ingests_into_spec_seed_and_change_pack(tmp_path: Path) -> None:
    review = Path("docs/reviews/9bc7851_PR_94.md")
    assert review.is_file()
    findings = ingest_review_path(review)
    assert any(f.id == "C1" for f in findings)
    seed = findings_to_spec_seed(findings, target="pr-94-query-surface", source_review=str(review))
    store = SpecStore(tmp_path)
    store.write_spec(seed)
    change = write_change_pack(
        tmp_path,
        added=["C1 containment"],
        modified=["C2 budget"],
        removed=["caller root"],
    )
    assert (change / "delta.json").is_file()
    assert store.load_spec().input_kind == "review_remediation"


def test_cli_seed_validate_plan_gate_and_sod(tmp_path: Path) -> None:
    review = Path("docs/reviews/9bc7851_PR_94.md")
    findings_out = tmp_path / "findings.json"
    assert (
        stf_main(
            [
                "ingest-review",
                "--review",
                str(review),
                "--out",
                str(findings_out),
                "--spec-dir",
                str(tmp_path),
                "--target",
                "pr-94-query-surface",
            ]
        )
        == 0
    )
    assert stf_main(["seed-tasks", "--target-dir", str(tmp_path)]) == 0
    assert stf_main(["validate", "--target-dir", str(tmp_path)]) == 0
    assert stf_main(["plan-gate", "--target-dir", str(tmp_path)]) == 0
    store = TasksStore(tmp_path)
    run_waves(store)
    with pytest.raises(PermissionError):
        store.mark_done(validation_token="forged")
    token = store.issue_validation_token()
    store.mark_done(validation_token=token)
    assert store.load_tasks().ledger == LedgerState.DONE


def test_handoff_checklist_lists_non_t0_tasks(tmp_path: Path) -> None:
    from tests.stf.conftest import write_spec_and_tasks_into

    write_spec_and_tasks_into(tmp_path)
    tasks = TasksStore(tmp_path).load_tasks()
    issues = issues_from_tasks(tasks)
    assert all("T0" not in i["title"] for i in issues)
    path = write_handoff_checklist(tmp_path / "HANDOFF.md", tasks)
    assert "T1" in path.read_text(encoding="utf-8")
