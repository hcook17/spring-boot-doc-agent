"""Unit tests — white-box, isolated helpers (shift-left)."""

from __future__ import annotations

import pytest

from stf.graph.dag import (
    CycleError,
    blast_radius,
    compute_waves,
    detect_cycle,
)
from stf.validators.lint_tasks import lint_summary, lint_tasks_document, mutate_tasks
from tests.stf.conftest import build_minimal_valid_spec, build_minimal_valid_tasks

MUTATION_MODES = (
    "bad-dep",
    "no-phase",
    "bad-inventory",
    "no-acceptance",
    "bad-blocker",
    "cycle",
)


def test_compute_waves_places_independent_tasks_in_same_wave() -> None:
    waves = compute_waves({"T0": [], "T1": ["T0"], "T2": ["T0"], "T3": ["T1", "T2"]})
    assert waves[0] == ["T0"]
    assert set(waves[1]) == {"T1", "T2"}
    assert waves[2] == ["T3"]


def test_detect_cycle_returns_path_when_tasks_depend_on_each_other() -> None:
    assert detect_cycle({"A": ["B"], "B": ["A"]}) is not None
    with pytest.raises(CycleError):
        compute_waves({"A": ["B"], "B": ["A"]})


def test_blast_radius_includes_every_transitive_consumer() -> None:
    radius = blast_radius(
        ["T1"],
        depends={"T0": [], "T1": ["T0"], "T2": ["T1"], "T3": ["T2"]},
        inputs_origins={"T2": ["T1"], "T3": ["T2"]},
    )
    assert radius == ["T1", "T2", "T3"]


def test_lint_accepts_minimal_valid_tasks() -> None:
    summary = lint_summary(
        lint_tasks_document(build_minimal_valid_tasks(), build_minimal_valid_spec())
    )
    assert summary["ok"]


@pytest.mark.parametrize("mode", MUTATION_MODES)
def test_each_named_mutant_is_killed_by_lint(mode: str) -> None:
    """Metamorphic/regression mutants — lint must fail closed."""
    mutated = mutate_tasks(build_minimal_valid_tasks(), mode)
    summary = lint_summary(lint_tasks_document(mutated, build_minimal_valid_spec()))
    assert not summary["ok"], f"mutant {mode} survived lint"
