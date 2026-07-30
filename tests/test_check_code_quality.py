#!/usr/bin/env python3
"""
Tests for check_code_quality.py.

The point of most of these is non-vacuity. A ratchet that silently passes
everything looks identical, from CI's green checkmark, to a ratchet that
works -- and this repo has already shipped one gate that could not fail
(CONSTRAINTS.md's note on check_llms_coverage.py's ENFORCE toggle, and
10-review-persona-and-standards.md's "a gate that is not a gate"). So every
failure mode below is asserted to actually produce a non-zero exit code, not
merely to populate an issues list.

Run with:
    pytest tests/test_check_code_quality.py -v
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

SCRIPT_DIR = SCRIPTS_DIR
import check_code_quality as checker  # noqa: E402


def measure_one(source: str):
    """Measure a single synthetic module named mod.py."""
    return checker.measure_source(source, "mod.py")


class ComplexityTest(unittest.TestCase):
    def test_straight_line_function_has_complexity_one(self):
        functions, _, _ = measure_one("def f():\n    return 1\n")
        self.assertEqual(functions["mod.py::f"]["complexity"], 1)

    def test_each_if_adds_one_branch(self):
        source = "def f(a):\n    if a:\n        return 1\n    if a > 2:\n        return 2\n    return 3\n"
        functions, _, _ = measure_one(source)
        self.assertEqual(functions["mod.py::f"]["complexity"], 3)

    def test_and_chain_counts_each_extra_operand(self):
        """`a and b and c` is two decisions, not one -- a reader evaluates
        both. This is where this metric deliberately exceeds textbook
        McCabe, so it is pinned rather than left implicit."""
        functions, _, _ = measure_one("def f(a, b, c):\n    return a and b and c\n")
        self.assertEqual(functions["mod.py::f"]["complexity"], 3)

    def test_comprehension_filter_counts_beyond_the_comprehension_itself(self):
        functions, _, _ = measure_one("def f(xs):\n    return [x for x in xs if x if x > 1]\n")
        self.assertEqual(functions["mod.py::f"]["complexity"], 4)


class NestingDepthTest(unittest.TestCase):
    def test_flat_function_has_depth_zero(self):
        functions, _, _ = measure_one("def f():\n    return 1\n")
        self.assertEqual(functions["mod.py::f"]["depth"], 0)

    def test_nested_blocks_accumulate_depth(self):
        source = (
            "def f(xs):\n"
            "    for x in xs:\n"
            "        if x:\n"
            "            with open(x) as h:\n"
            "                return h\n"
        )
        functions, _, _ = measure_one(source)
        self.assertEqual(functions["mod.py::f"]["depth"], 3)

    def test_sequential_blocks_do_not_accumulate_depth(self):
        """Two `if`s in a row are depth 1, not 2 -- the metric measures
        containment, which is what a reader has to hold on the stack, not
        the number of blocks."""
        source = "def f(a):\n    if a:\n        pass\n    if a:\n        pass\n"
        functions, _, _ = measure_one(source)
        self.assertEqual(functions["mod.py::f"]["depth"], 1)

    def test_nested_function_depth_belongs_to_itself_not_its_parent(self):
        source = (
            "def outer(xs):\n"
            "    def inner(ys):\n"
            "        for y in ys:\n"
            "            if y:\n"
            "                return y\n"
            "    return inner\n"
        )
        functions, _, _ = measure_one(source)
        self.assertEqual(functions["mod.py::outer"]["depth"], 0)
        self.assertEqual(functions["mod.py::outer.inner"]["depth"], 2)


class QualnameTest(unittest.TestCase):
    def test_method_is_keyed_by_class_and_name(self):
        functions, _, _ = measure_one("class C:\n    def m(self):\n        return 1\n")
        self.assertIn("mod.py::C.m", functions)

    def test_function_defined_inside_an_if_is_still_found(self):
        functions, _, _ = measure_one("import os\nif os.name:\n    def f():\n        return 1\n")
        self.assertIn("mod.py::f", functions)

    def test_duplicate_qualname_keeps_the_worse_measurement(self):
        """A conditional def gives one key two measurements. Keeping the
        worse one is the safe direction: the ratchet must not be loosened by
        a definition the interpreter may never execute."""
        source = (
            "import os\n"
            "if os.name:\n"
            "    def f(a):\n"
            "        return 1\n"
            "else:\n"
            "    def f(a):\n"
            "        if a:\n"
            "            if a > 1:\n"
            "                return 2\n"
            "        return 3\n"
        )
        functions, _, _ = measure_one(source)
        self.assertEqual(functions["mod.py::f"]["complexity"], 3)
        self.assertEqual(functions["mod.py::f"]["depth"], 2)


class AnnotationCoverageTest(unittest.TestCase):
    def test_return_annotation_alone_counts_as_annotated(self):
        _, total, annotated = measure_one("def f(a) -> int:\n    return a\n")
        self.assertEqual((total, annotated), (1, 1))

    def test_one_annotated_parameter_counts_as_annotated(self):
        _, total, annotated = measure_one("def f(a: int, b):\n    return a\n")
        self.assertEqual((total, annotated), (1, 1))

    def test_bare_function_does_not_count(self):
        _, total, annotated = measure_one("def f(a, b):\n    return a\n")
        self.assertEqual((total, annotated), (1, 0))

    def test_self_alone_does_not_make_a_method_annotated(self):
        """Nobody annotates `self`; counting it would let a method claim
        coverage it does not have."""
        _, total, annotated = measure_one("class C:\n    def m(self):\n        return 1\n")
        self.assertEqual((total, annotated), (1, 0))


class RatchetTest(unittest.TestCase):
    """The failure modes, each asserted to reach a non-zero exit code."""

    def _tree(self, tmp: str, source: str) -> Path:
        scripts = Path(tmp) / "scripts"
        scripts.mkdir(exist_ok=True)
        (scripts / "mod.py").write_text(source, encoding="utf-8")
        return scripts

    SIMPLE = "def f(a):\n    if a:\n        return 1\n    return 2\n"

    def test_unchanged_tree_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = self._tree(tmp, self.SIMPLE)
            baseline = checker.measure_tree(scripts)
            self.assertEqual(checker.compare(baseline, checker.measure_tree(scripts)), [])
            self.assertEqual(checker.exit_code([]), 0)

    def test_a_function_growing_more_complex_is_advisory_not_hard(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = self._tree(tmp, self.SIMPLE)
            baseline = checker.measure_tree(scripts)
            (scripts / "mod.py").write_text(
                "def f(a):\n    if a:\n        return 1\n    if a > 1:\n        return 3\n    return 2\n",
                encoding="utf-8")
            current = checker.measure_tree(scripts)
            self.assertEqual(checker.compare(baseline, current), [])
            advisories = checker.size_advisories(baseline, current)
            self.assertTrue(any("complexity" in i for i in advisories), advisories)
            self.assertEqual(checker.exit_code(checker.compare(baseline, current)), 0)

    def test_a_function_doing_more_is_advisory_not_hard(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = self._tree(tmp, self.SIMPLE)
            baseline = checker.measure_tree(scripts)
            body = "\n".join(f"    x{i} = {i}" for i in range(20))
            (scripts / "mod.py").write_text(
                f"def f(a):\n{body}\n    if a:\n        return 1\n    return 2\n", encoding="utf-8")
            current = checker.measure_tree(scripts)
            self.assertEqual(checker.compare(baseline, current), [])
            advisories = checker.size_advisories(baseline, current)
            self.assertTrue(any("statements" in i for i in advisories), advisories)
            self.assertEqual(checker.exit_code([]), 0)

    def test_adding_comments_is_not_a_regression(self):
        """The metric is statements, not line span, precisely so that
        documenting a subtle piece of code does not read as making it worse.
        This repo is 38-54% prose in its larger modules; a gate that fires on
        a new comment block is a gate that gets deleted."""
        with tempfile.TemporaryDirectory() as tmp:
            scripts = self._tree(tmp, self.SIMPLE)
            baseline = checker.measure_tree(scripts)
            commentary = "\n".join(f"    # explanatory line {i}" for i in range(30))
            (scripts / "mod.py").write_text(
                f"def f(a):\n{commentary}\n    if a:\n        return 1\n    return 2\n",
                encoding="utf-8")
            self.assertEqual(checker.compare(baseline, checker.measure_tree(scripts)), [])

    def test_a_docstring_does_not_count_as_a_statement(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = self._tree(tmp, "def f(a):\n    return a\n")
            bare = checker.measure_tree(scripts)["functions"]["mod.py::f"]["statements"]
            (scripts / "mod.py").write_text(
                'def f(a):\n    """Now documented."""\n    return a\n', encoding="utf-8")
            documented = checker.measure_tree(scripts)["functions"]["mod.py::f"]["statements"]
            self.assertEqual(bare, documented)

    def test_a_nested_functions_body_is_not_counted_in_its_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = self._tree(tmp, "def outer():\n    def inner():\n        return 1\n    return inner\n")
            functions = checker.measure_tree(scripts)["functions"]
            # outer counts one statement: the `return`. The nested `def` is
            # skipped rather than counted, because inner has its own entry
            # below -- otherwise growing inner would regress outer too.
            self.assertEqual(functions["mod.py::outer"]["statements"], 1)
            self.assertEqual(functions["mod.py::outer.inner"]["statements"], 1)

    def test_a_function_getting_simpler_passes_and_does_not_auto_tighten(self):
        """Improvement is allowed without --update, but it does not silently
        become the new floor -- otherwise a refactor followed by a revert
        would fail for no reason the author could see."""
        with tempfile.TemporaryDirectory() as tmp:
            scripts = self._tree(tmp, self.SIMPLE)
            baseline = checker.measure_tree(scripts)
            (scripts / "mod.py").write_text("def f(a):\n    return 2\n", encoding="utf-8")
            self.assertEqual(checker.compare(baseline, checker.measure_tree(scripts)), [])

    def test_a_new_function_worse_than_anything_is_advisory_not_hard(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = self._tree(tmp, self.SIMPLE)
            baseline = checker.measure_tree(scripts)
            (scripts / "mod.py").write_text(
                self.SIMPLE
                + "def g(a, b, c, d):\n"
                + "    if a:\n        if b:\n            if c:\n                if d:\n                    return 1\n"
                + "    return 0\n",
                encoding="utf-8")
            current = checker.measure_tree(scripts)
            self.assertEqual(checker.compare(baseline, current), [])
            advisories = checker.size_advisories(baseline, current)
            self.assertTrue(any("new function" in i for i in advisories), advisories)

    def test_a_new_function_within_existing_limits_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = self._tree(tmp, self.SIMPLE)
            baseline = checker.measure_tree(scripts)
            (scripts / "mod.py").write_text(self.SIMPLE + "def g(a):\n    return a\n",
                                            encoding="utf-8")
            self.assertEqual(checker.compare(baseline, checker.measure_tree(scripts)), [])

    def test_dropping_type_annotations_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = self._tree(tmp, "def f(a: int) -> int:\n    return a\n")
            baseline = checker.measure_tree(scripts)
            (scripts / "mod.py").write_text("def f(a):\n    return a\n", encoding="utf-8")
            issues = checker.compare(baseline, checker.measure_tree(scripts))
            self.assertTrue(any("annotation coverage fell" in i for i in issues), issues)
            self.assertEqual(checker.exit_code(issues), 1)

    def test_deleting_a_function_is_not_a_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = self._tree(tmp, self.SIMPLE + "def g(a):\n    return a\n")
            baseline = checker.measure_tree(scripts)
            (scripts / "mod.py").write_text(self.SIMPLE, encoding="utf-8")
            self.assertEqual(checker.compare(baseline, checker.measure_tree(scripts)), [])

    def test_an_unparseable_file_is_reported_rather_than_skipped_silently(self):
        """A syntax error must not read as "nothing to measure here." Silent
        truncation reading as completeness is on this repo's own
        anti-pattern list."""
        with tempfile.TemporaryDirectory() as tmp:
            scripts = self._tree(tmp, self.SIMPLE)
            baseline = checker.measure_tree(scripts)
            (scripts / "broken.py").write_text("def f(:\n", encoding="utf-8")
            issues = checker.compare(baseline, checker.measure_tree(scripts))
            self.assertTrue(any("could not parse" in i for i in issues), issues)
            self.assertEqual(checker.exit_code(issues), 1)


class TrackedFilesOnlyTest(unittest.TestCase):
    """The baseline is a committed artifact, so it must describe the committed
    tree -- not whatever happens to be sitting in the working directory.

    This is a regression test for a real incident: regenerating the baseline
    while a concurrent session's untracked files were present absorbed 93 of
    their functions and raised the annotation floor above what the committed
    tree could meet, which would have failed CI on its first run while blaming
    files that were never committed."""

    def _git(self, cwd, *args):
        subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)

    def test_untracked_file_is_not_measured(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._git(repo, "init", "-q")
            scripts = repo / "scripts"
            scripts.mkdir()
            (scripts / "tracked.py").write_text("def a():\n    return 1\n", encoding="utf-8")
            self._git(repo, "add", "scripts/tracked.py")
            self._git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

            (scripts / "untracked.py").write_text("def b():\n    return 2\n", encoding="utf-8")

            measured = checker.measure_tree(scripts)
            keys = list(measured["functions"])
            self.assertIn("tracked.py::a", keys)
            self.assertNotIn("untracked.py::b", keys,
                             "an untracked file leaked into a committed artifact")

    def test_falls_back_to_glob_outside_a_git_checkout(self):
        """An exported tarball has no .git; the script must still work rather
        than silently measuring nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            scripts.mkdir()
            (scripts / "mod.py").write_text("def a():\n    return 1\n", encoding="utf-8")
            self.assertIn("mod.py::a", checker.measure_tree(scripts)["functions"])

    def test_nested_fixture_python_files_are_not_measured(self):
        """scripts/test_fixtures/ holds fixture sources, not modules of this
        tool; measuring them would ratchet somebody else's sample code."""
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            (scripts / "test_fixtures").mkdir(parents=True)
            (scripts / "mod.py").write_text("def a():\n    return 1\n", encoding="utf-8")
            (scripts / "test_fixtures" / "sample.py").write_text(
                "def fixture():\n    return 1\n", encoding="utf-8")
            keys = list(checker.measure_tree(scripts)["functions"])
            self.assertIn("mod.py::a", keys)
            self.assertNotIn("sample.py::fixture", keys)


