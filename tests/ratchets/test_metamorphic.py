#!/usr/bin/env python3
"""Metamorphic relations over the evidence set, across input type and velocity.

The property defended: **when the input changes in a known way, the output set
must change in the way that implies -- and in no other way.** Each test names
its relation, so a failure says which invariant broke under which shape of
input, rather than reporting that a number moved.

Not covered by sibling suites. tests/ratchets/test_set_delta.py pins what the relations mean
(pure set arithmetic, no scanning). tests/ratchets/test_drift_normalization.py measures a
false-positive RATE for the drift comparator over four Java perturbations.
Neither asks whether the scanner itself holds these invariants, and two of its
stated bounds are closed here -- claude/drift-normalization-measurement-2026-07-25.md
records "Only Java is perturbed" and "No encoding or line-ending perturbation".

Two axes, both deliberate:

  TYPE      java, .gradle, .properties, yaml, empty, malformed, BOM, CRLF,
            unicode filename -- what the input IS.
  VELOCITY  one edit, bulk rename, sustained churn, append-only growth, mass
            deletion, re-scan, whole-tree duplication -- how FAST and how
            BROADLY it changes.

Velocity matters separately from type because the failures differ: a single
edit tests locality, a bulk rename tests that locality still holds at scale,
and repeated application tests idempotence, which nothing here asserted before
(the word appears in no other suite).

Java transforms come from java_perturbations.FORMATTING_ONLY rather than being
rewritten, so the meaning-preserving guarantee is the one that module already
argues for.

Run with: pytest tests/ratchets/test_metamorphic.py -v
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

FIXTURES = SCRIPTS_DIR / "coverage" / "rule_fixtures"

import java_perturbations as perturb  # noqa: E402
import set_delta as sd  # noqa: E402
_TMP: Path = None  # type: ignore[assignment]
BASE: Path = None  # type: ignore[assignment]
BASE_SET = None


def setUpModule() -> None:
    """One reference corpus and one reference scan, reused by every case.
    Each scan shells out to ast-grep, so rescanning per test would multiply
    the suite's runtime for no additional assurance."""
    global _TMP, BASE, BASE_SET
    _TMP = Path(tempfile.mkdtemp(prefix="metamorphic_"))
    BASE = _TMP / "base"
    shutil.copytree(FIXTURES, BASE)
    BASE_SET = sd.signals_set(BASE)
    if not BASE_SET:
        raise AssertionError(
            "the reference scan found nothing; every relation below would hold "
            "vacuously against an empty set")


def tearDownModule() -> None:
    shutil.rmtree(_TMP, ignore_errors=True)


class CorpusCase(unittest.TestCase):
    """Each test gets its own copy, so a mutation cannot leak sideways."""

    def variant(self) -> Path:
        target = Path(tempfile.mkdtemp(prefix="variant_", dir=_TMP)) / "repo"
        shutil.copytree(BASE, target)
        return target

    def assertRelation(self, repo: Path, relation, msg: str = "") -> None:
        residue = sd.classify(sd.delta(BASE_SET, sd.signals_set(repo)), relation)
        if not residue.is_empty():
            self.fail(f"{msg}\nunexplained:\n" + "\n".join(residue.describe()))


# ---------------------------------------------------------------------------
# TYPE axis
# ---------------------------------------------------------------------------

class FormattingIsMeaningPreservingTest(CorpusCase):
    """Every FORMATTING_ONLY transform must leave the set untouched -- except
    the one this repo has already flagged as unresolved, which is asserted
    separately below rather than skipped."""

    KNOWN_MOVES_THE_SET = "wrap_annotation_args"

    def _apply(self, name: str) -> Path:
        repo = self.variant()
        transform = perturb.FORMATTING_ONLY[name]
        for java in repo.glob("*.java"):
            java.write_text(transform(java.read_text(encoding="utf-8")),
                            encoding="utf-8")
        return repo

    def test_each_formatting_transform_changes_nothing(self) -> None:
        for name in perturb.FORMATTING_ONLY:
            if name == self.KNOWN_MOVES_THE_SET:
                continue
            with self.subTest(transform=name):
                self.assertRelation(self._apply(name), sd.unchanged(),
                                    f"{name} moved the evidence set")

    def test_wrapping_annotation_args_still_moves_the_set(self) -> None:
        """A ratchet on a known defect, asserted in the direction that is
        true today so it fails in BOTH directions.

        CONSTRAINTS.md's "Known precision tradeoffs" records this as flagged
        and unresolved: the stored `match` is only the matched node's first
        line, so splitting `@GetMapping("/x")` across lines leaves
        `@GetMapping(` behind and the member no longer compares equal. This
        suite reproduced it independently, from the scanner side rather than
        the drift-comparator side.

        **If this test starts failing, the defect was fixed.** Delete it and
        fold wrap_annotation_args back into the loop above -- do not adjust
        it to keep passing.
        """
        residue = sd.classify(
            sd.delta(BASE_SET, sd.signals_set(self._apply(self.KNOWN_MOVES_THE_SET))),
            sd.unchanged())
        self.assertFalse(
            residue.is_empty(),
            "wrap_annotation_args no longer moves the set -- the first-line "
            "match defect appears fixed; see this test's docstring")


