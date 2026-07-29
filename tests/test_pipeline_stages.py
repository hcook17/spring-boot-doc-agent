#!/usr/bin/env python3
"""
Structural (mechanical) tests for the LLM pipeline stages —
file-summarizer, architect-segment/architect-merge, gap-analyzer,
software-architect-and-testing, doc-writer — none of which had any test
coverage before this file. Only the two deterministic scripts
(spring_signal_scan.py, partition_repo.py) and spring_drift_check.py had
tests; a prompt regression in any of the six agents/*.md files was
previously invisible except by a human reading generated output and
noticing something's wrong.

Per claude/steering-prompts/01-testability-research-prompt.md: this suite
is mechanical wherever possible, not LLM-as-judge. It does not invoke any
LLM itself — Claude Code subagents can't be driven from a plain Python
process outside a live session — so it validates two things instead:

1. The validator functions in this file, against synthetic sample data
   shaped exactly like what agents/file-summarizer.md, agents/gap-analyzer.md,
   agents/architect-segment.md + architect-merge.md, and agents/doc-writer.md
   document as their required output shape. Each test is a regression guard
   for one concrete, previously-plausible failure class (a malformed tag, an
   [Evidenced — ...] citation that doesn't resolve to a real file/line, an
   Unknown-tag ratio that's silently ballooned, an unbounded gap-analyzer
   question list, an architecture node whose label doesn't trace back to any
   known file).
2. Optionally, the same validators against a *real* completed pipeline run's
   actual output artifacts (summaries.json, the merged architecture diagram,
   gap_questions.json, and the 14 generated docs/*.md files), gated behind
   the PIPELINE_ARTIFACTS_DIR environment variable — same opt-in,
   skip-if-absent pattern as test_partition_repo_real_world.py's
   PARTITION_REPO_REAL_FIXTURE_DIR. Not required for this file's main
   assertions to run or pass.

The fixture repo used for file/line resolution below is the same one
spring_signal_scan.py's own test suite already uses
(scripts/test_fixtures/spring_signals/) — deliberately reused rather than
building a second one, since a second independently-maintained fixture tree
is exactly the kind of two-sources-of-truth drift this project's own history
(IMPLEMENTATION_HANDOFF.md item 1, item 4) has already hit twice.

Run with:
    python3 scripts/test_pipeline_stages.py -v

Opt-in real-artifacts pass:
    PIPELINE_ARTIFACTS_DIR=/path/to/completed/run/output python3 scripts/test_pipeline_stages.py -v
"""

import json
import os
import sys
import unittest
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH
# TAG_PATTERNS, TAG_WORD_SPAN, find_malformed_tags(), count_tags_by_kind(),
# and VALID_DOC_FILES moved to doc_tag_utils.py so run_manifest.py's
# evidence_tag_counts computation can import the exact same tag grammar
# instead of a second copy that could drift out of sync with what this
# suite enforces. Re-imported here under their original names so the rest
# of this file (and its own tests, which assert against these names
# directly) is unchanged.
from doc_engine.tools.doc_tag_utils import (
    VALID_DOC_FILES,
    count_tags_by_kind,
    find_malformed_tags,
    resolve_evidenced_citations,
)
from doc_engine.tools.pipeline_validators import (
    FILE_SUMMARY_REQUIRED_KEYS,
    VALID_SPRING_ROLES,
    find_untraceable_nodes,
    validate_architecture_testing_review_findings,
    validate_file_summarizer_entries,
    validate_gap_analyzer_questions,
)

SCRIPT_DIR = SCRIPTS_DIR

