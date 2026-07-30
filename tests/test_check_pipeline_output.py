#!/usr/bin/env python3
"""
Unit tests for check_pipeline_output.py.

Every check here replaces something that used to be carried only by an
instruction in agents/doc-writer.md, so each test is really asserting "this
failure is now caught by a check rather than by an LLM's cooperation."

The duplicate-path case (test_duplicate_output_path_shape_is_caught) is the
one worth reading: two writers handed the same output_path produce fourteen
files with one name duplicated and one missing. A count check passes that.
Only comparing against the taxonomy's actual name set catches it — which is
why check_file_set compares sets rather than lengths.

Run with:
    pytest tests/test_check_pipeline_output.py -v
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH
from doc_engine.tools import check_pipeline_output as c
from doc_engine.tools.doc_tag_utils import VALID_DOC_FILES

SCRIPT_DIR = SCRIPTS_DIR


def write_docs(docs_dir, names, body="# Title\n\nA claim. [Unknown — not evidenced in code, not covered in interview]\n"):
    for name in names:
        (docs_dir / f"{name}.md").write_text(body, encoding="utf-8")


class FileSetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_fourteen_present_is_clean(self):
        write_docs(self.tmp, VALID_DOC_FILES)
        self.assertEqual(c.check_file_set(self.tmp), [])

    def test_missing_file_flagged_by_name(self):
        write_docs(self.tmp, VALID_DOC_FILES - {"database"})
        issues = c.check_file_set(self.tmp)
        self.assertEqual(len(issues), 1)
        self.assertIn("database.md", issues[0])

    def test_unexpected_file_flagged(self):
        write_docs(self.tmp, VALID_DOC_FILES | {"scratch_notes"})
        issues = c.check_file_set(self.tmp)
        self.assertTrue(any("scratch_notes.md" in i for i in issues))

    def test_duplicate_output_path_shape_is_caught(self):
        # Two writers given the same output_path: fourteen writes, but one
        # name written twice and another never written. Counting to fourteen
        # passes this; comparing against the taxonomy's name set does not.
        names = (VALID_DOC_FILES - {"glossary"})
        write_docs(self.tmp, names)
        self.assertEqual(len(list(self.tmp.glob("*.md"))), 13)
        issues = c.check_file_set(self.tmp)
        self.assertTrue(any("glossary.md" in i for i in issues),
                        "the destroyed sibling must be named, not just counted")


class TagAndCitationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = Path(tempfile.mkdtemp())
        (self.repo / "src").mkdir()
        (self.repo / "src" / "Real.java").write_text("a\nb\nc\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_resolvable_citation_is_clean(self):
        write_docs(self.tmp, ["readme"], "# R\n\nX. [Evidenced — src/Real.java:2]\n")
        self.assertEqual(c.check_tags_and_citations(self.tmp, self.repo), [])

    def test_citation_to_missing_file_flagged(self):
        write_docs(self.tmp, ["readme"], "# R\n\nX. [Evidenced — src/Ghost.java:2]\n")
        issues = c.check_tags_and_citations(self.tmp, self.repo)
        self.assertTrue(any("Ghost.java" in i for i in issues))

    def test_citation_past_end_of_file_flagged(self):
        write_docs(self.tmp, ["readme"], "# R\n\nX. [Evidenced — src/Real.java:99]\n")
        issues = c.check_tags_and_citations(self.tmp, self.repo)
        self.assertTrue(any("points past the end" in i for i in issues))

    def test_malformed_tag_flagged(self):
        # Hyphen instead of the required em dash.
        write_docs(self.tmp, ["readme"], "# R\n\nX. [Evidenced - src/Real.java:2]\n")
        issues = c.check_tags_and_citations(self.tmp, self.repo)
        self.assertTrue(any("malformed" in i for i in issues))

    def test_citations_skipped_without_target_repo(self):
        write_docs(self.tmp, ["readme"], "# R\n\nX. [Evidenced — src/Ghost.java:2]\n")
        self.assertEqual(c.check_tags_and_citations(self.tmp, None), [])


class PorcelainParseTest(unittest.TestCase):
    def test_plain_paths(self):
        self.assertEqual(c.parse_porcelain("?? docs/readme.md\n M src/A.java\n"),
                         ["docs/readme.md", "src/A.java"])

    def test_rename_takes_destination(self):
        self.assertEqual(c.parse_porcelain("R  old/A.java -> new/B.java\n"), ["new/B.java"])

    def test_quoted_path_with_spaces(self):
        self.assertEqual(c.parse_porcelain('?? "docs/my file.md"\n'), ["docs/my file.md"])

    def test_blank_lines_ignored(self):
        self.assertEqual(c.parse_porcelain("\n\n"), [])


class WriteScopeTest(unittest.TestCase):
    """The structural replacement for doc-writer.md's 'write to exactly the
    path given and nowhere else'."""

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        (self.repo / "src").mkdir()
        (self.repo / "src" / "A.java").write_text("class A {}\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "init"], cwd=self.repo, check=True)
        self.docs = self.repo / "docs"
        self.docs.mkdir()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_writes_confined_to_docs_are_clean(self):
        write_docs(self.docs, VALID_DOC_FILES)
        self.assertEqual(c.check_target_repo_writes(self.repo, self.docs), [])

    def test_write_outside_docs_is_flagged(self):
        write_docs(self.docs, VALID_DOC_FILES)
        (self.repo / "src" / "A.java").write_text("class A { /* clobbered */ }\n", encoding="utf-8")
        issues = c.check_target_repo_writes(self.repo, self.docs)
        self.assertTrue(any("A.java" in i for i in issues))

    def test_docs_outside_repo_means_repo_must_be_untouched(self):
        external = Path(tempfile.mkdtemp())
        try:
            write_docs(external, VALID_DOC_FILES)
            self.assertEqual(c.check_target_repo_writes(self.repo, external), [])
            (self.repo / "src" / "A.java").write_text("touched\n", encoding="utf-8")
            issues = c.check_target_repo_writes(self.repo, external)
            self.assertTrue(any("A.java" in i for i in issues))
        finally:
            shutil.rmtree(external, ignore_errors=True)

    def test_non_git_target_is_reported_not_crashed(self):
        plain = Path(tempfile.mkdtemp())
        try:
            issues = c.check_target_repo_writes(plain, plain / "docs")
            self.assertTrue(any("not a git checkout" in i for i in issues))
        finally:
            shutil.rmtree(plain, ignore_errors=True)


class ExitCodeTest(unittest.TestCase):
    def test_clean_is_zero(self):
        self.assertEqual(c.exit_code([]), 0)

    def test_issues_fail(self):
        self.assertEqual(c.exit_code(["something"]), 1)

    def test_there_is_no_enforce_toggle(self):
        self.assertFalse(hasattr(c, "ENFORCE"))


if __name__ == "__main__":
    unittest.main()