class DocstringContractTest(unittest.TestCase):
    """The orientation contract from CONTRIBUTING.md: a runnable module says
    how to run it near the top.

    The exemption test matters more than the violation tests. A check that
    demanded a Usage block from an imported-only module would be pointed at
    the wrong thing, and would push four library modules to invent a command
    they do not have -- this repo's own "a validator that validates fixtures"
    anti-pattern, one step removed."""

    MAIN = '\n\nif __name__ == "__main__":\n    pass\n'

    def test_usage_near_the_top_passes(self):
        source = '"""One line.\n\nUsage:\n    python3 mod.py\n"""' + self.MAIN
        self.assertIsNone(checker.docstring_violation(source, "mod.py"))

    def test_run_with_is_accepted_too(self):
        """The repo already uses both spellings; the contract is about the
        reader finding it, not about one exact word."""
        source = '"""One line.\n\nRun with:\n    python3 mod.py\n"""' + self.MAIN
        self.assertIsNone(checker.docstring_violation(source, "mod.py"))

    def test_usage_buried_below_the_threshold_is_flagged(self):
        filler = "\n".join(f"line {i}" for i in range(30))
        source = f'"""One line.\n\n{filler}\n\nUsage:\n    python3 mod.py\n"""' + self.MAIN
        violation = checker.docstring_violation(source, "mod.py")
        self.assertIsNotNone(violation)
        self.assertIn("docstring line", violation)

    def test_runnable_module_with_no_usage_at_all_is_flagged(self):
        source = '"""One line.\n\nSome rationale, but no command anywhere.\n"""' + self.MAIN
        violation = checker.docstring_violation(source, "mod.py")
        self.assertIsNotNone(violation)
        self.assertIn("never says how to run it", violation)

    def test_runnable_module_with_no_docstring_is_flagged(self):
        violation = checker.docstring_violation("x = 1" + self.MAIN, "mod.py")
        self.assertIsNotNone(violation)
        self.assertIn("no module docstring", violation)

    def test_library_module_without_a_cli_is_exempt(self):
        """doc_tag_utils.py and the three underscore helpers are imported and
        never run. They must not be asked for a command."""
        source = '"""A shared constant table.\n\nLong rationale, no command, correctly.\n"""\nX = 1\n'
        self.assertIsNone(checker.docstring_violation(source, "lib.py"))

    def test_a_main_string_that_is_not_the_guard_does_not_count(self):
        """`"__main__"` inside a docstring or an error message must not make a
        library module look runnable."""
        source = '"""Mentions __main__ in prose only."""\nMSG = "see __main__"\n'
        self.assertIsNone(checker.docstring_violation(source, "lib.py"))

    def test_syntax_error_defers_rather_than_double_reporting(self):
        """measure_tree already reports unparseable files; this check stays
        quiet so one broken file does not produce two findings."""
        self.assertIsNone(checker.docstring_violation("def f(:\n", "broken.py"))

    def test_a_new_violation_fails_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            scripts.mkdir()
            good = '"""One line.\n\nUsage:\n    python3 mod.py\n"""' + self.MAIN
            (scripts / "mod.py").write_text(good, encoding="utf-8")
            baseline = checker.measure_tree(scripts)
            self.assertEqual(baseline["docstring_violations"], {})

            filler = "\n".join(f"line {i}" for i in range(30))
            (scripts / "mod.py").write_text(
                f'"""One line.\n\n{filler}\n\nUsage:\n    python3 mod.py\n"""' + self.MAIN,
                encoding="utf-8")
            issues = checker.compare(baseline, checker.measure_tree(scripts))
            self.assertTrue(any("docstring contract" in i for i in issues), issues)
            self.assertEqual(checker.exit_code(issues), 1)

    def test_a_baselined_violation_does_not_fail_the_gate(self):
        """The ratchet's whole point: modules predating the rule are recorded,
        not blocking."""
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            scripts.mkdir()
            bad = '"""One line.\n\nNo command here.\n"""' + self.MAIN
            (scripts / "mod.py").write_text(bad, encoding="utf-8")
            baseline = checker.measure_tree(scripts)
            self.assertIn("mod.py", baseline["docstring_violations"])
            self.assertEqual(checker.compare(baseline, checker.measure_tree(scripts)), [])

    def test_violations_are_compared_by_module_not_by_message(self):
        """The messages carry line numbers. If comparison used them, shifting
        an unrelated line in an already-violating module would report a new
        violation."""
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            scripts.mkdir()
            filler = "\n".join(f"line {i}" for i in range(30))
            (scripts / "mod.py").write_text(
                f'"""One line.\n\n{filler}\n\nUsage:\n    python3 mod.py\n"""' + self.MAIN,
                encoding="utf-8")
            baseline = checker.measure_tree(scripts)

            longer = "\n".join(f"line {i}" for i in range(40))
            (scripts / "mod.py").write_text(
                f'"""One line.\n\n{longer}\n\nUsage:\n    python3 mod.py\n"""' + self.MAIN,
                encoding="utf-8")
            current = checker.measure_tree(scripts)
            self.assertNotEqual(baseline["docstring_violations"]["mod.py"],
                                current["docstring_violations"]["mod.py"])
            self.assertEqual(checker.compare(baseline, current), [])