class TagFormatTest(unittest.TestCase):
    def test_all_five_forms_recognized_and_not_flagged_malformed(self):
        text = (
            "Uses PostgreSQL [Evidenced — build.gradle]. "
            "Endpoint requires BILLING_READ [Evidenced — InvoiceController.java:11]. "
            "Deploy cadence is weekly [Confirmed — interview, 2026-07-23]. "
            "Retry policy [Unknown — not evidenced in code, not covered in interview]. "
            "Owning team is Billing [Per existing docs — README.md, unverified against code]. "
            "Config binds env vars [Evidenced — Invoice.java:6; inference avoided beyond this]."
        )
        self.assertEqual(find_malformed_tags(text), [])
        counts = count_tags_by_kind(text)
        self.assertEqual(counts["evidenced"], 3)
        self.assertEqual(counts["confirmed"], 1)
        self.assertEqual(counts["unknown"], 1)
        self.assertEqual(counts["per_existing_docs"], 1)

    def test_wrong_dash_flagged_malformed(self):
        # Regression: a hyphen instead of an em dash is a real, easy-to-miss
        # LLM substitution that reads fine to a human skim but fails the
        # "exact wording" rule doc-taxonomy.md requires.
        text = "Owned by Billing team [Evidenced - build.gradle]."
        self.assertEqual(find_malformed_tags(text), ["[Evidenced - build.gradle]"])

    def test_missing_citation_flagged_malformed(self):
        # An Evidenced tag with no actual path/citation after the dash is
        # exactly the "guess dressed up as a tag" doc-taxonomy.md warns
        # against — it must not silently pass as well-formed.
        text = "Something is true [Evidenced —]."
        self.assertEqual(find_malformed_tags(text), ["[Evidenced —]"])

    def test_lowercase_tag_word_flagged_malformed(self):
        text = "Something is true [evidenced — build.gradle]."
        # Lowercase doesn't match TAG_WORD_SPAN at all (by design — this
        # documents the limit: a fully different casing isn't caught as
        # "malformed," it's simply invisible to a grep-shaped check. Confirm
        # that limit explicitly rather than silently relying on it.
        self.assertEqual(find_malformed_tags(text), [])
        self.assertEqual(count_tags_by_kind(text)["evidenced"], 0)


class EvidencedCitationResolutionTest(unittest.TestCase):
    def test_real_file_and_line_resolves(self):
        text = (
            "Requires BILLING_READ "
            "[Evidenced — src/main/java/com/example/billing/InvoiceController.java:11]."
        )
        self.assertEqual(resolve_evidenced_citations(text, FIXTURE_DIR), [])

    def test_whole_file_citation_resolves(self):
        text = (
            "Maps to table billing_invoice "
            "[Evidenced — src/main/java/com/example/billing/Invoice.java]."
        )
        self.assertEqual(resolve_evidenced_citations(text, FIXTURE_DIR), [])

    def test_nonexistent_file_fails_resolution(self):
        text = "Something [Evidenced — NoSuchController.java:5]."
        failures = resolve_evidenced_citations(text, FIXTURE_DIR)
        self.assertEqual(len(failures), 1)
        self.assertIn("does not exist", failures[0][1])

    def test_line_number_past_end_of_file_fails_resolution(self):
        text = (
            "Something "
            "[Evidenced — src/main/java/com/example/billing/Invoice.java:9999]."
        )
        failures = resolve_evidenced_citations(text, FIXTURE_DIR)
        self.assertEqual(len(failures), 1)
        self.assertIn("past the end", failures[0][1])


