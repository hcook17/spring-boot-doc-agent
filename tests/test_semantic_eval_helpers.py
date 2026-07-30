#!/usr/bin/env python3
"""
Unit tests for semantic_eval_helpers.py's two mechanical checks —
find_unmatched_confirmed_tags() and check_mermaid_syntax() — plus run()'s
end-to-end artifacts-directory wiring against a small synthetic fixture
tree (built in a tempdir, not scripts/fixtures/spring_signals/: that
fixture is a source-code tree for ast-grep/token-estimation tests, not a
pipeline-output tree with docs/*.md + interview_answers.json, so reusing it
here would be forcing a fit rather than genuine reuse).

Run with:
    pytest tests/test_semantic_eval_helpers.py -v
"""

import json
import os
import sys
import tempfile
import unittest
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH
from doc_engine.tools import semantic_eval_helpers

SCRIPT_DIR = SCRIPTS_DIR

ANSWERED_ENTRY = {
    "blocks_file": "database", "topic": "write ownership: billing_invoice",
    "question": "Is InvoiceService.markPaid the only writer of billing_invoice?",
    "status": "answered", "answer": "Yes, InvoiceService is the only writer of billing_invoice.",
    "date": "2026-07-23",
}
SKIPPED_ENTRY = {
    "blocks_file": "authorization", "topic": "endpoint intent",
    "question": "Is this endpoint intentionally public?",
    "status": "skipped", "date": "2026-07-23",
}


class UnmatchedConfirmedTagsTest(unittest.TestCase):
    def test_matching_claim_not_flagged(self):
        text = ("InvoiceService is the only writer of billing_invoice "
                "[Confirmed — interview, 2026-07-23].")
        findings = semantic_eval_helpers.find_unmatched_confirmed_tags(text, [ANSWERED_ENTRY])
        self.assertEqual(findings, [])

    def test_unrelated_claim_flagged(self):
        text = ("The service deploys nightly at 2am UTC "
                "[Confirmed — interview, 2026-07-23].")
        findings = semantic_eval_helpers.find_unmatched_confirmed_tags(text, [ANSWERED_ENTRY])
        self.assertEqual(len(findings), 1)
        self.assertIn("candidate hallucinated", findings[0]["reason"])

    def test_no_interview_answers_flags_every_confirmed_tag(self):
        text = "Something is true [Confirmed — interview, 2026-07-23]."
        findings = semantic_eval_helpers.find_unmatched_confirmed_tags(text, [])
        self.assertEqual(len(findings), 1)

    def test_skipped_entries_never_back_a_confirmed_tag(self):
        # A skipped question has no answer text — it must never be treated
        # as support for a Confirmed tag even if topic words overlap.
        text = ("This endpoint is intentionally public "
                "[Confirmed — interview, 2026-07-23].")
        findings = semantic_eval_helpers.find_unmatched_confirmed_tags(text, [SKIPPED_ENTRY])
        self.assertEqual(len(findings), 1)

    def test_overlap_exactly_at_threshold_is_not_flagged(self):
        # Jaccard overlap = |intersection| / |union| = 3 / 20 = 0.15 exactly,
        # matching DEFAULT_OVERLAP_THRESHOLD. The check is a strict `<`, so
        # a claim landing exactly on the threshold counts as matched, not
        # flagged — this pins down that boundary explicitly rather than
        # leaving it implicit.
        shared = ["aa", "bb", "cc"]
        clause_tokens = shared + [f"c{i}" for i in range(10)]   # 13 tokens
        entry_tokens = shared + [f"e{i}" for i in range(7)]     # 10 tokens
        # union = 13 + 10 - 3 = 20; intersection = 3; ratio = 3/20 = 0.15
        text = " ".join(clause_tokens) + " [Confirmed — interview, 2026-07-23]."
        entry = {"status": "answered", "topic": " ".join(entry_tokens), "question": "", "answer": "", "date": "2026-07-23"}
        findings = semantic_eval_helpers.find_unmatched_confirmed_tags(text, [entry], overlap_threshold=0.15)
        self.assertEqual(findings, [])

    def test_overlap_just_below_threshold_is_flagged(self):
        shared = ["aa", "bb"]
        clause_tokens = shared + [f"c{i}" for i in range(11)]   # 13 tokens
        entry_tokens = shared + [f"e{i}" for i in range(8)]     # 10 tokens
        # union = 13 + 10 - 2 = 21; intersection = 2; ratio = 2/21 ≈ 0.095 < 0.15
        text = " ".join(clause_tokens) + " [Confirmed — interview, 2026-07-23]."
        entry = {"status": "answered", "topic": " ".join(entry_tokens), "question": "", "answer": "", "date": "2026-07-23"}
        findings = semantic_eval_helpers.find_unmatched_confirmed_tags(text, [entry], overlap_threshold=0.15)
        self.assertEqual(len(findings), 1)

    def test_custom_overlap_threshold_changes_classification(self):
        # Same clause/entry pair (ratio ~0.095) classified differently
        # depending on the threshold parameter — confirms the parameter is
        # actually load-bearing, not a documented-but-unused default.
        shared = ["aa", "bb"]
        clause_tokens = shared + [f"c{i}" for i in range(11)]
        entry_tokens = shared + [f"e{i}" for i in range(8)]
        text = " ".join(clause_tokens) + " [Confirmed — interview, 2026-07-23]."
        entry = {"status": "answered", "topic": " ".join(entry_tokens), "question": "", "answer": "", "date": "2026-07-23"}

        flagged_at_default = semantic_eval_helpers.find_unmatched_confirmed_tags(text, [entry], overlap_threshold=0.15)
        not_flagged_at_lower_threshold = semantic_eval_helpers.find_unmatched_confirmed_tags(text, [entry], overlap_threshold=0.05)
        self.assertEqual(len(flagged_at_default), 1)
        self.assertEqual(not_flagged_at_lower_threshold, [])

    def test_multiple_tags_evaluated_independently(self):
        text = (
            "InvoiceService is the only writer of billing_invoice "
            "[Confirmed — interview, 2026-07-23]. "
            "The service deploys nightly at 2am UTC "
            "[Confirmed — interview, 2026-07-23]."
        )
        findings = semantic_eval_helpers.find_unmatched_confirmed_tags(text, [ANSWERED_ENTRY])
        self.assertEqual(len(findings), 1)
        self.assertIn("deploys nightly", findings[0]["claim_clause"])


