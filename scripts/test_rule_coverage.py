#!/usr/bin/env python3
"""Contract for rule_coverage.py, the gate that proves each CodeQL query can
actually fire.

Not covered by sibling suites. test_spring_signal_scan.py pins what the
scanner *produces* for a handful of buckets; it names a few of the rule ids and
has never asserted that the rest are capable of matching anything at all.
That gap is the whole reason this file exists: on a real production Spring
service, many rules returned zero and nothing could say whether they were broken
or simply unexercised.

The load-bearing test is test_a_rule_with_no_fixture_is_caught. Without it,
rule_coverage.py could report "all rules fired" because it silently found no
rules to check, which is the vacuous-pass shape this repo keeps writing
directional tests against.

Run with: python3 scripts/test_rule_coverage.py -v
"""
from __future__ import annotations

import collections
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rule_coverage as rc  # noqa: E402


class TestRuleIdParsing(unittest.TestCase):
    def test_the_real_rule_file_yields_rules(self) -> None:
        """If this ever returns [], every other check here passes vacuously."""
        ids = rc.rule_ids()
        self.assertGreaterEqual(len(ids), 20)
        self.assertIn("persistence__entity", ids)

    def test_duplicate_rule_ids_are_deduplicated(self) -> None:
        """A query may repeat the same rule_id in multiple branches; the
        denominator must count each logical rule only once."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Dummy.ql"
            path.write_text(
                'rule_id = "bucket__real"\n'
                'rule_id = "bucket__real"\n'
                'rule_id = "bucket__other"\n',
                encoding="utf-8")
            self.assertEqual(rc.rule_ids(path), ["bucket__real", "bucket__other"])


class TestNonVacuity(unittest.TestCase):
    def test_every_real_rule_fires_on_the_fixture_corpus(self) -> None:
        """The invariant itself, against the committed fixtures."""
        self.assertEqual(rc.check_non_vacuity(), [])

    def test_a_rule_with_no_fixture_is_caught(self) -> None:
        """Proves the gate is not passing because it looked at nothing: a
        rule that exists but nothing triggers must be reported."""
        original = rc.rule_ids
        try:
            rc.rule_ids = lambda *a, **k: original() + ["invented__rule"]  # type: ignore[assignment]
            problems = rc.check_non_vacuity()
            self.assertTrue(any("invented__rule" in p for p in problems), problems)
        finally:
            rc.rule_ids = original  # type: ignore[assignment]

    def test_a_missing_fixture_corpus_fails_rather_than_passing(self) -> None:
        real_dir = rc.FIXTURE_DIR
        try:
            rc.FIXTURE_DIR = Path(tempfile.gettempdir()) / "definitely-not-here"
            self.assertTrue(rc.check_non_vacuity())
        finally:
            rc.FIXTURE_DIR = real_dir

    def test_an_exemption_must_state_a_reason(self) -> None:
        real = dict(rc.FIXTURE_EXEMPT)
        try:
            rc.FIXTURE_EXEMPT["some__rule"] = "   "
            self.assertTrue(any("no stated reason" in p
                                for p in rc.check_non_vacuity()))
        finally:
            rc.FIXTURE_EXEMPT.clear()
            rc.FIXTURE_EXEMPT.update(real)


class TestRatchet(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.real_baseline = rc.BASELINE_FILE
        rc.BASELINE_FILE = Path(self.tmp.name) / "baseline.json"

    def tearDown(self) -> None:
        rc.BASELINE_FILE = self.real_baseline
        self.tmp.cleanup()

    def baseline(self, counts: dict) -> None:
        rc.BASELINE_FILE.write_text(json.dumps({
            "schema_version": rc.SCHEMA_VERSION,
            "corpus": "fake",
            "counts": counts,
        }), encoding="utf-8")

    def test_a_rule_dropping_to_zero_is_a_regression(self) -> None:
        self.baseline({"a__b": 5})
        self.assertTrue(rc.check_ratchet(collections.Counter()))

    def test_rising_counts_pass(self) -> None:
        self.baseline({"a__b": 5})
        self.assertEqual(rc.check_ratchet(collections.Counter({"a__b": 9})), [])

    def test_a_rule_that_was_already_zero_is_not_a_regression(self) -> None:
        """Zero-to-zero is the ordinary case for a framework this corpus does
        not use, and flagging it would make the gate cry wolf permanently."""
        self.baseline({"a__b": 0})
        self.assertEqual(rc.check_ratchet(collections.Counter()), [])

    def test_a_missing_baseline_is_not_a_failure(self) -> None:
        self.assertEqual(rc.check_ratchet(collections.Counter()), [])

    def test_a_stale_schema_version_is_rejected(self) -> None:
        rc.BASELINE_FILE.write_text(
            json.dumps({"schema_version": 999, "counts": {}}), encoding="utf-8")
        self.assertTrue(rc.check_ratchet(collections.Counter()))


class TestExitCodes(unittest.TestCase):
    """Assert the exit code, not an internal list -- the exit code is what CI
    actually reads."""

    def test_fixture_mode_exits_zero(self) -> None:
        self.assertEqual(rc.main([]), 0)

    def test_a_missing_target_directory_exits_two(self) -> None:
        self.assertEqual(rc.main(["no-such-directory-here"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
