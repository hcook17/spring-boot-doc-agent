#!/usr/bin/env python3
"""
test_citation_coverage.py — tests for the missing-citation checks.

Two halves, mirroring the script's two checks. The false-positive tests
matter more than the true-positive ones here: a coverage checker that
flags ordinary prose gets muted, and a muted checker reports nothing at
all — the exact state citation_coverage.py exists to end.
"""

import os
import shutil
import sys
import tempfile
import unittest
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH
from doc_engine.tools import citation_coverage as cc


class TestUntaggedClaims(unittest.TestCase):

    def kinds(self, text):
        return [f["claim"] for f in cc.find_untagged_claims(text)]

    def test_untagged_claim_naming_a_class_is_flagged(self):
        text = "The OwnerController handles owner lookups.\n"
        self.assertEqual(len(cc.find_untagged_claims(text)), 1)

    def test_untagged_claim_naming_a_path_is_flagged(self):
        text = "- Datasource settings live in application.yml.\n"
        findings = cc.find_untagged_claims(text)
        self.assertEqual(len(findings), 1)
        self.assertIn("application.yml", findings[0]["named_artifacts"])

    def test_untagged_claim_naming_an_annotation_is_flagged(self):
        text = "- Endpoints are guarded with @PreAuthorize.\n"
        self.assertEqual(len(cc.find_untagged_claims(text)), 1)

    def test_untagged_claim_naming_a_config_key_is_flagged(self):
        text = "- The pool is sized by spring.datasource.hikari.maximum-pool-size.\n"
        self.assertEqual(len(cc.find_untagged_claims(text)), 1)

    def test_tagged_claim_is_not_flagged(self):
        text = "- The OwnerController handles lookups [Evidenced — src/Owner.java:6].\n"
        self.assertEqual(cc.find_untagged_claims(text), [])

    def test_unknown_tag_counts_as_tagged(self):
        text = ("- Write ownership of OwnerRepository is unclear "
                "[Unknown — not evidenced in code, not covered in interview].\n")
        self.assertEqual(cc.find_untagged_claims(text), [])

    def test_confirmed_tag_counts_as_tagged(self):
        text = "- OwnerController is called by batch [Confirmed — interview, 2026-07-24].\n"
        self.assertEqual(cc.find_untagged_claims(text), [])

    def test_malformed_tag_is_not_double_reported(self):
        """A wrong-dash tag is already find_malformed_tags()' finding. Counting
        it as untagged too would file one defect as two."""
        text = "- The OwnerController handles lookups [Evidenced - src/Owner.java:6].\n"
        self.assertEqual(cc.find_untagged_claims(text), [])

    def test_miscased_tag_is_reported_as_miscased_not_missing(self):
        """A lowercase tag word matches neither TAG_PATTERNS nor
        TAG_WORD_SPAN, so every counter in the repo scores it as absent.
        It is a citation the writer did make — report the real defect."""
        text = "- The OwnerController handles lookups [evidenced — src/Owner.java:6].\n"
        self.assertEqual(cc.find_untagged_claims(text), [])
        findings = cc.find_miscased_tags(text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "miscased_tag")

    def test_correctly_cased_tag_is_not_miscased(self):
        text = "- Lookups happen [Evidenced — src/Owner.java:6].\n"
        self.assertEqual(cc.find_miscased_tags(text), [])

    def test_all_caps_tag_word_is_miscased(self):
        text = "- Lookups happen [EVIDENCED — src/Owner.java:6].\n"
        self.assertEqual(len(cc.find_miscased_tags(text)), 1)

    def test_wrong_dash_alone_is_not_miscased(self):
        """A correctly-cased but wrong-dash tag is find_malformed_tags()'
        finding, not this one."""
        text = "- Lookups happen [Evidenced - src/Owner.java:6].\n"
        self.assertEqual(cc.find_miscased_tags(text), [])

    # --- false positives: the half that keeps this checker usable ---

    def test_prose_without_an_artifact_is_exempt(self):
        text = ("Requests are authenticated before they reach any handler.\n"
                "This section explains how access control works.\n")
        self.assertEqual(cc.find_untagged_claims(text), [])

    def test_headings_are_exempt(self):
        self.assertEqual(cc.find_untagged_claims("# OwnerController\n## application.yml\n"), [])

    def test_fenced_code_is_exempt(self):
        text = "```java\nclass OwnerController { void save() {} }\n```\n"
        self.assertEqual(cc.find_untagged_claims(text), [])

    def test_mermaid_block_is_exempt(self):
        text = "```mermaid\nflowchart TD\n  A[OwnerController] --> B[OwnerRepository]\n```\n"
        self.assertEqual(cc.find_untagged_claims(text), [])

    def test_taxonomy_placeholders_are_exempt(self):
        text = "- None found.\n- Not applicable\n- asked, not answered\n"
        self.assertEqual(cc.find_untagged_claims(text), [])

    def test_table_rule_is_exempt(self):
        self.assertEqual(cc.find_untagged_claims("| --- | --- |\n"), [])

    def test_bare_url_is_not_an_artifact(self):
        """A URL host looks exactly like a dotted config key. Linking to a
        website is not a claim about this codebase."""
        text = "Detection runs on tree-sitter, see https://ast-grep.github.io/ for details.\n"
        self.assertEqual(cc.find_untagged_claims(text), [])

    def test_markdown_link_target_is_not_an_artifact(self):
        text = "Detection runs on [ast-grep](https://ast-grep.github.io/) upstream.\n"
        self.assertEqual(cc.find_untagged_claims(text), [])

    def test_link_text_naming_a_real_artifact_still_counts(self):
        """Stripping the URL must not strip the visible text with it."""
        text = "See [OwnerController](https://example.com/x) for the handler.\n"
        self.assertEqual(len(cc.find_untagged_claims(text)), 1)

    def test_ordinary_abbreviation_is_not_a_config_key(self):
        """'e.g.' and friends must not read as a dotted config key."""
        text = "Some parts of the flow are asynchronous, e.g. the retry path.\n"
        self.assertEqual(cc.find_untagged_claims(text), [])

    def test_sentence_level_not_bullet_level(self):
        """A bullet whose second sentence is tagged does not thereby cite its
        first — doc-taxonomy.md's rule is per-claim."""
        text = ("- OwnerController handles lookups. OwnerRepository persists them "
                "[Evidenced — src/Owner.java:6].\n")
        findings = cc.find_untagged_claims(text)
        self.assertEqual(len(findings), 1)
        self.assertIn("OwnerController handles lookups", findings[0]["claim"])