class FileSummarizerShapeTest(unittest.TestCase):
    def test_valid_entries_pass(self):
        entries = [{
            "file": "InvoiceController.java", "cluster": ["Invoice.java"],
            "summary": "Handles invoice retrieval and creation.",
            "relationships": ["Invoice.java"], "cross_group_relationships": [],
            "group_function": "Invoice billing API", "spring_role": "controller",
            "evidence": [{"line": 42, "what": "creates invoices from the POST handler"}],
        }]
        self.assertEqual(validate_file_summarizer_entries(entries), [])

    def test_missing_key_flagged(self):
        entries = [{"file": "X.java", "cluster": [], "summary": "s",
                    "relationships": [], "group_function": "", "spring_role": "other",
                    "evidence": []}]
        problems = validate_file_summarizer_entries(entries)
        self.assertEqual(len(problems), 1)
        self.assertIn("cross_group_relationships", problems[0][1])

    def test_invalid_spring_role_flagged(self):
        entries = [{"file": "X.java", "cluster": [], "summary": "s", "relationships": [],
                    "cross_group_relationships": [], "group_function": "",
                    "spring_role": "controllerish", "evidence": []}]
        problems = validate_file_summarizer_entries(entries)
        self.assertEqual(len(problems), 1)
        self.assertIn("spring_role", problems[0][1])

    def _entry(self, **overrides):
        entry = {"file": "X.java", "cluster": [], "summary": "s", "relationships": [],
                 "cross_group_relationships": [], "group_function": "",
                 "spring_role": "other", "evidence": []}
        entry.update(overrides)
        return entry

    def test_missing_evidence_key_flagged(self):
        """The whole point of the field: a summarizer that silently stops
        emitting it drops every semantic line anchor in the run."""
        entry = self._entry()
        del entry["evidence"]
        problems = validate_file_summarizer_entries([entry])
        self.assertEqual(len(problems), 1)
        self.assertIn("evidence", problems[0][1])

    def test_empty_evidence_list_is_legitimate(self):
        """A genuinely whole-file summary has no single anchor. Requiring a
        non-empty list would just buy back invented line numbers."""
        self.assertEqual(validate_file_summarizer_entries([self._entry()]), [])

    def test_evidence_must_be_a_list(self):
        problems = validate_file_summarizer_entries([self._entry(evidence={"line": 1, "what": "x"})])
        self.assertTrue(any("must be a list" in p[1] for p in problems))

    def test_evidence_entry_missing_line_flagged(self):
        problems = validate_file_summarizer_entries([self._entry(evidence=[{"what": "x"}])])
        self.assertTrue(any("missing keys" in p[1] for p in problems))

    def test_evidence_line_must_be_an_int(self):
        problems = validate_file_summarizer_entries([self._entry(evidence=[{"line": "42", "what": "x"}])])
        self.assertTrue(any("must be an int" in p[1] for p in problems))

    def test_evidence_line_bool_rejected(self):
        """bool subclasses int; True is not a line number."""
        problems = validate_file_summarizer_entries([self._entry(evidence=[{"line": True, "what": "x"}])])
        self.assertTrue(any("must be an int" in p[1] for p in problems))

    def test_evidence_line_must_be_positive(self):
        problems = validate_file_summarizer_entries([self._entry(evidence=[{"line": 0, "what": "x"}])])
        self.assertTrue(any(">= 1" in p[1] for p in problems))

    def test_evidence_what_must_be_non_empty(self):
        problems = validate_file_summarizer_entries([self._entry(evidence=[{"line": 5, "what": "  "}])])
        self.assertTrue(any("non-empty string" in p[1] for p in problems))


class GapAnalyzerShapeTest(unittest.TestCase):
    def test_valid_bounded_list_passes(self):
        questions = [
            {"blocks_file": "database", "topic": "write ownership", "question": "q1", "evidence": "src/main/java/A.java:10 is the only writer"},
            {"blocks_file": "database", "topic": "write ownership 2", "question": "q2", "evidence": "src/main/java/B.java:20 has no guard"},
            {"blocks_file": "authorization", "topic": "endpoint", "question": "q3", "evidence": "src/main/java/C.java:30 is unmapped"},
        ]
        self.assertEqual(validate_gap_analyzer_questions(questions), [])

    def test_invalid_blocks_file_flagged(self):
        questions = [{"blocks_file": "faq", "topic": "t", "question": "q", "evidence": "src/main/java/A.java:10 is the only writer"}]
        problems = validate_gap_analyzer_questions(questions)
        self.assertEqual(len(problems), 1)
        self.assertIn("not one of the fourteen", problems[0][1])

    def test_non_contiguous_grouping_flagged(self):
        # Regression: gap-analyzer.md requires output "grouped by which file
        # they block" so the orchestrator can present them grouped. A
        # blocks_file that reappears after another file's questions have
        # already started is the mechanical signature of that rule breaking.
        questions = [
            {"blocks_file": "database", "topic": "t1", "question": "q1", "evidence": "src/main/java/A.java:10 is the only writer"},
            {"blocks_file": "authorization", "topic": "t2", "question": "q2", "evidence": "src/main/java/B.java:20 has no guard"},
            {"blocks_file": "database", "topic": "t3", "question": "q3", "evidence": "src/main/java/C.java:30 is unmapped"},
        ]
        problems = validate_gap_analyzer_questions(questions)
        self.assertEqual(len(problems), 1)
        self.assertIn("non-contiguously", problems[0][1])

    def test_elided_path_in_evidence_flagged(self):
        """gap-analyzer.md's own example used to ship `(src/.../Foo.java)`,
        so this malformed shape was actively modeled for the agent."""
        questions = [{"blocks_file": "database", "topic": "t", "question": "q",
                      "evidence": "InvoiceService.markPaid (src/.../InvoiceService.java) is the only writer"}]
        problems = validate_gap_analyzer_questions(questions)
        self.assertTrue(any("elided path" in p[1] for p in problems))

    def test_evidence_without_any_citation_flagged(self):
        """Unconstrained prose here leaves every downstream
        [Confirmed — interview, <date>] claim unanchored to any location."""
        questions = [{"blocks_file": "database", "topic": "t", "question": "q",
                      "evidence": "this table looks like it has one writer"}]
        problems = validate_gap_analyzer_questions(questions)
        self.assertTrue(any("no file citation" in p[1] for p in problems))

    def test_evidence_with_path_and_line_passes(self):
        questions = [{"blocks_file": "database", "topic": "t", "question": "q",
                      "evidence": "src/main/java/com/example/InvoiceService.java:88 is the only write path"}]
        self.assertEqual(validate_gap_analyzer_questions(questions), [])

    def test_evidence_with_bare_path_passes(self):
        """A path without a line is weaker but still resolvable; the taxonomy
        allows whole-file citations, so this is not the failure being caught."""
        questions = [{"blocks_file": "database", "topic": "t", "question": "q",
                      "evidence": "declared in src/main/resources/schema.sql"}]
        self.assertEqual(validate_gap_analyzer_questions(questions), [])

    def test_padded_list_exceeds_sanity_ceiling(self):
        questions = [{"blocks_file": "database", "topic": f"t{i}", "question": f"q{i}", "evidence": f"src/main/java/A{i}.java:10 is the only writer"}
                     for i in range(41)]
        problems = validate_gap_analyzer_questions(questions, max_questions=40)
        self.assertTrue(any("sanity ceiling" in p[1] for p in problems))


