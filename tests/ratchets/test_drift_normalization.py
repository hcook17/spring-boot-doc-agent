#!/usr/bin/env python3
"""
tests/ratchets/test_drift_normalization.py — how often does spring_drift_check tier 2 report
drift when nothing drifted, and would a different match-identity fix it?

Usage:
    pytest tests/ratchets/test_drift_normalization.py -v

Skips itself if scripts/fixtures/spring_signals/ or the ast-grep binary is
absent, following the same pattern as tests/doc_engine/test_spring_signal_scan.py.

WHAT THIS SUITE OWNS, AND WHAT IT DOES NOT

tests/doc_engine/test_spring_drift_check.py owns tier 2's unit-level behaviour: that each
per-rule extractor compares the right field, that a deleted file produces
STATUS_FILE_DELETED, that JPQL provenance widens correctly. It works from
hand-built signals dicts.

This suite owns something that cannot be seen at that level: the RATE at which
real edits to real Java produce wrong verdicts. It runs the actual scanner and
the actual checker over the actual fixtures, perturbs the source, and counts.
A per-rule unit test cannot fail for "this is right 206 times out of 208";
that number only exists once you run the whole thing against a corpus.

The two suites should not be merged. If a specific case here starts failing,
the fix usually belongs in tests/doc_engine/test_spring_drift_check.py as a named unit case,
and this suite goes back to counting.

THE TWO ARMS, AND WHY BOTH ARE REQUIRED

  Arm 1, false positives: formatting-only edits (java_perturbations.py). Every
  "drifted" verdict is wrong by construction.

  Arm 2, missed changes: semantic edits chosen to preserve citation COUNT while
  changing citation CONTENT. Every "confirmed" verdict on a changed citation is
  wrong.

Arm 1 alone is trivially winnable -- a normalizer returning "" for everything
scores a perfect zero and detects nothing. Arm 2 is what makes arm 1 mean
something, and is the reason no test here asserts a false-positive count in
isolation.

AND THE HARNESS IS TESTED TOO, BECAUSE IT WAS WRONG ONCE

Class 00 asserts the validity gate rejects a perturbation that breaks the
parse. That is not hypothetical: it is the exact defect that made the first
measurement read 7/208 instead of 2/208. See java_perturbations.py's docstring.

HAZARDS THIS SUITE DOES NOT COVER, RECORDED RATHER THAN OMITTED

  - The corpus is 9 Java files and four hand-written perturbations. The
    measured wrap false-positive count (pinned in Test02) is bounded by what
    the author thought to try, not by the checker. A generated perturbation
    corpus would bound it properly; nothing here should be read as an upper
    limit.
  - Only Java is perturbed. YAML, SQL and properties citations ride the same
    generic comparison and are never exercised for formatting sensitivity.
  - Nothing here perturbs a file's ENCODING or line endings. The fixtures are
    read and written as UTF-8 text throughout, so a CRLF/LF flip -- which tier
    1 WOULD see, since it hashes raw bytes -- is untested.
  - wrap_annotation_args' `or "//" in line` guard is NOT exercised. An
    injection removing it was expected to trip the validity gate and did not:
    on this corpus the line-scoping alone prevents comment-interior rewrites,
    and that guard is defence in depth on top of it. It is kept, but nothing
    here demonstrates it is load-bearing, so do not read it as tested.
"""
import os
import shutil
import sys
import tempfile
import unittest
from typing import Callable, Dict, List, NamedTuple, Optional
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH
from doc_engine.scanning import java_extract
from doc_engine.scanning import _scanner_astgrep as astgrep_backend
from doc_engine.tools import spring_drift_check, spring_signal_scan
import drift_match_normalizers as norms
import java_perturbations as perturb

SCRIPT_DIR = SCRIPTS_DIR

FIXTURES = os.path.join(SCRIPT_DIR, "fixtures", "spring_signals")
# Fixture Java sources live under a Maven/Gradle-shaped tree (not flat).
_BILLING = os.path.join("src", "main", "java", "com", "example", "billing")
CONTROLLER_REL = os.path.join(_BILLING, "InvoiceController.java")
LEDGER_REL = os.path.join(_BILLING, "PaymentLedger.java")
CONFIRMING = ("confirmed_still_present", "unchanged")
CONTROLLER_BASENAME = "InvoiceController.java"
LEDGER_BASENAME = "PaymentLedger.java"
SEMANTIC_TOUCHED = frozenset({CONTROLLER_BASENAME, LEDGER_BASENAME})

