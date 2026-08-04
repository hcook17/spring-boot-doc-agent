#!/usr/bin/env python3
"""Contract for rule_coverage.py, the gate that proves each CodeQL query can
actually fire.

Not covered by sibling suites. tests/doc_engine/test_spring_signal_scan.py pins what the
scanner *produces* for a handful of buckets; it names a few of the rule ids and
has never asserted that the rest are capable of matching anything at all.
That gap is the whole reason this file exists: on a real production Spring
service, many rules returned zero and nothing could say whether they were broken
or simply unexercised.

The load-bearing test is test_a_rule_with_no_fixture_is_caught. Without it,
rule_coverage.py could report "all rules fired" because it silently found no
rules to check, which is the vacuous-pass shape this repo keeps writing
directional tests against.

L6: also pins committed baseline schema SoR, fail-closed missing/forged
baseline, empty pack / empty fixtures, main exit 1, and drop-to-zero-only
ratchet polarity (partial drops stay green).

Run with: pytest tests/coverage/test_rule_coverage.py -v
"""
from __future__ import annotations

import collections
import json
import sys
import tempfile
import unittest
from pathlib import Path
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

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

    def test_as_rule_id_spelling_is_enumerated(self) -> None:
        """RawQueries.ql uses `"…" as rule_id`; missing it under-counts the pack."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Raw.ql"
            path.write_text('"bucket__as_form" as rule_id,\n', encoding="utf-8")
            self.assertEqual(rc.rule_ids(path), ["bucket__as_form"])
        self.assertIn("raw_queries__query", rc.rule_ids())
        self.assertGreaterEqual(len(rc.rule_ids()), 29)


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

    def test_an_empty_fixture_directory_fails(self) -> None:
        """Present-but-empty corpus is not a vacuous pass."""
        real_dir = rc.FIXTURE_DIR
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "spring_signals"
            empty.mkdir()
            try:
                rc.FIXTURE_DIR = empty
                problems = rc.check_non_vacuity()
                self.assertTrue(problems, "empty fixture dir must fail non-vacuity")
            finally:
                rc.FIXTURE_DIR = real_dir

    def test_an_empty_pack_fails_rather_than_passing_vacuously(self) -> None:
        original = rc.rule_ids
        try:
            rc.rule_ids = lambda *a, **k: []  # type: ignore[assignment]
            problems = rc.check_non_vacuity()
            self.assertTrue(any("empty" in p.lower() or "no rule" in p.lower()
                                for p in problems), problems)
        finally:
            rc.rule_ids = original  # type: ignore[assignment]

    def test_an_exemption_must_state_a_reason(self) -> None:
        real = dict(rc.FIXTURE_EXEMPT)
        try:
            rc.FIXTURE_EXEMPT["some__rule"] = "   "
            self.assertTrue(any("no stated reason" in p
                                for p in rc.check_non_vacuity()))
        finally:
            rc.FIXTURE_EXEMPT.clear()
            rc.FIXTURE_EXEMPT.update(real)

    def test_fixture_dir_is_spring_signals_not_metamorphic_rule_fixtures(self) -> None:
        """Corpus ownership: coverage SoR ≠ metamorphic rule_fixtures/."""
        resolved = rc.FIXTURE_DIR.resolve()
        self.assertEqual(resolved.name, "spring_signals")
        self.assertEqual(
            resolved,
            (SCRIPTS_DIR / "fixtures" / "spring_signals").resolve(),
        )
        metamorphic = (SCRIPTS_DIR / "coverage" / "rule_fixtures").resolve()
        self.assertNotEqual(resolved, metamorphic)


class TestCommittedBaselineSoR(unittest.TestCase):
    """Hermetic CI witness: committed baseline stamp matches SCHEMA_VERSION
    and count keys are pack-owned. Does not require an external corpus."""

    def test_write_baseline_keeps_only_pack_owned_keys(self) -> None:
        """--update must not reintroduce scanner-only / non-pack tags."""
        with tempfile.TemporaryDirectory() as tmp:
            real = rc.BASELINE_FILE
            try:
                rc.BASELINE_FILE = Path(tmp) / "baseline.json"
                counts = collections.Counter({
                    "persistence__entity": 3,
                    "deployment__build_gradle": 99,  # filesystem tag, not pack
                    "raw_queries__query": 7,
                })
                rc.write_baseline(Path(tmp) / "corpus", counts)
                data = json.loads(rc.BASELINE_FILE.read_text(encoding="utf-8"))
                self.assertEqual(data["schema_version"], rc.SCHEMA_VERSION)
                self.assertIn("persistence__entity", data["counts"])
                self.assertIn("raw_queries__query", data["counts"])
                self.assertNotIn("deployment__build_gradle", data["counts"])
            finally:
                rc.BASELINE_FILE = real


class TestRatchet(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.real_baseline = rc.BASELINE_FILE
        rc.BASELINE_FILE = Path(self.tmp.name) / "baseline.json"

    def tearDown(self) -> None:
        rc.BASELINE_FILE = self.real_baseline
        self.tmp.cleanup()

    def baseline(self, counts: dict, *, schema_version: int | None = None) -> None:
        rc.BASELINE_FILE.write_text(json.dumps({
            "schema_version": rc.SCHEMA_VERSION if schema_version is None else schema_version,
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

    def test_partial_count_drop_is_not_a_regression(self) -> None:
        """Polarity pin: drop-to-zero only; 5→3 stays green (coverage-gates)."""
        self.baseline({"a__b": 5})
        self.assertEqual(rc.check_ratchet(collections.Counter({"a__b": 3})), [])

    def test_a_missing_baseline_is_a_failure(self) -> None:
        """SoR absent ≠ OK (L6 fail-closed)."""
        self.assertFalse(rc.BASELINE_FILE.is_file())
        problems = rc.check_ratchet(collections.Counter())
        self.assertTrue(problems)
        self.assertTrue(any("missing" in p.lower() or "absent" in p.lower()
                            for p in problems), problems)

    def test_a_stale_schema_version_is_rejected(self) -> None:
        rc.BASELINE_FILE.write_text(
            json.dumps({"schema_version": 999, "counts": {}}), encoding="utf-8")
        self.assertTrue(rc.check_ratchet(collections.Counter()))

    def test_counts_not_an_object_is_rejected(self) -> None:
        rc.BASELINE_FILE.write_text(json.dumps({
            "schema_version": rc.SCHEMA_VERSION,
            "counts": ["not", "an", "object"],
        }), encoding="utf-8")
        problems = rc.check_ratchet(collections.Counter())
        self.assertTrue(any("counts" in p for p in problems), problems)

    def test_missing_counts_key_is_rejected(self) -> None:
        rc.BASELINE_FILE.write_text(json.dumps({
            "schema_version": rc.SCHEMA_VERSION,
            "corpus": "fake",
        }), encoding="utf-8")
        problems = rc.check_ratchet(collections.Counter())
        self.assertTrue(any("counts" in p for p in problems), problems)

    def test_corrupt_json_baseline_is_rejected(self) -> None:
        rc.BASELINE_FILE.write_text("{not-json", encoding="utf-8")
        problems = rc.check_ratchet(collections.Counter())
        self.assertTrue(problems)
        self.assertTrue(any("json" in p.lower() or "parse" in p.lower()
                            for p in problems), problems)


class TestExitCodes(unittest.TestCase):
    """Assert the exit code, not an internal list -- the exit code is what CI
    actually reads."""

    def test_fixture_mode_exits_zero(self) -> None:
        self.assertEqual(rc.main([]), 0)

    def test_a_missing_target_directory_exits_two(self) -> None:
        self.assertEqual(rc.main(["no-such-directory-here"]), 2)

    def test_non_vacuity_failure_exits_one(self) -> None:
        original = rc.rule_ids
        try:
            rc.rule_ids = lambda *a, **k: original() + ["invented__exit1"]  # type: ignore[assignment]
            self.assertEqual(rc.main([]), 1)
        finally:
            rc.rule_ids = original  # type: ignore[assignment]

    def test_ratchet_failure_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "corpus"
            repo.mkdir()
            (repo / "Empty.java").write_text("// empty\n", encoding="utf-8")
            real_baseline = rc.BASELINE_FILE
            baseline = Path(tmp) / "baseline.json"
            baseline.write_text(json.dumps({
                "schema_version": rc.SCHEMA_VERSION,
                "corpus": "fake",
                "counts": {"persistence__entity": 5},
            }), encoding="utf-8")
            try:
                rc.BASELINE_FILE = baseline
                self.assertEqual(rc.main([str(repo)]), 1)
            finally:
                rc.BASELINE_FILE = real_baseline


if __name__ == "__main__":
    unittest.main(verbosity=2)
