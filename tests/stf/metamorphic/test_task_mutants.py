"""Metamorphic tests — named mutants must be killed (regression ratchet)."""

from __future__ import annotations

import pytest

from stf.validators.lint_tasks import lint_summary, lint_tasks_document, mutate_tasks
from tests.stf.conftest import build_minimal_valid_spec, build_minimal_valid_tasks


@pytest.mark.parametrize(
    "mode",
    ["bad-dep", "no-phase", "bad-inventory", "no-acceptance", "bad-blocker", "cycle"],
)
def test_metamorphic_mutant_changes_validity_from_pass_to_fail(mode: str) -> None:
    baseline = build_minimal_valid_tasks()
    spec = build_minimal_valid_spec()
    assert lint_summary(lint_tasks_document(baseline, spec))["ok"]
    mutant = mutate_tasks(baseline, mode)
    assert not lint_summary(lint_tasks_document(mutant, spec))["ok"]
