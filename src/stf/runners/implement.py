"""Plan/verify gates + wave runner (SPOQ semantics)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from stf.graph.dag import assign_waves_to_tasks, blast_radius, compute_waves
from stf.runners.store import TasksStore
from stf.schemas.blockers import Blocker, BlockerClass, BlockerStatus
from stf.schemas.spec import SpecDocument
from stf.schemas.tasks import LedgerState, TasksDocument
from stf.validators.lint_tasks import lint_summary, lint_tasks_document

MAX_CONCURRENT = 4


class PlanGateError(RuntimeError):
    pass


class VerifyGateError(RuntimeError):
    pass


def plan_gate(tasks: TasksDocument, spec: SpecDocument | None = None) -> dict:
    """Dual gate #1 — before Wave 1 execution."""
    results = lint_tasks_document(tasks, spec)
    summary = lint_summary(results)
    if not summary["ok"]:
        raise PlanGateError(f"plan gate failed: {summary['fail']} FAIL(s)")
    depends = {t.id: t.depends for t in tasks.tasks}
    waves = compute_waves(depends)
    finding_coverage = True
    if spec and spec.finding_ids:
        # At least one task should reference inventory for critical findings
        inv_cited = {i.get("origin") for t in tasks.tasks for i in t.inputs}
        finding_coverage = any(f"INV-{fid}" in inv_cited for fid in spec.finding_ids if fid.startswith("C"))
    return {"ok": True, "waves": waves, "finding_coverage": finding_coverage, "lint": summary}


def verify_gate(
    *,
    verify_commands: list[str],
    runner: Callable[[str], int] | None = None,
) -> dict:
    """Dual gate #2 — Verify cmds must exit 0 (or dry-run)."""
    if runner is None:
        # dry-run acceptance when no runner provided
        return {"ok": True, "results": [{"cmd": c, "rc": 0, "dry_run": True} for c in verify_commands]}
    results = []
    for cmd in verify_commands:
        rc = runner(cmd)
        results.append({"cmd": cmd, "rc": rc})
        if rc != 0:
            raise VerifyGateError(f"verify failed: {cmd} rc={rc}")
    return {"ok": True, "results": results}


def run_waves(
    store: TasksStore,
    *,
    task_fn: Callable[[str], None] | None = None,
    max_concurrent: int = MAX_CONCURRENT,
    start_wave: int | None = None,
) -> dict:
    """Execute topological waves with semaphore ≤4."""
    tasks = store.load_tasks()
    store.set_ledger(LedgerState.PROGRESS)
    depends = {t.id: t.depends for t in tasks.tasks}
    waves = compute_waves(depends)
    wave_map = assign_waves_to_tasks(depends)
    for t in tasks.tasks:
        t.wave = wave_map.get(t.id)
    store.write_tasks(tasks)

    resume = start_wave if start_wave is not None else tasks.resume_wave
    executed: list[str] = []
    for wi, wave in enumerate(waves):
        if wi < resume:
            continue
        # T0 must be alone in wave 0 ideally — still run with concurrency cap
        workers = min(max_concurrent, max(1, len(wave)))
        if task_fn is None:
            for tid in wave:
                executed.append(tid)
            continue
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(task_fn, tid): tid for tid in wave}
            for fut in as_completed(futs):
                tid = futs[fut]
                fut.result()
                executed.append(tid)
        store.set_ledger(LedgerState.PROGRESS, resume_wave=wi + 1)
    return {"executed": executed, "waves": waves}


def append_blocker(
    store: TasksStore,
    *,
    title: str,
    falsified: str,
    evidence: str,
    class_: BlockerClass,
    falsified_tasks: list[str],
) -> Blocker:
    tasks = store.load_tasks()
    depends = {t.id: t.depends for t in tasks.tasks}
    inputs_origins = {
        t.id: [i.get("origin", "") for i in t.inputs] for t in tasks.tasks
    }
    radius = blast_radius(
        falsified_tasks, depends=depends, inputs_origins=inputs_origins
    )
    bid = f"B{len(tasks.blockers) + 1}"
    blocker = Blocker(
        id=bid,
        title=title,
        status=BlockerStatus.OPEN,
        falsified=falsified,
        evidence=evidence,
        **{"class": class_},
        blast_radius_tasks=radius,
        resume_wave=tasks.resume_wave,
    )
    tasks.blockers.append(blocker)
    tasks.ledger = LedgerState.STALL
    store.write_tasks(tasks)
    return blocker


def constitution_excerpts(repo_root: Path, *, max_chars: int = 4000) -> str:
    """Spec Kit constitution mapping → CONSTRAINTS.md + CLAUDE.md excerpts."""
    parts: list[str] = []
    for name in ("CONSTRAINTS.md", "CLAUDE.md"):
        p = Path(repo_root) / name
        if p.is_file():
            text = p.read_text(encoding="utf-8")[: max_chars // 2]
            parts.append(f"<!-- {name} -->\n{text}")
    return "\n\n".join(parts)