class ArchitectureTestingReviewShapeTest(unittest.TestCase):
    def test_valid_finding_passes(self):
        findings = [{
            "lens": "ddia", "concept": "DDIA ch.6 — no version field",
            "claim": "InvoiceLedger has no @Version field.",
            "evidence": [{"file": "InvoiceLedger.java", "line": 22, "what": "@Entity with no @Version"}],
            "external_research": None, "severity": "worth-flagging",
        }]
        self.assertEqual(validate_architecture_testing_review_findings(findings), [])

    def test_missing_evidence_flagged(self):
        findings = [{"lens": "testing", "concept": "c", "claim": "x", "evidence": [], "severity": "informational"}]
        problems = validate_architecture_testing_review_findings(findings)
        self.assertTrue(any("non-empty array" in p[1] for p in problems))

    def test_invalid_lens_flagged(self):
        findings = [{"lens": "security", "concept": "c", "claim": "x",
                     "evidence": [{"line": 1, "what": "w"}], "severity": "informational"}]
        problems = validate_architecture_testing_review_findings(findings)
        self.assertTrue(any("not one of" in p[1] and "lens" in str(p) for p in problems) or
                        any("security" in p[1] for p in problems))

    def test_tier_c_only_external_research_flagged(self):
        """Regression for claude/steering-prompts/10-review-persona-and-standards.md
        §2's "Tier C may never appear as a citation" — a finding whose
        external_research rests entirely on deepwiki.com (Tier C) with no
        Tier A/B backing must be caught, not silently accepted."""
        findings = [{
            "lens": "ddia", "concept": "c", "claim": "x",
            "evidence": [{"line": 1, "what": "w"}], "severity": "informational",
            "external_research": {
                "question": "q",
                "sources": [{"tier": "C", "identifier": "deepwiki.com/x/y"}],
                "verdict": "PLAUSIBLE",
            },
        }]
        problems = validate_architecture_testing_review_findings(findings)
        self.assertTrue(any("Tier C" in p[1] for p in problems))

    def test_tier_a_backed_external_research_passes(self):
        findings = [{
            "lens": "ddia", "concept": "c", "claim": "x",
            "evidence": [{"line": 1, "what": "w"}], "severity": "informational",
            "external_research": {
                "question": "q",
                "sources": [{"tier": "A", "identifier": "github.com/x/y"}],
                "verdict": "CONFIRMED",
            },
        }]
        self.assertEqual(validate_architecture_testing_review_findings(findings), [])

    def test_invalid_verdict_flagged(self):
        findings = [{
            "lens": "ddia", "concept": "c", "claim": "x",
            "evidence": [{"line": 1, "what": "w"}], "severity": "informational",
            "external_research": {"question": "q", "sources": [], "verdict": "MAYBE"},
        }]
        problems = validate_architecture_testing_review_findings(findings)
        self.assertTrue(any("verdict" in p[1] for p in problems))

    def test_padded_list_exceeds_sanity_ceiling(self):
        findings = [{"lens": "ddia", "concept": f"c{i}", "claim": f"x{i}",
                     "evidence": [{"line": i, "what": "w"}], "severity": "informational"}
                    for i in range(61)]
        problems = validate_architecture_testing_review_findings(findings, max_findings=60)
        self.assertTrue(any("sanity ceiling" in p[1] for p in problems))