class TestWeakAnchors(unittest.TestCase):

    SRC = """package com.example;

import org.springframework.stereotype.Controller;

@Controller
class OwnerController {
    private final OwnerRepository owners;

    public String processFindForm() {
        return "redirect:/owners/";
    }
}
"""

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.repo, "src"))
        with open(os.path.join(self.repo, "src", "OwnerController.java"), "w",
                  encoding="utf-8") as f:
            f.write(self.SRC)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_symbol_absent_from_file_is_flagged(self):
        text = ("The SecurityFilterChain bean is declared "
                "[Evidenced — src/OwnerController.java:5].\n")
        findings = cc.find_weak_anchors(text, self.repo)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "symbol_absent_from_file")

    def test_symbol_outside_window_is_flagged(self):
        """The real observed failure: a fact that exists in the file, cited at
        a line nowhere near it."""
        text = ("The processFindForm() method redirects after a search "
                "[Evidenced — src/OwnerController.java:1].\n")
        findings = cc.find_weak_anchors(text, self.repo, window=2)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "symbol_outside_window")
        self.assertIn("processFindForm", findings[0]["found_elsewhere_in_file"])

    def test_accurate_citation_is_not_flagged(self):
        text = ("The processFindForm() method redirects after a search "
                "[Evidenced — src/OwnerController.java:9].\n")
        self.assertEqual(cc.find_weak_anchors(text, self.repo), [])

    def test_whole_file_citation_has_no_anchor_to_check(self):
        text = "Dependencies are declared [Evidenced — build.gradle].\n"
        self.assertEqual(cc.find_weak_anchors(text, self.repo), [])

    def test_unresolvable_citation_is_left_to_the_other_checker(self):
        """resolve_evidenced_citations() owns 'this path does not exist'.
        Reporting it here too would file one defect twice."""
        text = "The Ghost class does things [Evidenced — src/Ghost.java:3].\n"
        self.assertEqual(cc.find_weak_anchors(text, self.repo), [])

    def test_citation_past_end_of_file_is_left_to_the_other_checker(self):
        text = "The OwnerRepository is injected [Evidenced — src/OwnerController.java:999].\n"
        self.assertEqual(cc.find_weak_anchors(text, self.repo), [])

    def test_claim_naming_only_the_cited_file_is_not_evidence(self):
        """A claim about OwnerController citing OwnerController.java tells us
        nothing about whether that *line* supports it, so there is nothing to
        check and nothing to flag."""
        text = "The OwnerController exists [Evidenced — src/OwnerController.java:1].\n"
        self.assertEqual(cc.find_weak_anchors(text, self.repo), [])

    def test_window_is_configurable(self):
        text = ("The processFindForm() method redirects "
                "[Evidenced — src/OwnerController.java:1].\n")
        self.assertEqual(len(cc.find_weak_anchors(text, self.repo, window=2)), 1)
        self.assertEqual(cc.find_weak_anchors(text, self.repo, window=20), [])


class TestCheckDocsAndExit(unittest.TestCase):

    def setUp(self):
        self.docs = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.docs, ignore_errors=True)

    def _write(self, name, text):
        with open(os.path.join(self.docs, name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_check_docs_reports_per_file(self):
        self._write("a.md", "The OwnerController handles lookups.\n")
        self._write("b.md", "Everything here is plain narrative prose.\n")
        report = cc.check_docs(self.docs, None)
        self.assertEqual(len(report["a.md"]["untagged_claims"]), 1)
        self.assertEqual(report["b.md"]["untagged_claims"], [])
        self.assertEqual(cc.total_findings(report), 1)

    def test_weak_anchor_check_skipped_without_target_repo_is_stated_not_silent(self):
        """check_pipeline_output.py's equivalent returns clean and says nothing
        when no target repo is given. This one says so out loud."""
        self._write("a.md", "Lookups happen [Evidenced — src/OwnerController.java:9].\n")
        report = cc.check_docs(self.docs, None)
        self.assertEqual(report["a.md"]["weak_anchors"], [])
        self.assertIn("did not run", cc.format_report(report, None))

    def test_non_markdown_files_ignored(self):
        self._write("notes.txt", "The OwnerController handles lookups.\n")
        self.assertEqual(cc.check_docs(self.docs, None), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
