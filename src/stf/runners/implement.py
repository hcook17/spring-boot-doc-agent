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


def _cited_origins(tasks: TasksDocument) -> set[object]:
    return {i.get("origin") for t in tasks.tasks for i in t.inputs}


def _critical_finding_ids(finding_ids: list[str]) -> list[str]:
    return [fid for fid in finding_ids if fid.startswith("C")]


def _finding_coverage(tasks: TasksDocument, spec: SpecDocument | None) -> bool:
    if spec is None or not spec.finding_ids:
        return True
    inv_cited = _cited_origins(tasks)
    return any(f"INV-{fid}" in inv_cited for fid in _critical_finding_ids(spec.finding_ids))


def plan_gate(tasks: TasksDocument, spec: SpecDocument | None = None) -> dict:
    """Dual gate #1 — before Wave 1 execution."""
    results = lint_tasks_document(tasks, spec)
    summary = lint_summary(results)
    if not summary["ok"]:
        raise PlanGateError(f"plan gate failed: {summary['fail']} FAIL(s)")
    depends = {t.id: t.depends for t in tasks.tasks}
    waves = compute_waves(depends)
    return {
        "ok": True,
        "waves": waves,
        "finding_coverage": _finding_coverage(tasks, spec),
        "lint": summary,
    }


def _dry_run_verify_results(verify_commands: list[str]) -> dict:
    return {
        "ok": True,
        "results": [{"cmd": c, "rc": 0, "dry_run": True} for c in verify_commands],
    }


def verify_gate(
    *,
    verify_commands: list[str],
    runner: Callable[[str], int] | None = None,
) -> dict:
    """Dual gate #2 — Verify cmds must exit 0 (or dry-run)."""
    if runner is None:
        return _dry_run_verify_results(verify_commands)
    results = []
    for cmd in verify_commands:
        rc = runner(cmd)
        results.append({"cmd": cmd, "rc": rc})
        if rc != 0:
            raise VerifyGateError(f"verify failed: {cmd} rc={rc}")
    return {"ok": True, "results": results}


def _assign_task_waves(tasks: TasksDocument) -> list[list[str]]:
    depends = {t.id: t.depends for t in tasks.tasks}
    waves = compute_waves(depends)
    wave_map = assign_waves_to_tasks(depends)
    for t in tasks.tasks:
        t.wave = wave_map.get(t.id)
    return waves


def _run_wave_dry(wave: list[str], executed: list[str]) -> None:
    executed.extend(wave)


def _run_wave_concurrent(
    wave: list[str],
    *,
    task_fn: Callable[[str], None],
    max_concurrent: int,
    executed: list[str],
) -> None:
    workers = min(max_concurrent, max(1, len(wave)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(task_fn, tid): tid for tid in wave}
        for fut in as_completed(futs):
            tid = futs[fut]
            fut.result()
            executed.append(tid)


def _execute_remaining_waves(
    *,
    store: TasksStore,
    waves: list[list[str]],
    resume: int,
    task_fn: Callable[[str], None] | None,
    max_concurrent: int,
) -> list[str]:
    executed: list[str] = []
    for wi, wave in enumerate(waves):
        if wi < resume:
            continue
        if task_fn is None:
            _run_wave_dry(wave, executed)
            continue
        _run_wave_concurrent(
            wave,
            task_fn=task_fn,
            max_concurrent=max_concurrent,
            executed=executed,
        )
        store.set_ledger(LedgerState.PROGRESS, resume_wave=wi + 1)
    return executed


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
    waves = _assign_task_waves(tasks)
    store.write_tasks(tasks)
    resume = start_wave if start_wave is not None else tasks.resume_wave
    executed = _execute_remaining_waves(
        store=store,
        waves=waves,
        resume=resume,
        task_fn=task_fn,
        max_concurrent=max_concurrent,
    )
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