class MermaidSyntaxTest(unittest.TestCase):
    def test_well_formed_diagram_passes(self):
        mermaid = (
            "flowchart TB\n"
            "  subgraph API\n"
            '    A["InvoiceController.java"] --> B["InvoiceRepository.java"]\n'
            "  end\n"
        )
        self.assertEqual(semantic_eval_helpers.check_mermaid_syntax(mermaid), [])

    def test_unbalanced_square_brackets_flagged(self):
        mermaid = 'flowchart TB\n  A["InvoiceController.java --> B["InvoiceRepository.java"]\n'
        findings = semantic_eval_helpers.check_mermaid_syntax(mermaid)
        types = {f["type"] for f in findings}
        self.assertIn("unbalanced_square_brackets", types)

    def test_unbalanced_subgraph_end_flagged(self):
        mermaid = 'flowchart TB\n  subgraph API\n    A["X"] --> B["Y"]\n'  # missing `end`
        findings = semantic_eval_helpers.check_mermaid_syntax(mermaid)
        types = {f["type"] for f in findings}
        self.assertIn("unbalanced_subgraph_end", types)

    def test_unbalanced_quotes_flagged(self):
        mermaid = 'flowchart TB\n  A["X] --> B["Y"]\n'
        findings = semantic_eval_helpers.check_mermaid_syntax(mermaid)
        types = {f["type"] for f in findings}
        self.assertIn("unbalanced_quotes", types)

    def test_all_endpoints_labeled_no_undefined_ref(self):
        mermaid = (
            'flowchart TB\n'
            '  A["InvoiceController.java"] --> B["InvoiceRepository.java"]\n'
        )
        self.assertEqual(semantic_eval_helpers.find_undefined_node_refs(mermaid), [])
        types = {f["type"] for f in semantic_eval_helpers.check_mermaid_syntax(mermaid)}
        self.assertNotIn("undefined_node_ref", types)

    def test_edge_endpoint_never_labeled_flagged(self):
        # Regression: a node that only ever shows up as a bare edge
        # endpoint, never given a label anywhere in the diagram, is the
        # mechanical signature of a truncated/malformed diagram for this
        # pipeline's output specifically (agents/architect-segment.md rule
        # 3 requires every real node to carry a genuine file/class label).
        mermaid = (
            'flowchart TB\n'
            '  A["InvoiceController.java"] --> Z\n'
        )
        self.assertEqual(semantic_eval_helpers.find_undefined_node_refs(mermaid), ["Z"])
        types = {f["type"] for f in semantic_eval_helpers.check_mermaid_syntax(mermaid)}
        self.assertIn("undefined_node_ref", types)

    def test_node_labeled_elsewhere_in_diagram_not_flagged(self):
        # B is only a bare edge target on the first line, but it does get a
        # real label on a later line (e.g. as the source of a second edge)
        # — this must not be flagged, since it does have a label somewhere.
        mermaid = (
            'flowchart TB\n'
            '  A["InvoiceController.java"] --> B\n'
            '  B["InvoiceService.java"] --> C["InvoiceRepository.java"]\n'
        )
        self.assertEqual(semantic_eval_helpers.find_undefined_node_refs(mermaid), [])

    def test_traceability_is_a_separate_concern_from_undefined_ref(self):
        # find_undefined_node_refs only checks whether a node has *a* label
        # at all — not whether that label is a real file/class name (that's
        # test_pipeline_stages.py's find_untraceable_nodes' job). A
        # fabricated-but-present label must not be flagged here.
        mermaid = 'flowchart TB\n  A["Billing Orchestration Service"] --> B["InvoiceRepository.java"]\n'
        self.assertEqual(semantic_eval_helpers.find_undefined_node_refs(mermaid), [])


