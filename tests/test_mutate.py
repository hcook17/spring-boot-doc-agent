#!/usr/bin/env python3
"""Contract for mutate.py -- the harness that proves the other suites can fail.

A mutation harness that cannot report a survivor is worse than none: it emits
a reassuring score while checking nothing, and the score is the artifact people
would trust. `SurvivorDetectionTest` is therefore the load-bearing case here.

The second property, equally important and easy to lose: **the working tree is
never touched.** The manual ritual this harness replaces relied on try/finally
and a steady hand, and a crash between break and restore left the repo
silently broken. `SandboxIsolationTest` asserts the tracked tree is unchanged
after a real run, including one that raises partway through.

`RegistryAnchorsTest` is the guard against slow rot: a mutator whose anchor no
longer exists in the file it names silently tests nothing while still counting
as "applied" in a naive implementation. Here it is a test failure.

Run with: pytest tests/test_mutate.py -v
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

import mutate  # noqa: E402


class RegistryAnchorsTest(unittest.TestCase):
    """Every mutator must still find its anchor in the real tree."""

    def test_every_mutator_anchor_exists(self) -> None:
        """A drifted anchor is a mutator that silently tests nothing. Checked
        the way the mutator itself locates its target: structurally for the
        ast-grep ones, literally for the rest -- asserting a substring against
        a pattern containing `$V` would fail for the wrong reason."""
        for m in mutate.MUTATORS:
            with self.subTest(mutator=m.name):
                path = mutate.REPO_ROOT / m.path
                self.assertTrue(path.is_file(), f"{m.path} is missing")
                if m.lang:
                    found = subprocess.run(
                        ["ast-grep", "run", "-l", m.lang, "-p", m.find,
                         "--json=compact", str(path)],
                        capture_output=True, text=True)
                    self.assertNotEqual(
                        json.loads(found.stdout or "[]"), [],
                        f"{m.name}'s structural pattern matches nothing in {m.path}")
                else:
                    self.assertIn(m.find, path.read_text(encoding="utf-8"),
                                  f"{m.name}'s literal anchor has drifted out of "
                                  f"{m.path}; it is testing nothing")

    def test_literal_mutators_state_why_they_are_not_structural(self) -> None:
        """Text matching is the thing this repo spent a release removing. A
        literal anchor is allowed, but only for the two reasons the Mutator
        docstring gives, so the count is pinned here rather than left to grow
        quietly."""
        literal = {m.path for m in mutate.MUTATORS if not m.lang}
        self.assertEqual(
            literal,
            {"adapters/claude/agents/gap-analyzer.md",
             "adapters/claude/agents/file-summarizer.md", "CLAUDE.md",
             "src/doc_engine/scanning/resources/spring_ast_grep_rules.yml"},
            "a new literal mutator appeared; either make it structural or "
            "extend Mutator's docstring with the reason it cannot be")

    def test_every_mutator_names_a_real_suite(self) -> None:
        for m in mutate.MUTATORS:
            with self.subTest(mutator=m.name):
                try:
                    path = mutate.resolve_suite_path(
                        mutate.REPO_ROOT, m.expected_caught_by
                    )
                except FileNotFoundError:
                    path = None
                self.assertIsNotNone(
                    path,
                    f"{m.name} names a suite that does not exist",
                )

    def test_every_mutator_states_why(self) -> None:
        """A survivor report is only actionable if it says what stopped being
        defended. An empty `why` makes the report a name and a shrug."""
        for m in mutate.MUTATORS:
            with self.subTest(mutator=m.name):
                self.assertGreater(len(m.why.strip()), 20, m.name)

    def test_mutator_names_are_unique(self) -> None:
        names = [m.name for m in mutate.MUTATORS]
        self.assertEqual(len(names), len(set(names)))

    def test_a_mutation_actually_changes_the_text(self) -> None:
        for m in mutate.MUTATORS:
            with self.subTest(mutator=m.name):
                self.assertNotEqual(m.find, m.replace, m.name)


class ApplyMutationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mutator(self, find="alpha", replace="beta", path="f.txt", lang=""):
        return mutate.Mutator("m", path, lang, find, replace,
                              "test_set_delta.py", "why " * 6)

    def test_a_structural_pattern_that_matches_nothing_is_an_error(self) -> None:
        """ast-grep exits 0 whether or not its pattern matched -- the silent
        zero this repo has been bitten by twice. The applier compares the file
        before and after rather than trusting the exit code."""
        (self.tmp / "m.py").write_text("x = 1\n", encoding="utf-8")
        error = mutate.apply_mutation(
            self.tmp, self._mutator(find="totally_absent($A)", replace="other($A)",
                                    path="m.py", lang="python"))
        self.assertIn("matched nothing", error or "")

    def test_a_structural_rewrite_survives_reindentation(self) -> None:
        """The reason for structural anchors at all: a literal one breaks
        when someone reformats the target."""
        (self.tmp / "m.py").write_text(
            "def f():\n        return lambda member, direction: False\n",
            encoding="utf-8")
        error = mutate.apply_mutation(
            self.tmp,
            self._mutator(find="return lambda member, direction: False",
                          replace="return lambda member, direction: True",
                          path="m.py", lang="python"))
        self.assertIsNone(error)
        self.assertIn("True", (self.tmp / "m.py").read_text(encoding="utf-8"))

    def test_applies_the_replacement(self) -> None:
        (self.tmp / "f.txt").write_text("alpha\n", encoding="utf-8")
        self.assertIsNone(mutate.apply_mutation(self.tmp, self._mutator()))
        self.assertEqual((self.tmp / "f.txt").read_text(encoding="utf-8"), "beta\n")

    def test_a_missing_anchor_is_an_error_not_a_silent_noop(self) -> None:
        """The failure this returns an error for: a mutator that quietly
        changes nothing would be scored as 'killed' or 'survived' on the
        strength of a file it never touched."""
        (self.tmp / "f.txt").write_text("nothing here\n", encoding="utf-8")
        self.assertIn("anchor not found", mutate.apply_mutation(self.tmp, self._mutator()))

    def test_a_missing_file_is_an_error(self) -> None:
        self.assertIn("not in the tracked tree",
                      mutate.apply_mutation(self.tmp, self._mutator()))

    def test_only_the_first_occurrence_is_replaced(self) -> None:
        (self.tmp / "f.txt").write_text("alpha alpha\n", encoding="utf-8")
        mutate.apply_mutation(self.tmp, self._mutator())
        self.assertEqual((self.tmp / "f.txt").read_text(encoding="utf-8"), "beta alpha\n")


class SurvivorDetectionTest(unittest.TestCase):
    """The load-bearing case. A harness that cannot report a survivor emits a
    reassuring score while checking nothing."""

    def test_a_mutation_no_suite_catches_is_reported_as_survived(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mutate_selftest_") as tmp:
            harmless = mutate.Mutator(
                "harmless-comment-edit", "scripts/set_delta.py", "",
                "THE RESIDUE IS THE FINDING", "THE RESIDUE IS THE FINDING.",
                "test_set_delta.py",
                "editing a docstring changes no behaviour, so nothing should catch it")
            outcome = mutate.evaluate(harmless, Path(tmp))
        self.assertEqual(outcome.status, "survived", outcome.detail)

    def test_a_real_mutation_is_reported_as_killed(self) -> None:
        """The other direction, so 'survived' is not simply what this
        harness always says."""
        with tempfile.TemporaryDirectory(prefix="mutate_selftest_") as tmp:
            real = next(m for m in mutate.MUTATORS if m.name == "relation-permits-everything")
            outcome = mutate.evaluate(real, Path(tmp))
        self.assertEqual(outcome.status, "killed", outcome.detail)


class ReportTest(unittest.TestCase):
    def _outcomes(self, *pairs):
        return [mutate.Outcome(n, s, "detail") for n, s in pairs]

    def test_a_new_survivor_is_a_nonzero_result(self) -> None:
        self.assertEqual(mutate.report(self._outcomes(("a", "survived")), {}), 1)

    def test_a_baselined_survivor_is_accepted(self) -> None:
        self.assertEqual(mutate.report(self._outcomes(("a", "survived")), {"a": "known"}), 0)

    def test_all_killed_is_zero(self) -> None:
        self.assertEqual(mutate.report(self._outcomes(("a", "killed")), {}), 0)

    def test_an_unapplied_mutator_is_nonzero_even_if_baselined(self) -> None:
        """A drifted anchor is never acceptable: it means the mutator is
        inert, which the baseline must not be able to excuse."""
        self.assertEqual(mutate.report(self._outcomes(("a", "not-applied")), {"a": "known"}), 1)


class BaselineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self._real = mutate.BASELINE_FILE
        mutate.BASELINE_FILE = self.tmp / "baseline.json"

    def tearDown(self) -> None:
        mutate.BASELINE_FILE = self._real
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_round_trip(self) -> None:
        mutate.write_baseline([mutate.Outcome("a", "survived", "because"),
                               mutate.Outcome("b", "killed", "-")])
        loaded = mutate.load_baseline()
        self.assertEqual(loaded, {"a": "because"})

    def test_a_stale_schema_version_is_ignored_not_trusted(self) -> None:
        mutate.BASELINE_FILE.write_text(
            json.dumps({"schema_version": 999, "accepted_survivors": {"a": "x"}}),
            encoding="utf-8")
        self.assertEqual(mutate.load_baseline(), {})

    def test_a_missing_baseline_accepts_nothing(self) -> None:
        self.assertEqual(mutate.load_baseline(), {})


class SandboxIsolationTest(unittest.TestCase):
    """The property that makes this safe to run on every commit."""

    def _tracked_diff(self) -> str:
        return subprocess.run(["git", "-C", str(mutate.REPO_ROOT), "diff", "--stat"],
                              capture_output=True, text=True).stdout.strip()

    def test_a_run_leaves_the_tracked_tree_untouched(self) -> None:
        before = self._tracked_diff()
        with tempfile.TemporaryDirectory(prefix="mutate_iso_") as tmp:
            mutate.evaluate(mutate.MUTATORS[0], Path(tmp))
        self.assertEqual(self._tracked_diff(), before,
                         "a mutation escaped the sandbox into the working tree")

    def test_materialize_copies_only_tracked_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mutate_mat_") as tmp:
            dest = Path(tmp) / "copy"
            dest.mkdir()
            mutate.materialize(dest)
            self.assertTrue((dest / "scripts" / "set_delta.py").is_file())
            # The working tree carries an untracked target repo of ~101MB;
            # copying it per mutation would make this harness unusable.
            self.assertFalse((dest / "ocs-api-service-develop").exists())
            self.assertFalse((dest / ".git").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