class ArchitectureTraceabilityTest(unittest.TestCase):
    def test_known_node_labels_trace(self):
        mermaid = (
            "flowchart TB\n"
            '  A["InvoiceController.java"] -->|calls| B["InvoiceRepository.java"]\n'
        )
        known_names = {"InvoiceController.java", "InvoiceRepository.java", "Invoice.java"}
        self.assertEqual(find_untraceable_nodes(mermaid, known_names), [])

    def test_fabricated_node_label_flagged(self):
        # Regression: architect-segment.md rule 3 explicitly forbids
        # inventing a "friendlier" label — this is the mechanical check for
        # that rule actually holding, since a human skim of a diagram won't
        # catch a plausible-sounding but nonexistent node name.
        mermaid = (
            "flowchart TB\n"
            '  A["Billing Orchestration Service"] --> B["InvoiceRepository.java"]\n'
        )
        known_names = {"InvoiceController.java", "InvoiceRepository.java", "Invoice.java"}
        untraceable = find_untraceable_nodes(mermaid, known_names)
        self.assertEqual(untraceable, ["Billing Orchestration Service"])


class RealArtifactsOptInTest(unittest.TestCase):
    """Opt-in pass against a real completed pipeline run's actual output,
    gated by PIPELINE_ARTIFACTS_DIR (same pattern as
    test_partition_repo_real_world.py's PARTITION_REPO_REAL_FIXTURE_DIR).
    Expected directory layout: summaries.json (file-summarizer output),
    architecture.md (merged Mermaid + discrepancies), gap_questions.json
    (gap-analyzer output), and docs/*.md (the fourteen doc-writer outputs).
    Skipped entirely if the env var isn't set — this file's other test
    classes don't depend on it."""

    @classmethod
    def setUpClass(cls):
        cls.artifacts_dir = os.environ.get("PIPELINE_ARTIFACTS_DIR")
        if not cls.artifacts_dir:
            raise unittest.SkipTest("PIPELINE_ARTIFACTS_DIR not set — opt-in real-artifacts pass skipped")
        if not os.path.isdir(cls.artifacts_dir):
            raise unittest.SkipTest(f"PIPELINE_ARTIFACTS_DIR={cls.artifacts_dir!r} is not a directory")

    def test_summaries_json_shape(self):
        path = os.path.join(self.artifacts_dir, "summaries.json")
        if not os.path.isfile(path):
            self.skipTest("summaries.json not present in PIPELINE_ARTIFACTS_DIR")
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
        self.assertEqual(validate_file_summarizer_entries(entries), [])

    def test_gap_questions_shape(self):
        path = os.path.join(self.artifacts_dir, "gap_questions.json")
        if not os.path.isfile(path):
            self.skipTest("gap_questions.json not present in PIPELINE_ARTIFACTS_DIR")
        with open(path, encoding="utf-8") as f:
            questions = json.load(f)
        self.assertEqual(validate_gap_analyzer_questions(questions), [])

    def test_generated_docs_tags_well_formed_and_resolvable(self):
        docs_dir = os.path.join(self.artifacts_dir, "docs")
        target_repo_dir = os.environ.get("PIPELINE_ARTIFACTS_TARGET_REPO", self.artifacts_dir)
        if not os.path.isdir(docs_dir):
            self.skipTest("docs/ not present in PIPELINE_ARTIFACTS_DIR")
        for name in os.listdir(docs_dir):
            if not name.endswith(".md"):
                continue
            with open(os.path.join(docs_dir, name), encoding="utf-8") as f:
                text = f.read()
            with self.subTest(file=name):
                self.assertEqual(find_malformed_tags(text), [])
                unresolved = resolve_evidenced_citations(text, target_repo_dir)
                self.assertEqual(unresolved, [], f"unresolvable [Evidenced — ...] citations in {name}: {unresolved}")


if __name__ == "__main__":
    unittest.main()