class EncodingAndLineEndingsTest(CorpusCase):
    """Closes a bound test_drift_normalization states it does not cover:
    'No encoding or line-ending perturbation.'"""

    def test_crlf_line_endings_change_nothing(self) -> None:
        repo = self.variant()
        for java in repo.glob("*.java"):
            raw = java.read_text(encoding="utf-8").replace("\n", "\r\n")
            java.write_bytes(raw.encode("utf-8"))
        self.assertRelation(repo, sd.unchanged(), "CRLF moved the evidence set")

    def test_a_utf8_bom_changes_nothing(self) -> None:
        repo = self.variant()
        for java in repo.glob("*.java"):
            java.write_bytes(b"\xef\xbb\xbf" + java.read_bytes())
        self.assertRelation(repo, sd.unchanged(), "a BOM moved the evidence set")


class IrrelevantFileTypesTest(CorpusCase):
    """Adding a file no Java rule can match must not move Java members."""

    def test_an_empty_file_adds_nothing(self) -> None:
        repo = self.variant()
        (repo / "Empty.java").write_text("", encoding="utf-8")
        self.assertRelation(repo, sd.unchanged(), "an empty file moved the set")

    def test_a_unicode_filename_is_handled(self) -> None:
        repo = self.variant()
        (repo / "Ünïcode.txt").write_text("nothing structural\n", encoding="utf-8")
        self.assertRelation(repo, sd.unchanged(), "a unicode filename moved the set")

    def test_unparseable_java_does_not_disturb_its_siblings(self) -> None:
        """A file ast-grep cannot parse must not take the rest of the corpus
        with it. Locality under a hostile input, not just a benign one."""
        repo = self.variant()
        (repo / "Broken.java").write_text("public class {{{ <<< not java\n",
                                          encoding="utf-8")
        self.assertRelation(repo, sd.confined_to(["Broken.java"]),
                            "an unparseable file disturbed other files")


class BuildFileTypeTest(CorpusCase):
    """The .gradle axis.

    These get a filename-level bucket entry and no structural signals, since
    ast-grep has no Groovy grammar. So the correct relation is confinement to
    the file itself, NOT `unchanged` -- adding one genuinely does add a
    member. Writing `unchanged` here first is what made that concrete: the
    test failed, and it was the test that was wrong, not the scanner.
    """

    def test_adding_a_gradle_file_moves_only_itself(self) -> None:
        repo = self.variant()
        (repo / "build.gradle").write_text(
            'dependencies { implementation("org.springframework.boot:x") }\n',
            encoding="utf-8")
        self.assertRelation(repo, sd.confined_to(["build.gradle"]),
                            "a .gradle file moved a member of another file")

    def test_adding_a_properties_file_moves_only_itself(self) -> None:
        repo = self.variant()
        (repo / "gradle.properties").write_text("repoPassword=literal\n",
                                                encoding="utf-8")
        self.assertRelation(repo, sd.confined_to(["gradle.properties"]),
                            "a .properties file moved a member of another file")

    def test_a_gradle_file_contributes_no_structural_rule(self) -> None:
        """The consequence of the missing Groovy grammar, asserted rather
        than assumed: whatever a .gradle file contributes, it is not a hit
        from one of the Java rules in spring_ast_grep_rules.yml."""
        repo = self.variant()
        (repo / "build.gradle").write_text("@RestController\n@Entity\n",
                                           encoding="utf-8")
        added = sd.delta(BASE_SET, sd.signals_set(repo)).added
        for member in added:
            self.assertNotIn("__", member.rule_id,
                             f"a .gradle file produced a structural rule hit: {member}")


# ---------------------------------------------------------------------------
# VELOCITY axis
# ---------------------------------------------------------------------------

