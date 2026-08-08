"""DAG utilities — SPOQ-style topological waves + blast-radius BFS."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable


class CycleError(ValueError):
    """Dependency graph contains a cycle."""


def _normalize_deps(tasks: dict[str, Iterable[str]]) -> dict[str, set[str]]:
    return {tid: set(deps or ()) for tid, deps in tasks.items()}


def _dfs_cycle(
    node: str,
    deps: dict[str, set[str]],
    visiting: set[str],
    visited: set[str],
    stack: list[str],
) -> list[str] | None:
    if node in visiting:
        if node in stack:
            i = stack.index(node)
            return stack[i:] + [node]
        return [node, node]
    if node in visited:
        return None
    visiting.add(node)
    stack.append(node)
    for pred in deps.get(node, ()):
        if pred not in deps:
            continue
        hit = _dfs_cycle(pred, deps, visiting, visited, stack)
        if hit:
            return hit
    stack.pop()
    visiting.remove(node)
    visited.add(node)
    return None


def detect_cycle(tasks: dict[str, Iterable[str]]) -> list[str] | None:
    """Return one cycle path if present, else None."""
    deps = _normalize_deps(tasks)
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []
    for tid in deps:
        hit = _dfs_cycle(tid, deps, visiting, visited, stack)
        if hit:
            return hit
    return None


def compute_waves(tasks: dict[str, Iterable[str]]) -> list[list[str]]:
    """Topological wave assignment: wave k = tasks whose deps are all in earlier waves."""
    deps = _normalize_deps(tasks)
    cycle = detect_cycle(deps)
    if cycle:
        raise CycleError(f"cycle detected: {' -> '.join(cycle)}")

    remaining = set(deps)
    placed: set[str] = set()
    waves: list[list[str]] = []
    while remaining:
        ready = sorted(
            tid for tid in remaining if deps[tid].issubset(placed)
        )
        if not ready:
            ready = sorted(remaining)
        waves.append(ready)
        for tid in ready:
            remaining.discard(tid)
            placed.add(tid)
    return waves


def _is_task_origin(origin: str) -> bool:
    return len(origin) >= 2 and origin[0] == "T" and origin[1:].isdigit()


def _build_reverse_depends(depends: dict[str, Iterable[str]]) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = defaultdict(set)
    for tid, preds in _normalize_deps(depends).items():
        for p in preds:
            reverse[p].add(tid)
    return reverse


def _add_inputs_origin_edges(
    reverse: dict[str, set[str]],
    inputs_origins: dict[str, Iterable[str]],
) -> None:
    for tid, origins in inputs_origins.items():
        for o in origins:
            if _is_task_origin(o):
                reverse[o].add(tid)


def _bfs_reachable(seeds: Iterable[str], reverse: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    q: deque[str] = deque(seeds)
    while q:
        cur = q.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        for nxt in reverse.get(cur, ()):
            if nxt not in seen:
                q.append(nxt)
    return seen


def blast_radius(
    falsified_tasks: Iterable[str],
    *,
    depends: dict[str, Iterable[str]],
    inputs_origins: dict[str, Iterable[str]] | None = None,
) -> list[str]:
    """Tasks transitively dependent on falsified items via depends/inputs (BFS)."""
    reverse = _build_reverse_depends(depends)
    if inputs_origins:
        _add_inputs_origin_edges(reverse, inputs_origins)
    return sorted(_bfs_reachable(falsified_tasks, reverse))


def assign_waves_to_tasks(tasks: dict[str, Iterable[str]]) -> dict[str, int]:
    waves = compute_waves(tasks)
    out: dict[str, int] = {}
    for i, wave in enumerate(waves):
        for tid in wave:
            out[tid] = i
    return out
