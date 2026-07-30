#!/usr/bin/env python3
"""Contract for semgrep_rule_coverage.py, the semgrep analog of
test_rule_coverage.py.

Mirrors that file's structure and its central lesson: the load-bearing test
is test_a_rule_with_no_fixture_is_caught, not
test_every_real_rule_fires_on_the_fixture_corpus -- without it, this checker
could report "10/10 rules fired" because it silently found no rules to
check, which is the vacuous-pass shape rule_coverage.py was built to catch,
and now this file's semgrep counterpart is held to the same standard.

Run with: pytest tests/test_semgrep_rule_coverage.py -v
"""
from __future__ import annotations

import collections
import json
import sys
import tempfile
import unittest
from pathlib import Path
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

import semgrep_rule_coverage as sc  # noqa: E402


class TestRuleIdParsing(unittest.TestCase):
    def test_the_real_rule_file_yields_rules(self) -> None:
        """If this ever returns [], every other check here passes vacuously."""
        ids = sc.rule_ids()
        self.assertGreaterEqual(len(ids), 10)
        self.assertIn("architecture_ddia__entity_no_version_field", ids)
        self.assertIn("testing_est__test_method_no_assertion", ids)

    def test_a_nested_id_is_not_mistaken_for_a_rule(self) -> None:
        """A bare `id:` inside a rule body (e.g. metavariable-pattern) is not
        a rule name -- only a `- id:` list item under `rules:` is."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.yml"
            path.write_text(
                "rules:\n"
                "  - id: bucket__real\n"
                "    languages: [java]\n"
                "    pattern-inside: |\n"
                "      id: not_a_rule\n",
                encoding="utf-8")
            self.assertEqual(sc.rule_ids(path), ["bucket__real"])


class TestCheckIdNormalization(unittest.TestCase):
    """semgrep prefixes check_id with a cwd-dependent path when a rule file
    is passed by local path (see the module docstring); this is the specific
    behavior that made the un-normalized version of this checker silently
    report every rule as unfired the first time it was run from a different
    directory than it was written in."""

    def test_short_prefix_is_stripped(self) -> None:
        self.assertEqual(
            sc._normalize_check_id("scripts.architecture_ddia__entity_no_version_field"),
            "architecture_ddia__entity_no_version_field")

    def test_long_absolute_path_prefix_is_stripped(self) -> None:
        self.assertEqual(
            sc._normalize_check_id(
                "C.Users.someone.Downloads.repo.scripts."
                "testing_est__test_method_no_assertion"),
            "testing_est__test_method_no_assertion")

    def test_an_unprefixed_id_is_left_alone(self) -> None:
        self.assertEqual(
            sc._normalize_check_id("architecture_ddia__unbounded_findall_exposed"),
            "architecture_ddia__unbounded_findall_exposed")


class TestNonVacuity(unittest.TestCase):
    def test_every_real_rule_fires_on_the_fixture_corpus(self) -> None:
        """The invariant itself, against the committed fixtures. Requires a
        real `semgrep` on PATH -- skipped, not silently passed, if absent."""
        try:
            sc.find_semgrep()
        except sc.SemgrepNotFoundError:
            self.skipTest("semgrep not on PATH")
        self.assertEqual(sc.check_non_vacuity(), [])

    def test_a_rule_with_no_fixture_is_caught(self) -> None:
        """Proves the gate is not passing because it looked at nothing: a
        rule that exists but nothing triggers must be reported."""
        try:
            sc.find_semgrep()
        except sc.SemgrepNotFoundError:
            self.skipTest("semgrep not on PATH")
        original = sc.rule_ids
        try:
            sc.rule_ids = lambda *a, **k: original() + ["invented__rule"]  # type: ignore[assignment]
            problems = sc.check_non_vacuity()
            self.assertTrue(any("invented__rule" in p for p in problems), problems)
        finally:
            sc.rule_ids = original  # type: ignore[assignment]

    def test_a_missing_fixture_corpus_fails_rather_than_passing(self) -> None:
        real_dir = sc.FIXTURE_DIR
        try:
            sc.FIXTURE_DIR = Path(tempfile.gettempdir()) / "definitely-not-here"
            self.assertTrue(sc.check_non_vacuity())
        finally:
            sc.FIXTURE_DIR = real_dir

    def test_an_exemption_must_state_a_reason(self) -> None:
        try:
            sc.find_semgrep()
        except sc.SemgrepNotFoundError:
            self.skipTest("semgrep not on PATH")
        real = dict(sc.FIXTURE_EXEMPT)
        try:
            sc.FIXTURE_EXEMPT["some__rule"] = "   "
            self.assertTrue(any("no stated reason" in p
                                for p in sc.check_non_vacuity()))
        finally:
            sc.FIXTURE_EXEMPT.clear()
            sc.FIXTURE_EXEMPT.update(real)


class TestRatchet(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.real_baseline = sc.BASELINE_FILE
        sc.BASELINE_FILE = Path(self.tmp.name) / "baseline.json"

    def tearDown(self) -> None:
        sc.BASELINE_FILE = self.real_baseline
        self.tmp.cleanup()

    def baseline(self, counts: dict) -> None:
        sc.BASELINE_FILE.write_text(json.dumps({
            "schema_version": sc.SCHEMA_VERSION,
            "corpus": "fake",
            "counts": counts,
        }), encoding="utf-8")

    def test_a_rule_dropping_to_zero_is_a_regression(self) -> None:
        self.baseline({"a__b": 5})
        self.assertTrue(sc.check_ratchet(collections.Counter()))

    def test_rising_counts_pass(self) -> None:
        self.baseline({"a__b": 5})
        self.assertEqual(sc.check_ratchet(collections.Counter({"a__b": 9})), [])

    def test_a_rule_that_was_already_zero_is_not_a_regression(self) -> None:
        self.baseline({"a__b": 0})
        self.assertEqual(sc.check_ratchet(collections.Counter()), [])

    def test_a_missing_baseline_is_not_a_failure(self) -> None:
        self.assertEqual(sc.check_ratchet(collections.Counter()), [])

    def test_a_stale_schema_version_is_rejected(self) -> None:
        sc.BASELINE_FILE.write_text(
            json.dumps({"schema_version": 999, "counts": {}}), encoding="utf-8")
        self.assertTrue(sc.check_ratchet(collections.Counter()))


class TestExitCodes(unittest.TestCase):
    """Assert the exit code, not an internal list -- the exit code is what CI
    actually reads."""

    def test_fixture_mode_exits_zero_or_two_without_semgrep(self) -> None:
        code = sc.main([])
        try:
            sc.find_semgrep()
            self.assertEqual(code, 0)
        except sc.SemgrepNotFoundError:
            self.assertEqual(code, 2)

    def test_a_missing_target_directory_exits_two(self) -> None:
        self.assertEqual(sc.main(["no-such-directory-here"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