class SingleEditLocalityTest(CorpusCase):
    def test_one_file_edited_moves_only_that_file(self) -> None:
        repo = self.variant()
        target = repo / "ApiSurface.java"
        target.write_text(target.read_text(encoding="utf-8")
                          .replace("@RestController", "@RestController\n@Timed", 1),
                          encoding="utf-8")
        self.assertRelation(repo, sd.confined_to(["ApiSurface.java"]),
                            "a one-file edit reached other files")


class BulkRenameTest(CorpusCase):
    """Locality at scale. A rename moves every member of the renamed file,
    so the relation is confinement to the union of old and new names."""

    def test_renaming_every_file_confines_movement_to_those_names(self) -> None:
        repo = self.variant()
        affected = []
        for java in sorted(repo.glob("*.java")):
            new = java.with_name(f"Renamed{java.name}")
            affected += [java.name, new.name]
            java.rename(new)
        self.assertRelation(repo, sd.confined_to(affected),
                            "a bulk rename moved members of untouched files")


class ChurnIsIdempotentTest(CorpusCase):
    """Sustained churn. Applying a meaning-preserving edit k times must land
    in the same place as applying it once -- idempotence, which no other
    suite in this repo asserts by name."""

    REPEATS = 5

    def test_repeated_reindent_is_stable(self) -> None:
        repo = self.variant()
        seen = []
        for _ in range(self.REPEATS):
            for java in repo.glob("*.java"):
                java.write_text(perturb.reindent(java.read_text(encoding="utf-8")),
                                encoding="utf-8")
            seen.append(sd.signals_set(repo))
        self.assertEqual(len(set(seen)), 1, "the set moved between churn rounds")
        self.assertRelation(repo, sd.unchanged(),
                            f"{self.REPEATS} rounds of reindent moved the set")


class AppendOnlyGrowthTest(CorpusCase):
    def test_adding_files_only_grows_the_set(self) -> None:
        repo = self.variant()
        for i in range(3):
            (repo / f"Added{i}.java").write_text(
                f"package fx;\n@RestController\npublic class Added{i} {{}}\n",
                encoding="utf-8")
        self.assertRelation(repo, sd.grows_only(),
                            "adding files removed an existing member")


class MassDeletionTest(CorpusCase):
    def test_deleting_files_removes_only_their_members(self) -> None:
        repo = self.variant()
        removed = [p.name for p in sorted(repo.glob("*.java"))[:3]]
        for name in removed:
            (repo / name).unlink()
        self.assertRelation(repo, sd.confined_to(removed),
                            "deleting files disturbed the survivors")


class RescanDeterminismTest(CorpusCase):
    """An invariant, not a probe: two scans of an unchanged tree must be
    equal as sets. Stated because directional-tests rule 4 records a
    re-run-and-diff probe passing against an unfixed scanner."""

    def test_two_scans_of_the_same_tree_agree(self) -> None:
        self.assertEqual(sd.signals_set(BASE), BASE_SET)


class DuplicationScalesTest(CorpusCase):
    """Whole-tree duplication must multiply every rule's count by exactly 2."""

    def test_duplicating_the_corpus_doubles_every_rule_count(self) -> None:
        repo = self.variant()
        copy_dir = repo / "copy"
        copy_dir.mkdir()
        for java in list(repo.glob("*.java")):
            shutil.copy2(java, copy_dir / java.name)
        problems = sd.check_scaling(BASE_SET, sd.signals_set(repo), 2)
        self.assertEqual(problems, [], "\n".join(problems))


class HarnessIsNotVacuousTest(CorpusCase):
    """Proves the machinery above can fail. Without this, every assertion in
    this file could be passing because the corpus scans to nothing, or
    because assertRelation never inspects anything."""

    def test_a_real_semantic_edit_is_reported_under_unchanged(self) -> None:
        repo = self.variant()
        target = repo / "ApiSurface.java"
        target.write_text(target.read_text(encoding="utf-8")
                          .replace("@RestController", "@RestController\n@Timed", 1),
                          encoding="utf-8")
        residue = sd.classify(sd.delta(BASE_SET, sd.signals_set(repo)), sd.unchanged())
        self.assertFalse(residue.is_empty(),
                         "a real added annotation produced no residue")

    def test_the_reference_corpus_is_not_empty(self) -> None:
        self.assertGreater(len(BASE_SET), 10, len(BASE_SET))


if __name__ == "__main__":
    unittest.main(verbosity=2)
