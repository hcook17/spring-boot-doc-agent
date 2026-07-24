#!/usr/bin/env python3
"""
Unit tests for check_llms_coverage.py's mechanical bits: frontmatter parsing
and coverage diffing. No live `gh` calls here — that's exercised for real
every time this repo's CI runs check_llms_coverage.py itself, same split
test_verify_llms_docs.py draws against verify_llms_docs.py.

Run with:
    python3 scripts/test_check_llms_coverage.py -v
"""

import os
import pathlib
import sys
import tempfile
import textwrap
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import check_llms_coverage as c  # noqa: E402


def write_doc(tmp_dir, name, text):
    path = pathlib.Path(tmp_dir) / name
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


class ParseFrontmatterTest(unittest.TestCase):
    def test_parses_known_fields(self):
        d = tempfile.mkdtemp()
        p = write_doc(d, "pr-1.md", """\
            ---
            pr: 1
            title: Some title
            state: MERGED
            merge_commit: abc123
            ---

            # PR #1
            """)
        fields = c.parse_frontmatter(p)
        self.assertEqual(fields["pr"], "1")
        self.assertEqual(fields["state"], "MERGED")

    def test_no_frontmatter_returns_empty(self):
        d = tempfile.mkdtemp()
        p = write_doc(d, "pr-2.md", "# no frontmatter here\n")
        self.assertEqual(c.parse_frontmatter(p), {})


class CheckCoverageTest(unittest.TestCase):
    def _llms_dir(self, files):
        d = tempfile.mkdtemp()
        for name, text in files.items():
            write_doc(d, name, text)
        return pathlib.Path(d)

    def test_missing_doc_is_flagged(self):
        llms_dir = self._llms_dir({})
        merged = [{"number": 9, "title": "Add claude/llms/"}]
        issues = c.check_coverage(merged, llms_dir)
        self.assertEqual(len(issues), 1)
        self.assertIn("pr-9.md is missing", issues[0])

    def test_existing_merged_doc_is_clean(self):
        llms_dir = self._llms_dir({
            "pr-1.md": """\
                ---
                pr: 1
                state: MERGED
                ---
                # PR #1
                """
        })
        merged = [{"number": 1, "title": "x"}]
        issues = c.check_coverage(merged, llms_dir)
        self.assertEqual(issues, [])

    def test_stale_open_state_on_merged_pr_is_flagged(self):
        # The exact pr-13.md drift this script exists to catch.
        llms_dir = self._llms_dir({
            "pr-13.md": """\
                ---
                pr: 13
                state: OPEN
                ---
                # PR #13
                """
        })
        merged = [{"number": 13, "title": "x"}]
        issues = c.check_coverage(merged, llms_dir)
        self.assertEqual(len(issues), 1)
        self.assertIn("state: OPEN", issues[0])

    def test_multiple_missing_docs_all_reported(self):
        llms_dir = self._llms_dir({})
        merged = [{"number": n, "title": "x"} for n in (10, 11, 12)]
        issues = c.check_coverage(merged, llms_dir)
        self.assertEqual(len(issues), 3)

    def test_missing_state_field_is_not_flagged_as_stale(self):
        # Absent `state:` shouldn't be treated as a mismatch — only an
        # explicit non-MERGED value should trip the stale-state check.
        llms_dir = self._llms_dir({
            "pr-1.md": """\
                ---
                pr: 1
                ---
                # PR #1
                """
        })
        merged = [{"number": 1, "title": "x"}]
        issues = c.check_coverage(merged, llms_dir)
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