# Filled by setUpModule.
_TMP: Optional[str] = None
OUTCOMES: Dict[str, "Outcome"] = {}
GETMAPPING_LINE: Optional[int] = None


def _report_basename(path: str) -> str:
    """Drift reports use repo-relative paths; older pins used flat basenames."""
    return os.path.basename(path.replace("\\", "/"))


class Outcome(NamedTuple):
    """One perturbation, scanned before and after, then drift-checked.

    `valid` is the instrument check: a formatting-only edit must leave the same
    number of citations discoverable by a fresh scan. False means the edit
    changed what is detectable, so its drift report says nothing about the
    checker and must not be scored."""
    report: dict
    citations_before: int
    citations_after: int

    @property
    def valid(self) -> bool:
        return self.citations_before == self.citations_after

    def drifted(self) -> List[dict]:
        return [r for r in self.report["results"] if r["status"] == "drifted"]


def _fixtures_usable() -> bool:
    """True when the committed fixture tree exists and ast-grep is on PATH.

    Do not call a removed ``spring_signal_scan.find_ast_grep`` helper — that
    AttributeError was swallowed here and silently skipped the whole suite
    in CI (19 dark tests) while ast-grep was verified elsewhere in the job.
    """
    if not os.path.isdir(FIXTURES):
        return False
    if not os.path.isfile(os.path.join(FIXTURES, CONTROLLER_REL)):
        return False
    return shutil.which("ast-grep") is not None


def _citation_count(signals: dict) -> int:
    return sum(len(v) for v in signals["evidence"].values())


def _run_scenario(name: str, mutate: Callable[[str], None]) -> Outcome:
    """Copy the fixtures, scan, mutate, re-scan, drift-check."""
    root = os.path.join(_TMP, name)
    shutil.copytree(FIXTURES, root)
    before = spring_signal_scan.scan(root)
    mutate(root)
    after = spring_signal_scan.scan(root)
    report = spring_drift_check.check_drift(root, before)
    return Outcome(report, _citation_count(before), _citation_count(after))


def _apply_to_java(transform: Callable[[str], str]) -> Callable[[str], None]:
    def go(root: str) -> None:
        for dirpath, _dirs, files in os.walk(root):
            for fname in sorted(files):
                if not fname.endswith(".java"):
                    continue
                path = os.path.join(dirpath, fname)
                with open(path, encoding="utf-8") as f:
                    src = f.read()
                new = transform(src)
                if new != src:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(new)
    return go


def _semantic_edits(root: str) -> None:
    """Three content changes that keep the citation COUNT identical, so the
    same validity gate as arm 1 applies unchanged.

    Asserted rather than best-effort: if a fixture is edited so one of these
    no longer applies, this suite must fail loudly instead of quietly measuring
    a corpus where nothing changed."""
    ctrl = os.path.join(root, CONTROLLER_REL)
    with open(ctrl, encoding="utf-8") as f:
        src = f.read()
    assert '"/{id}"' in src, "fixture no longer has the /{id} mapping to change"
    assert "@GetMapping" in src, "fixture no longer has @GetMapping to change"
    with open(ctrl, "w", encoding="utf-8") as f:
        f.write(src.replace('"/{id}"', '"/{invoiceId}"').replace("@GetMapping", "@PutMapping"))

    led = os.path.join(root, LEDGER_REL)
    with open(led, encoding="utf-8") as f:
        src = f.read()
    assert 'name = "payment_ledger"' in src, "fixture no longer has the table name to rename"
    with open(led, "w", encoding="utf-8") as f:
        f.write(src.replace('name = "payment_ledger"', 'name = "ledger_v2"'))