class RunEndToEndTest(unittest.TestCase):
    def test_run_against_synthetic_artifacts_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = os.path.join(tmp, "docs")
            os.makedirs(docs_dir)

            with open(os.path.join(tmp, "interview_answers.json"), "w", encoding="utf-8") as f:
                json.dump([ANSWERED_ENTRY], f)

            with open(os.path.join(docs_dir, "database.md"), "w", encoding="utf-8") as f:
                f.write("InvoiceService is the only writer of billing_invoice "
                        "[Confirmed — interview, 2026-07-23].\n"
                        "The service deploys nightly at 2am UTC "
                        "[Confirmed — interview, 2026-07-23].\n")

            with open(os.path.join(docs_dir, "architecture.md"), "w", encoding="utf-8") as f:
                f.write("# Architecture\n\n```mermaid\nflowchart TB\n"
                         '  A["Invoice.java" --> B["InvoiceRepository.java"]\n```\n')

            report = semantic_eval_helpers.run(tmp)

            self.assertIn("database.md", report["unmatched_confirmed_tags_by_file"])
            self.assertEqual(len(report["unmatched_confirmed_tags_by_file"]["database.md"]), 1)
            self.assertTrue(len(report["mermaid_syntax_findings"]) >= 1)

    def test_run_with_no_interview_answers_file_treats_all_confirmed_as_unmatched(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = os.path.join(tmp, "docs")
            os.makedirs(docs_dir)
            with open(os.path.join(docs_dir, "readme.md"), "w", encoding="utf-8") as f:
                f.write("Deploy cadence is weekly [Confirmed — interview, 2026-07-23].\n")

            report = semantic_eval_helpers.run(tmp)
            self.assertIn("readme.md", report["unmatched_confirmed_tags_by_file"])

    def test_run_with_no_docs_dir_returns_empty_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = semantic_eval_helpers.run(tmp)
            self.assertEqual(report["unmatched_confirmed_tags_by_file"], {})
            self.assertEqual(report["mermaid_syntax_findings"], [])


if __name__ == "__main__":
    unittest.main()