class BaselineRoundTripTest(unittest.TestCase):
    def test_baseline_survives_a_json_round_trip(self):
        """compare() runs against JSON-loaded data in production, where dict
        key order and int/str typing can differ from the in-memory object."""
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            scripts.mkdir()
            (scripts / "mod.py").write_text("def f(a):\n    return a\n", encoding="utf-8")
            path = Path(tmp) / "baseline.json"
            checker.write_baseline(path, checker.measure_tree(scripts))
            reloaded = checker.load_baseline(path)
            self.assertIsNotNone(reloaded)
            self.assertEqual(checker.compare(reloaded, checker.measure_tree(scripts)), [])

    def test_measurement_is_byte_stable_across_runs(self):
        """The baseline is committed and diffed; an unstable serialization
        would make every regeneration look like a change."""
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            scripts.mkdir()
            (scripts / "b.py").write_text("def b():\n    return 1\n", encoding="utf-8")
            (scripts / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
            first = Path(tmp) / "one.json"
            second = Path(tmp) / "two.json"
            checker.write_baseline(first, checker.measure_tree(scripts))
            checker.write_baseline(second, checker.measure_tree(scripts))
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_function_keys_are_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            scripts.mkdir()
            (scripts / "mod.py").write_text(
                "def z():\n    return 1\ndef a():\n    return 1\n", encoding="utf-8")
            keys = list(checker.measure_tree(scripts)["functions"])
            self.assertEqual(keys, sorted(keys))

    def test_a_missing_baseline_is_a_usage_error_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(checker.load_baseline(Path(tmp) / "absent.json"))


class CommittedBaselineTest(unittest.TestCase):
    def test_the_committed_baseline_matches_the_current_tree(self):
        """The real gate, run against this repo. If this fails, either
        annotation/docstring coverage regressed or the baseline needs
        --update -- the message says which."""
        baseline = checker.load_baseline(checker.DEFAULT_BASELINE)
        self.assertIsNotNone(baseline, "no committed baseline; run with --update")
        self.assertEqual(baseline.get("schema_version"), checker.SCHEMA_VERSION)
        current = checker.measure_tree(
            SCRIPT_DIR,
            extra_roots=[SCRIPT_DIR, SCRIPT_DIR.parent / "src" / "doc_engine"],
            repo_root=SCRIPT_DIR.parent,
        )
        issues = checker.compare(baseline, current)
        self.assertEqual(issues, [], "\n".join(issues))


if __name__ == "__main__":
    unittest.main()