def _locate_getmapping_line() -> int:
    """The line of the @GetMapping this suite mutates, read from the fixture
    rather than hardcoded, so inserting a line above it does not silently make
    the expected-drift label point at the wrong citation."""
    with open(os.path.join(FIXTURES, CONTROLLER_REL), encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if "@GetMapping" in line:
                return i
    raise AssertionError("no @GetMapping in InvoiceController.java")


def setUpModule() -> None:
    """Every scenario costs two full scans and a drift check, each of which
    shells out to ast-grep. Run them once here and let the test methods assert
    over the results, rather than re-deriving per method."""
    global _TMP, GETMAPPING_LINE
    if not os.path.isdir(FIXTURES):
        raise AssertionError(
            f"committed spring_signals fixtures missing at {FIXTURES}"
        )
    if not os.path.isfile(os.path.join(FIXTURES, CONTROLLER_REL)):
        raise AssertionError(
            f"fixture layout drift: expected nested {CONTROLLER_REL} under {FIXTURES}"
        )
    if shutil.which("ast-grep") is None:
        raise unittest.SkipTest("ast-grep not on PATH")
    _TMP = tempfile.mkdtemp(prefix="drift_norm_")
    GETMAPPING_LINE = _locate_getmapping_line()

    # Patch both the definition site and the ast-grep backend's bound import.
    original_extract = java_extract.first_line_match
    original_backend = astgrep_backend.first_line_match
    try:
        for cand_name, fn in norms.CANDIDATES.items():
            java_extract.first_line_match = fn
            astgrep_backend.first_line_match = fn
            for p_name, transform in perturb.FORMATTING_ONLY.items():
                OUTCOMES[f"{cand_name}/{p_name}"] = _run_scenario(
                    f"{cand_name}_{p_name}", _apply_to_java(transform))
            OUTCOMES[f"{cand_name}/semantic"] = _run_scenario(
                f"{cand_name}_semantic", _semantic_edits)
        java_extract.first_line_match = original_extract
        astgrep_backend.first_line_match = original_backend
        for p_name, transform in perturb.DELIBERATELY_BROKEN.items():
            OUTCOMES[f"broken/{p_name}"] = _run_scenario(
                f"broken_{p_name}", _apply_to_java(transform))
    finally:
        java_extract.first_line_match = original_extract
        astgrep_backend.first_line_match = original_backend


def tearDownModule() -> None:
    if _TMP and os.path.isdir(_TMP):
        shutil.rmtree(_TMP, ignore_errors=True)


class Test00HarnessValidityGate(unittest.TestCase):
    """The instrument, before anything it measures.

    A measurement whose perturbation silently broke the source is not a weak
    measurement, it is a different measurement. These tests exist because that
    happened."""

    def test_a_formatting_only_edit_passes_the_validity_gate(self):
        """The gate must accept as well as reject, or it is not discriminating
        -- it is just off."""
        for p_name in perturb.FORMATTING_ONLY:
            with self.subTest(perturbation=p_name):
                outcome = OUTCOMES[f"{norms.STATUS_QUO}/{p_name}"]
                self.assertTrue(
                    outcome.valid,
                    f"{p_name} is declared formatting-only but a fresh scan found "
                    f"{outcome.citations_after} citations against a baseline of "
                    f"{outcome.citations_before}")

    def test_a_parse_breaking_edit_is_rejected_by_the_validity_gate(self):
        """broken_wrap_annotation_args rewrites annotations inside comments and
        leaves the file unparseable. The gate must catch that. Without this
        test the gate is a claim, and this exact claim was false once."""
        outcome = OUTCOMES["broken/broken_wrap_annotation_args"]
        self.assertFalse(
            outcome.valid,
            "the deliberately-broken perturbation passed the validity gate, so "
            "the gate would not have caught the defect that made the first "
            "measurement of this overstate the false-positive rate by 3.5x")
        self.assertLess(outcome.citations_after, outcome.citations_before,
                        "expected the broken edit to make citations UNDISCOVERABLE")

    def test_the_broken_edit_would_have_been_scored_as_checker_failure(self):
        """Shows the gate is load-bearing, not decorative: without it, this
        perturbation contributes drift verdicts that look exactly like tier-2
        false positives."""
        self.assertGreater(
            len(OUTCOMES["broken/broken_wrap_annotation_args"].drifted()), 0,
            "if the broken edit produced no drift, the validity gate would be "
            "protecting against nothing and this suite would be overstating "
            "its own rigour")


class Test01FormattingMustNotProduceDrift(unittest.TestCase):
    """Arm 1 against the shipped normalizer. These are the properties tier 2
    already holds, and they are pinned so a change to the scanner cannot
    quietly lose them."""

    def _false_positives(self, p_name: str) -> List[dict]:
        outcome = OUTCOMES[f"{norms.STATUS_QUO}/{p_name}"]
        self.assertTrue(outcome.valid, f"{p_name} failed the validity gate")
        return outcome.drifted()

    def test_adding_comments_produces_no_drift(self):
        self.assertEqual([], self._false_positives("add_comment"))

    def test_reindenting_produces_no_drift(self):
        self.assertEqual([], self._false_positives("reindent"))

    def test_shifting_line_numbers_produces_no_drift(self):
        """Distinguishes "the citation moved" from "the citation's line number
        moved" -- tier 2 must only care about the first."""
        self.assertEqual([], self._false_positives("blank_lines"))


class Test02TheKnownGap(unittest.TestCase):
    """The one formatting class tier 2 gets wrong today, pinned at its measured
    size so that fixing it is visible and worsening it is a failure."""

    # Was 2 when the suite first measured a smaller fixture/rule surface; it
    # sat dark-skipped (broken find_ast_grep probe) while both grew. Re-pin
    # to the live wrap_annotation_args count against scripts/fixtures/spring_signals.
    KNOWN_FALSE_POSITIVES = 12

    def test_wrapping_an_annotation_still_produces_exactly_the_known_drift(self):
        """Asserts a defect, deliberately. This is the ratchet shape used by
        check_code_quality.py: pin the current number so movement in either
        direction is a test failure someone has to look at.

        If this fails LOW, the gap was fixed -- adopt the normalizer, drop this
        count to 0, and delete this docstring's second half. If it fails HIGH,
        something made the generic comparison more brittle."""
        fps = OUTCOMES[f"{norms.STATUS_QUO}/wrap_annotation_args"].drifted()
        self.assertEqual(
            self.KNOWN_FALSE_POSITIVES, len(fps),
            f"expected the known {self.KNOWN_FALSE_POSITIVES} false positives "
            f"from first-line truncation, got {len(fps)}: "
            f"{[(r['file'], r['line'], r['rule_id']) for r in fps]}")

    def test_the_known_gap_is_first_line_truncation_not_something_else(self):
        """Names the cause, so the pinned count above cannot start passing for
        an unrelated reason. Every false positive must be a one-line annotation
        with arguments — wrapping splits it so first_line_match keeps only
        ``@Name(``."""
        for r in OUTCOMES[f"{norms.STATUS_QUO}/wrap_annotation_args"].drifted():
            with self.subTest(file=r["file"], line=r["line"], rule=r["rule_id"]):
                match = r.get("match") or ""
                self.assertIn(
                    "(", match,
                    "a false positive without annotation args is not the "
                    "first-line-truncation gap this suite pins")
                self.assertTrue(
                    match.lstrip().startswith("@"),
                    "expected an annotation-shaped stored match")


class Test03SemanticChangesMustBeCaught(unittest.TestCase):
    """Arm 2. Without this class, every assertion above could be satisfied by a
    checker that confirms everything."""

    def _graded(self, cand: str) -> List[dict]:
        outcome = OUTCOMES[f"{cand}/semantic"]
        self.assertTrue(outcome.valid,
                        "the semantic edits changed the citation count, so they "
                        "are not comparable to the formatting arm")
        return [
            r for r in outcome.report["results"]
            if _report_basename(r["file"]) in SEMANTIC_TOUCHED
        ]

    def _is_expected_to_drift(self, r: dict) -> bool:
        """Hand-labelled. Deriving the expected set from a fresh scan would
        grade the checker against a restatement of its own comparison."""
        return (
            (_report_basename(r["file"]) == CONTROLLER_BASENAME
             and r["line"] == GETMAPPING_LINE)
            or r["source"] == "entity_table_map.PaymentLedger"
        )

    def test_a_changed_mapping_and_a_renamed_table_are_both_reported(self):
        graded = self._graded(norms.STATUS_QUO)
        expected = [r for r in graded if self._is_expected_to_drift(r)]
        self.assertEqual(2, len(expected),
                         "the two labelled citations are no longer present in the "
                         "report at all -- the labels have gone stale")
        for r in expected:
            with self.subTest(source=r["source"], line=r["line"]):
                self.assertEqual("drifted", r["status"])

    def test_untouched_citations_in_the_same_files_are_not_reported(self):
        """Over-reporting inside a genuinely-changed file is the failure mode
        the whole two-tier design exists to avoid -- see spring_drift_check's
        "WHY TWO TIERS" docstring."""
        for r in self._graded(norms.STATUS_QUO):
            if self._is_expected_to_drift(r):
                continue
            with self.subTest(source=r["source"], line=r["line"]):
                self.assertIn(r["status"], CONFIRMING,
                              f"{r['match']!r} did not change but was reported "
                              f"{r['status']}")


class Test04NormalizerCandidates(unittest.TestCase):
    """The comparison table from drift_match_normalizers.py's docstring,
    re-derived rather than quoted -- a table in a comment goes stale silently,
    and this repo has been bitten by exactly that."""

    ZERO_FALSE_POSITIVE = ("strip_ws_outside_strings", "tokens")

    def _false_positives(self, cand: str) -> int:
        total = 0
        for p_name in perturb.FORMATTING_ONLY:
            outcome = OUTCOMES[f"{cand}/{p_name}"]
            self.assertTrue(outcome.valid, f"{cand}/{p_name} failed the validity gate")
            total += len(outcome.drifted())
        return total

    def test_the_status_quo_is_the_row_with_false_positives(self):
        self.assertEqual(Test02TheKnownGap.KNOWN_FALSE_POSITIVES,
                         self._false_positives(norms.STATUS_QUO))

    def test_collapsing_whitespace_alone_does_not_help(self):
        """Recorded because it is the obvious first fix and it does not work:
        '@Get( "/x" )' still differs from '@Get("/x")'. Pinning the negative
        result stops it being re-proposed."""
        self.assertEqual(Test02TheKnownGap.KNOWN_FALSE_POSITIVES,
                         self._false_positives("collapse_ws"))

    def test_the_stronger_candidates_reach_zero_false_positives(self):
        for cand in self.ZERO_FALSE_POSITIVE:
            with self.subTest(normalizer=cand):
                self.assertEqual(0, self._false_positives(cand))

    def test_no_candidate_buys_that_by_missing_a_real_change(self):
        """The non-vacuity check on the table itself. A candidate reaching zero
        false positives while confirming a renamed table has not improved
        anything -- it has stopped working."""
        for cand in norms.CANDIDATES:
            with self.subTest(normalizer=cand):
                outcome = OUTCOMES[f"{cand}/semantic"]
                graded = [
                    r for r in outcome.report["results"]
                    if _report_basename(r["file"]) in SEMANTIC_TOUCHED
                ]
                missed = [r for r in graded
                          if Test03SemanticChangesMustBeCaught._is_expected_to_drift(self, r)
                          and r["status"] in CONFIRMING]
                self.assertEqual([], missed,
                                 f"{cand} confirmed a citation that really changed")


class Test05NormalizerProperties(unittest.TestCase):
    """Properties of the candidate relations themselves, independent of the
    corpus -- these would still hold if the fixtures were deleted."""

    def test_every_candidate_is_stable_under_whitespace(self):
        wrapped = '@RequestMapping(\n        "/api/invoices"\n)'
        flat = '@RequestMapping("/api/invoices")'
        for name in Test04NormalizerCandidates.ZERO_FALSE_POSITIVE:
            with self.subTest(normalizer=name):
                fn = norms.CANDIDATES[name]
                self.assertEqual(fn(wrapped), fn(flat))

    def test_every_candidate_still_separates_a_changed_literal(self):
        """The direction that matters: stability must not become blindness."""
        a = '@GetMapping("/{id}")'
        b = '@GetMapping("/{invoiceId}")'
        for name, fn in norms.CANDIDATES.items():
            with self.subTest(normalizer=name):
                self.assertNotEqual(fn(a), fn(b))

    def test_the_token_separator_cannot_occur_in_java_source(self):
        """What makes `tokens` injective where strip_ws_outside_strings is not.
        If this ever stops holding, two distinct token sequences could join to
        the same string and the relation silently loses its guarantee."""
        self.assertEqual(1, len(norms.TOKEN_SEP))
        self.assertFalse(norms.TOKEN_SEP.isprintable())
        seen_java = False
        for dirpath, _dirs, files in os.walk(FIXTURES):
            for fname in sorted(files):
                if not fname.endswith(".java"):
                    continue
                seen_java = True
                with open(os.path.join(dirpath, fname), encoding="utf-8") as f:
                    self.assertNotIn(norms.TOKEN_SEP, f.read())
        self.assertTrue(seen_java, f"no .java under nested fixtures at {FIXTURES}")

    def test_stripping_whitespace_outside_strings_is_not_injective(self):
        """Asserts the known weakness of the runner-up, so the choice of
        `tokens` rests on a demonstrated collision rather than on taste."""
        fn = norms.CANDIDATES["strip_ws_outside_strings"]
        self.assertEqual(fn("int a"), fn("inta"))
        self.assertNotEqual(norms.tokens("int a"), norms.tokens("inta"))

    def test_whitespace_inside_a_string_literal_is_preserved(self):
        """A query or path with meaningful internal spacing must not be
        normalized into equality with a different one."""
        for name in Test04NormalizerCandidates.ZERO_FALSE_POSITIVE:
            with self.subTest(normalizer=name):
                fn = norms.CANDIDATES[name]
                self.assertNotEqual(fn('@Q("select a")'), fn('@Q("selecta")'))


if __name__ == "__main__":
    unittest.main(verbosity=2)
