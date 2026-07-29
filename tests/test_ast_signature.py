#!/usr/bin/env python3
"""
Tests for _ast_signature.py.

These are the evidence for a design decision, kept executable. The choice of
t2 as the default was made from measurements taken in a throwaway script --
and a measurement made once in a scratch file decays exactly the way a claim
written in prose does, which is the failure this whole subsystem exists to
stop. So every measurement that justified the decision is a test here, and
re-runs on every commit rather than resting on a number in a commit message.

Written to skills/directional-tests/SKILL.md: each test names the property it
defends, and the ones that matter would go red if the property broke rather
than if a line stopped executing.

Run with:
    python3 scripts/test_ast_signature.py -v
"""

import ast
import pathlib
import sys
import tempfile
import unittest
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

import _ast_signature as sig  # noqa: E402

BASE = 'def f(x):\n    """Does a thing."""\n    return x + 1\n'


class NormalizationMatrixTest(unittest.TestCase):
    """One test per row of the measured matrix. Together these are the
    argument for the levels existing at all: if any two rows behaved alike,
    the level tag would be decoration."""

    def test_reformatting_does_not_move_t1(self):
        """The property that decides adoption. A checker that fires when
        someone runs a formatter is a checker that gets switched off, so this
        matters more than detection sensitivity."""
        spaced = 'def f(x):\n    """Does a thing."""\n    return x+1\n'
        self.assertEqual(sig.signature_of_source(BASE, "t1"),
                         sig.signature_of_source(spaced, "t1"))

    def test_adding_a_comment_does_not_move_t1(self):
        """Comments are Type-1 by definition and never enter the AST."""
        commented = 'def f(x):\n    """Does a thing."""\n    # why\n    return x + 1\n'
        self.assertEqual(sig.signature_of_source(BASE, "t1"),
                         sig.signature_of_source(commented, "t1"))

    def test_a_docstring_edit_moves_t1_but_not_t2(self):
        """The whole reason two levels exist. If this ever passes trivially --
        both moving, or neither -- the levels encode nothing and the extra
        machinery should be deleted rather than kept for symmetry."""
        reworded = 'def f(x):\n    """Adds one to x."""\n    return x + 1\n'
        self.assertNotEqual(sig.signature_of_source(BASE, "t1"),
                            sig.signature_of_source(reworded, "t1"),
                            "t1 must notice a docstring edit")
        self.assertEqual(sig.signature_of_source(BASE, "t2"),
                         sig.signature_of_source(reworded, "t2"),
                         "t2 must ignore a docstring edit")

    def test_a_semantic_change_moves_both_levels(self):
        """Non-vacuity for the whole module. A signature that never moves
        detects nothing, and every other test here would still pass."""
        changed = 'def f(x):\n    """Does a thing."""\n    return x + 2\n'
        for level in ("t1", "t2"):
            self.assertNotEqual(sig.signature_of_source(BASE, level),
                                sig.signature_of_source(changed, level),
                                f"{level} missed a behaviour change")

    def test_raw_byte_hashing_would_fire_on_reformatting(self):
        """Kept as executable justification for NOT reusing
        spring_signal_scan.compute_file_signature, which is a raw-byte hash by
        design. A comment saying 'raw hashing is too brittle' decays; this
        fails if it ever stops being true."""
        spaced = 'def f(x):\n    """Does a thing."""\n    return x+1\n'
        self.assertNotEqual(sig.signature_of_source(BASE, "raw"),
                            sig.signature_of_source(spaced, "raw"))


class LevelIsPartOfTheDataTest(unittest.TestCase):
    """A digest without its relation is not comparable to anything."""

    def test_t1_and_t2_differ_across_real_modules(self):
        """Measured at 0 agreements across 14 modules. If these ever collide
        the level tag stops carrying information -- so this is the test that
        justifies storing the level at all, not a coincidence worth asserting."""
        modules = sorted(SCRIPTS_DIR.glob("*.py"))[:14]
        self.assertGreater(len(modules), 5, "not enough modules to be meaningful")
        collisions = [
            p.name for p in modules
            if sig.signature(p, "t1").split(":")[1] == sig.signature(p, "t2").split(":")[1]
        ]
        self.assertEqual(collisions, [], f"t1 and t2 agreed on: {collisions}")

    def test_a_signature_always_carries_its_level(self):
        for level in ("raw", "t1", "t2"):
            self.assertTrue(sig.signature_of_source(BASE, level).startswith(f"{level}:"))

    def test_an_unknown_level_is_rejected(self):
        """A level nobody implemented must not quietly become a different
        relation -- the caller would compare incomparable digests and believe
        the result."""
        with self.assertRaises(ValueError):
            sig.signature_of_source(BASE, "t3")

    def test_a_bare_digest_cannot_be_interpreted(self):
        """Signatures predating this module have no level. Reading one must
        fail loudly rather than guessing which relation produced it."""
        with self.assertRaises(ValueError):
            sig.split_signature("deadbeef")

    def test_split_round_trips(self):
        level, digest = sig.split_signature(sig.signature_of_source(BASE, "t1"))
        self.assertEqual(level, "t1")
        self.assertEqual(len(digest), 64)


class RealModuleTest(unittest.TestCase):
    """Against this repo's own files. A toy fixture can satisfy the matrix
    above while proving nothing about the codebase the decision was made for."""

    def test_a_docstring_only_edit_to_a_real_module_does_not_move_t2(self):
        """The PR #49 case, generalised. That PR changed 18/12/11 docstring
        lines across three modules with zero changed lines outside the
        docstring; under t1 it would have staled every claim about them. This
        applies the same edit to a real module rather than a toy."""
        target = REPO_ROOT / "src" / "doc_engine" / "tools" / "citation_coverage.py"
        source = target.read_text(encoding="utf-8")
        tree = ast.parse(source)
        original = ast.get_docstring(tree)
        self.assertIsNotNone(original, "fixture module has no docstring to edit")

        rewritten = source.replace(original, "Completely different prose.", 1)
        self.assertNotEqual(rewritten, source, "the edit did not apply")

        self.assertEqual(sig.signature_of_source(source, "t2"),
                         sig.signature_of_source(rewritten, "t2"),
                         "t2 moved on a docstring-only edit to a real module")
        self.assertNotEqual(sig.signature_of_source(source, "t1"),
                            sig.signature_of_source(rewritten, "t1"),
                            "t1 should notice it, or the levels are identical here")

    def test_a_non_python_subject_is_hashed_raw_and_says_so(self):
        """Silently honouring a t2 request for an unparsed file would return a
        label asserting a normalization that never happened."""
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "notes.md"
            path.write_text("# not python\n", encoding="utf-8")
            self.assertTrue(sig.signature(path, "t2").startswith("raw:"))

    def test_the_default_level_is_t2(self):
        """Pinned because the default is the decision, not an implementation
        detail: it was t1 until measurement overturned it."""
        self.assertEqual(sig.DEFAULT_LEVEL, "t2")
        self.assertTrue(sig.signature_of_source(BASE).startswith("t2:"))


if __name__ == "__main__":
    unittest.main()
