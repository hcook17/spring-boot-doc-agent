#!/usr/bin/env python3
"""Contract for set_delta.py -- the algebra itself, in isolation.

Split deliberately from test_metamorphic.py: this suite is pure and fast
(no scanning, no ast-grep) and pins what the relations MEAN. That one runs
real scans over perturbed corpora and pins what the scanner DOES. Mixing them
would put a 20-second dependency in front of assertions that are really about
set arithmetic, and the slow half is always the half that gets cut.

The property defended: **a relation permits exactly the movements it names,
and the residue is everything else.** The failure this guards against is a
relation that quietly permits everything -- which would make every metamorphic
test in the sibling suite pass while checking nothing. `RelationsAreNotVacuous`
is the class that would catch it.

Run with: pytest tests/test_set_delta.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

import set_delta as sd  # noqa: E402

A = sd.Member("A.java", "api_surface__controller", "@RestController")
B = sd.Member("B.java", "persistence__entity", "@Entity")
C = sd.Member("A.java", "observability__timed", "@Timed")


def s(*members) -> frozenset:
    return frozenset(members)


class DeltaTest(unittest.TestCase):
    def test_identical_sets_have_an_empty_delta(self) -> None:
        self.assertTrue(sd.delta(s(A, B), s(A, B)).is_empty())

    def test_addition_and_removal_are_separated(self) -> None:
        change = sd.delta(s(A, B), s(A, C))
        self.assertEqual(change.added, s(C))
        self.assertEqual(change.removed, s(B))

    def test_delta_is_directional(self) -> None:
        """delta(x, y) is not delta(y, x). Getting this backwards would
        report every addition as a removal."""
        forward, backward = sd.delta(s(A), s(A, B)), sd.delta(s(A, B), s(A))
        self.assertEqual(forward.added, backward.removed)
        self.assertEqual(forward.removed, backward.added)


class UnchangedRelationTest(unittest.TestCase):
    def test_permits_nothing(self) -> None:
        residue = sd.classify(sd.delta(s(A), s(A, B)), sd.unchanged())
        self.assertEqual(residue.added, s(B))

    def test_an_empty_delta_leaves_no_residue(self) -> None:
        self.assertTrue(sd.classify(sd.delta(s(A), s(A)), sd.unchanged()).is_empty())


class ConfinedToTest(unittest.TestCase):
    def test_movement_inside_the_named_files_is_expected(self) -> None:
        residue = sd.classify(sd.delta(s(A), s(A, C)), sd.confined_to(["A.java"]))
        self.assertTrue(residue.is_empty())

    def test_movement_outside_them_is_residue(self) -> None:
        """Locality. This is the assertion that catches a rule edit reaching
        further than the file it was aimed at."""
        residue = sd.classify(sd.delta(s(A), s(A, B)), sd.confined_to(["A.java"]))
        self.assertEqual(residue.added, s(B))

    def test_an_empty_file_list_permits_nothing(self) -> None:
        residue = sd.classify(sd.delta(s(A), s(A, B)), sd.confined_to([]))
        self.assertEqual(residue.added, s(B))


class ConfinedToRulesTest(unittest.TestCase):
    def test_the_named_rule_may_move(self) -> None:
        residue = sd.classify(sd.delta(s(A), s(A, C)),
                              sd.confined_to_rules(["observability__timed"]))
        self.assertTrue(residue.is_empty())

    def test_another_rule_moving_is_residue(self) -> None:
        """Adding a rule must not disturb what the existing rules found."""
        residue = sd.classify(sd.delta(s(A), s(A, B)),
                              sd.confined_to_rules(["observability__timed"]))
        self.assertEqual(residue.added, s(B))


class GrowsOnlyTest(unittest.TestCase):
    def test_additions_are_expected(self) -> None:
        self.assertTrue(sd.classify(sd.delta(s(A), s(A, B)), sd.grows_only()).is_empty())

    def test_a_removal_is_a_regression(self) -> None:
        residue = sd.classify(sd.delta(s(A, B), s(A)), sd.grows_only())
        self.assertEqual(residue.removed, s(B))


class RelationsAreNotVacuousTest(unittest.TestCase):
    """The guard on the guards. A relation that permitted everything would
    make every metamorphic assertion pass while checking nothing, and it
    would look identical from a test that only feeds it conforming input."""

    def test_every_registered_relation_rejects_something(self) -> None:
        cases = {
            "unchanged": sd.unchanged(),
            "confined_to": sd.confined_to(["A.java"]),
            "confined_to_rules": sd.confined_to_rules(["api_surface__controller"]),
            "grows_only": sd.grows_only(),
        }
        self.assertEqual(set(cases), set(sd.RELATIONS),
                         "a relation was added to RELATIONS without a rejection case here")
        for name, relation in cases.items():
            with self.subTest(relation=name):
                change = sd.delta(s(A, B), s(A, C))
                self.assertFalse(sd.classify(change, relation).is_empty(),
                                 f"{name} permitted a delta it should have rejected")


class ScalingTest(unittest.TestCase):
    def test_exact_doubling_passes(self) -> None:
        before = s(A)
        after = s(A, sd.Member("A_copy.java", A.rule_id, A.match))
        self.assertEqual(sd.check_scaling(before, after, 2), [])

    def test_a_short_count_is_reported_with_both_numbers(self) -> None:
        """Rule 7 of the directional-tests doctrine: state the bound. A bare
        'scaling failed' would not say which rule or by how much."""
        problems = sd.check_scaling(s(A, B), s(A, B), 2)
        self.assertEqual(len(problems), 2)
        self.assertTrue(any("expected 2" in p for p in problems), problems)

    def test_counts_are_per_rule_not_per_set(self) -> None:
        counts = sd.counts_by_rule(s(A, C))
        self.assertEqual(counts["api_surface__controller"], 1)
        self.assertEqual(counts["observability__timed"], 1)


class ResidueDescriptionTest(unittest.TestCase):
    def test_describe_names_file_rule_and_direction(self) -> None:
        residue = sd.classify(sd.delta(s(A), s(A, B)), sd.unchanged())
        text = "\n".join(residue.describe())
        self.assertIn("B.java", text)
        self.assertIn("persistence__entity", text)
        self.assertTrue(text.lstrip().startswith("+"), text)


class ValidityGateTest(unittest.TestCase):
    def test_a_failed_scan_raises_rather_than_reporting_an_empty_set(self) -> None:
        """A failed scan and a repo with genuinely nothing in it produce the
        same empty set. Scoring the first as 'everything was removed' is a
        confident wrong answer, so it must raise instead."""
        with self.assertRaises(sd.ScanFailed):
            sd.signals_set(Path("no-such-directory-anywhere"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
