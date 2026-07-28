#!/usr/bin/env python3
"""
Unit tests for check_llms_coverage.py's mechanical bits: frontmatter parsing
and coverage diffing, including the most-recently-merged-PR grace window
(see check_llms_coverage.py's own "GRACE WINDOW" docstring section for why
it exists). No live `gh` calls here — that's exercised for real every time
this repo's CI runs check_llms_coverage.py itself, same split
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
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

SCRIPT_DIR = SCRIPTS_DIR
import check_llms_coverage as c  # noqa: E402


def write_doc(tmp_dir, name, text):
    path = pathlib.Path(tmp_dir) / name
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def pr(number, title="x", merged_at="2026-01-01T00:00:00Z"):
    return {"number": number, "title": title, "mergedAt": merged_at}


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


class MostRecentlyMergedTest(unittest.TestCase):
    def test_empty_list_returns_none(self):
        self.assertIsNone(c.most_recently_merged([]))

    def test_single_pr_is_the_most_recent(self):
        self.assertEqual(c.most_recently_merged([pr(5)]), 5)

    def test_picks_latest_by_mergedAt_not_by_number(self):
        # Lower PR number merged later — mergedAt must win, not number order.
        merged = [
            pr(10, merged_at="2026-01-05T00:00:00Z"),
            pr(9, merged_at="2026-01-06T00:00:00Z"),
        ]
        self.assertEqual(c.most_recently_merged(merged), 9)


class CheckCoverageTest(unittest.TestCase):
    def _llms_dir(self, files):
        d = tempfile.mkdtemp()
        for name, text in files.items():
            write_doc(d, name, text)
        return pathlib.Path(d)

    def test_missing_doc_is_flagged(self):
        llms_dir = self._llms_dir({
            "pr-10.md": """\
                ---
                pr: 10
                state: MERGED
                ---
                # PR #10
                """
        })
        merged = [
            pr(9, title="Add claude/llms/", merged_at="2026-01-01T00:00:00Z"),
            pr(10, merged_at="2026-01-02T00:00:00Z"),  # newest -- exempt, has a doc anyway
        ]
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
        merged = [pr(1)]
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
                """,
            "pr-14.md": """\
                ---
                pr: 14
                state: MERGED
                ---
                # PR #14
                """,
        })
        merged = [
            pr(13, merged_at="2026-01-01T00:00:00Z"),
            pr(14, merged_at="2026-01-02T00:00:00Z"),  # newest -- exempt
        ]
        issues = c.check_coverage(merged, llms_dir)
        self.assertEqual(len(issues), 1)
        self.assertIn("state: OPEN", issues[0])

    def test_multiple_missing_docs_all_reported(self):
        llms_dir = self._llms_dir({})
        merged = [
            pr(10, merged_at="2026-01-01T00:00:00Z"),
            pr(11, merged_at="2026-01-02T00:00:00Z"),
            pr(12, merged_at="2026-01-03T00:00:00Z"),  # newest -- exempt
        ]
        issues = c.check_coverage(merged, llms_dir)
        self.assertEqual(len(issues), 2)

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
        merged = [pr(1)]
        issues = c.check_coverage(merged, llms_dir)
        self.assertEqual(issues, [])

    def test_most_recently_merged_pr_with_no_doc_is_not_flagged(self):
        # The grace window: the single most-recently-merged PR gets a pass
        # on the missing-doc check.
        llms_dir = self._llms_dir({})
        merged = [pr(16, merged_at="2026-07-24T03:31:44Z")]
        issues = c.check_coverage(merged, llms_dir)
        self.assertEqual(issues, [])

    def test_older_pr_with_no_doc_still_flagged_even_if_newest_is_exempt(self):
        llms_dir = self._llms_dir({})
        merged = [
            pr(16, merged_at="2026-07-24T03:31:44Z"),  # older -- not exempt
            pr(17, merged_at="2026-07-24T03:38:08Z"),  # newest -- exempt
        ]
        issues = c.check_coverage(merged, llms_dir)
        self.assertEqual(len(issues), 1)
        self.assertIn("pr-16.md is missing", issues[0])

    def test_most_recently_merged_pr_with_stale_state_is_not_flagged(self):
        llms_dir = self._llms_dir({
            "pr-17.md": """\
                ---
                pr: 17
                state: OPEN
                ---
                # PR #17
                """
        })
        merged = [pr(17, merged_at="2026-07-24T03:38:08Z")]
        issues = c.check_coverage(merged, llms_dir)
        self.assertEqual(issues, [])

    def test_single_pr_total_with_no_doc_is_fully_exempt(self):
        # Matches the very first PR in a repo's history -- no prior PR could
        # have documented it, and there's no "next" PR yet to force it.
        llms_dir = self._llms_dir({})
        merged = [pr(1)]
        issues = c.check_coverage(merged, llms_dir)
        self.assertEqual(issues, [])


class ExitCodeTest(unittest.TestCase):
    def test_no_issues_is_always_zero_regardless_of_enforce(self):
        self.assertEqual(c.exit_code([], enforce=True), 0)
        self.assertEqual(c.exit_code([], enforce=False), 0)

    def test_issues_fail_when_enforced(self):
        self.assertEqual(c.exit_code(["something"], enforce=True), 1)

    def test_issues_are_non_blocking_when_not_enforced(self):
        self.assertEqual(c.exit_code(["something"], enforce=False), 0)


if __name__ == "__main__":
    unittest.main()
