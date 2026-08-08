"""Decompose ANSWER-KEY auto-scorer + transcript metrics stub."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stf.schemas.tasks import TasksDocument
from stf.validators.lint_tasks import lint_summary, lint_tasks_document


def score_decompose(
    tasks: TasksDocument,
    answer_key: dict[str, Any],
    *,
    spec=None,
) -> dict[str, Any]:
    """Score against ANSWER-KEY dimensions (G1/G2/C1/T0/lint)."""
    lint = lint_summary(lint_tasks_document(tasks, spec))
    scores = {
        "lint_pass": 1.0 if lint["ok"] else 0.0,
        "T0": 1.0 if any(t.id == "T0" for t in tasks.tasks) else 0.0,
    }
    must_ids = set(answer_key.get("required_task_titles_substrings") or [])
    titles = " ".join(t.title.lower() for t in tasks.tasks)
    g1 = sum(1 for s in must_ids if s.lower() in titles)
    scores["G1"] = g1 / max(1, len(must_ids)) if must_ids else 1.0

    must_inv = set(answer_key.get("required_inventory_ids") or [])
    cited = {i.get("origin") for t in tasks.tasks for i in t.inputs}
    g2 = sum(1 for i in must_inv if i in cited)
    scores["G2"] = g2 / max(1, len(must_inv)) if must_inv else 1.0

    conflict = answer_key.get("must_surface_conflict")
    if conflict:
        blob = json.dumps(tasks.model_dump()).lower()
        scores["C1"] = 1.0 if str(conflict).lower() in blob else 0.0
    else:
        scores["C1"] = 1.0

    total = sum(scores.values()) / len(scores)
    threshold = float(answer_key.get("threshold", 0.8))
    return {"scores": scores, "total": total, "pass": total >= threshold, "lint": lint}


def load_answer_key(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def estimate_main_context_peak(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Stub Cursor/Claude transcript metrics (ehe context_metrics ideas)."""
    peaks = [int(e.get("main_ctx") or 0) for e in events]
    tool_kb = sum(float(e.get("tool_result_kb") or 0) for e in events)
    return {
        "peak_main_ctx": max(peaks) if peaks else 0,
        "main_tool_result_kb": tool_kb,
        "events": len(events),
        "kpi": "peak_main_ctx should drop when fan-out delegates tool bulk",
    }
