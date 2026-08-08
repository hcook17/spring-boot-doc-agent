"""Lint results + TASKS/SPEC validators."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from stf.graph.dag import CycleError, compute_waves, detect_cycle
from stf.schemas.spec import SpecDocument
from stf.schemas.tasks import TasksDocument


@dataclass
class LintResult:
    level: str  # PASS | FAIL | WARN
    name: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def lint_tasks_document(
    tasks: TasksDocument,
    spec: SpecDocument | None = None,
    *,
    root: Path | None = None,
) -> list[LintResult]:
    """Validate typed TASKS against contract + optional SPEC inventory."""
    results: list[LintResult] = []

    def check(level: str, name: str, ok: bool, detail: str = "") -> None:
        results.append(LintResult(level if not ok else "PASS", name, detail if not ok else ""))

    check("FAIL", "has task blocks", len(tasks.tasks) >= 1, f"found {len(tasks.tasks)}")
    ids = [t.id for t in tasks.tasks]
    check("FAIL", "T0 pre-flight block", "T0" in ids, "no T0 task")
    check("FAIL", "why-this-order narrative", bool(tasks.why_this_order.strip()))

    depends_map = {t.id: list(t.depends) for t in tasks.tasks}
    cycle = detect_cycle(depends_map)
    check("FAIL", "dag acyclic", cycle is None, f"cycle: {cycle}")

    inventory = spec.inventory_ids() if spec else set()
    known_tasks = set(ids)
    for t in tasks.tasks:
        check("FAIL", f"{t.id} Goal", bool(t.goal.strip()))
        check("FAIL", f"{t.id} Acceptance", bool(t.acceptance.strip()))
        check("FAIL", f"{t.id} has phases", bool(t.tests or t.verify or t.implement))
        for dep in t.depends:
            check(
                "FAIL",
                f"{t.id} depends {dep} exists",
                dep in known_tasks,
                f"unknown dependency {dep}",
            )
        origins = [i.get("origin", "") for i in t.inputs]
        for origin in origins:
            if not origin:
                continue
            if origin.startswith("T") and origin[1:].isdigit():
                check(
                    "FAIL",
                    f"{t.id} input {origin} in depends",
                    origin in t.depends,
                    f"depends={t.depends}",
                )
                check(
                    "FAIL",
                    f"{t.id} input {origin} exists",
                    origin in known_tasks,
                    f"unknown task origin {origin}",
                )
            elif origin.lower() != "new":
                if spec is not None:
                    check(
                        "FAIL",
                        f"{t.id} inventory ID {origin} exists in SPEC",
                        origin in inventory,
                        "cited inventory ID absent from SPEC",
                    )
        # Locate anchors
        if root is not None and t.id != "T0" and t.locate:
            for token in t.locate.replace(",", " ").split():
                if "/" in token or "\\" in token:
                    rel = token.strip("`").replace("\\", "/")
                    if any(rel.endswith(ext) for ext in (".py", ".md", ".json", ".yml", ".yaml", ".java")):
                        fpath = root / rel
                        check("FAIL", f"{t.id} anchor file {rel}", fpath.is_file(), "cited file missing")

    if cycle is None and depends_map:
        try:
            compute_waves(depends_map)
            check("FAIL", "waves computable", True)
        except CycleError as exc:
            check("FAIL", "waves computable", False, str(exc))

    for b in tasks.blockers:
        check("FAIL", f"blocker {b.id} has falsified", bool(b.falsified.strip()))
        check("FAIL", f"blocker {b.id} has class", b.class_ is not None)

    return results


def lint_summary(results: list[LintResult]) -> dict[str, Any]:
    fails = [r for r in results if r.level == "FAIL"]
    warns = [r for r in results if r.level == "WARN"]
    passes = [r for r in results if r.level == "PASS"]
    return {
        "pass": len(passes),
        "fail": len(fails),
        "warn": len(warns),
        "ok": len(fails) == 0,
        "results": [r.to_dict() for r in results],
    }


def mutate_tasks(tasks: TasksDocument, mode: str) -> TasksDocument:
    """Named mutants for lint self-test (ehe _smoke_mutate modes + extras)."""
    data = tasks.model_copy(deep=True)
    if mode == "bad-dep":
        if len(data.tasks) >= 2:
            data.tasks[1].depends = ["T999"]
            data.tasks[1].inputs = [{"origin": "T999", "datum": "bogus"}]
    elif mode == "no-phase":
        if data.tasks:
            data.tasks[0].tests = ""
            data.tasks[0].verify = ""
            data.tasks[0].implement = ""
            data.tasks[0].data_modeling = ""
            data.tasks[0].locate = ""
    elif mode == "bad-inventory":
        if data.tasks:
            data.tasks[-1].inputs = [{"origin": "INV-DOES-NOT-EXIST", "datum": "x"}]
    elif mode == "no-acceptance":
        if data.tasks:
            data.tasks[0].acceptance = ""
    elif mode == "bad-blocker":
        from stf.schemas.blockers import Blocker, BlockerClass

        data.blockers.append(
            Blocker(
                id="B0",
                title="empty",
                falsified="",
                evidence="",
                **{"class": BlockerClass.DECISION},
            )
        )
    elif mode == "cycle":
        if len(data.tasks) >= 2:
            a, b = data.tasks[0].id, data.tasks[1].id
            data.tasks[0].depends = [b]
            data.tasks[1].depends = [a]
    else:
        raise ValueError(f"unknown mutate mode: {mode}")
    return data
