"""ANSWER-KEY auto-score."""

from stf.eval.scoring import score_decompose
from stf.schemas.spec import DataSourceRow, SpecDocument
from stf.schemas.tasks import TaskBlock, TasksDocument
from stf.eval.scoring import load_answer_key
from pathlib import Path


def test_score_decompose_pass():
    key = {
        "required_task_titles_substrings": ["probe", "fix"],
        "required_inventory_ids": ["INV-C1"],
        "threshold": 0.8,
    }
    tasks = TasksDocument(
        target="d",
        source_spec="s",
        why_this_order="o",
        tasks=[
            TaskBlock(id="T0", title="probe", goal="g", acceptance="a", tests="t", verify="v", implement="i"),
            TaskBlock(
                id="T1",
                title="fix containment",
                goal="g",
                acceptance="a",
                tests="t",
                verify="v",
                implement="i",
                depends=["T0"],
                inputs=[{"origin": "INV-C1", "datum": "x"}],
            ),
        ],
    )
    spec = SpecDocument(
        target="d",
        goal="g",
        inventory=[DataSourceRow(id="INV-C1", data_need="n", origin="o")],
    )
    result = score_decompose(tasks, key, spec=spec)
    assert result["pass"]
