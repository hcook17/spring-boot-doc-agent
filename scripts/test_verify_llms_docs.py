#!/usr/bin/env python3
"""
Unit tests for verify_llms_docs.py's mechanical bits: command parsing,
worktree-shape classification, and pass/fail evaluation. No live git/gh
calls and no network here — those are exercised for real every time this
repo's CI runs verify_llms_docs.py itself against the actual
claude/llms/pr-*.md files, which is the integration-test layer for this
tool. Deliberately kept separate, same split test_pipeline_stages.py draws
between its synthetic-data pass and its opt-in PIPELINE_ARTIFACTS_DIR pass.

Run with:
    python3 scripts/test_verify_llms_docs.py -v
"""

import os
import sys
import textwrap
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import verify_llms_docs as v  # noqa: E402


def write_doc(tmp_path, text):
    tmp_path.write_text(textwrap.dedent(text), encoding="utf-8")
    return tmp_path


class ParseCommandsTest(unittest.TestCase):
    """Exercises the actual shapes found across claude/llms/pr-1.md..pr-8.md."""

    def _parse(self, text):
        import pathlib
        import tempfile

        d = tempfile.mkdtemp()
        p = pathlib.Path(d) / "pr-99.md"
        write_doc(p, text)
        return v.parse_commands(p)

    def test_single_command_with_own_expect_line(self):
        cmds = self._parse("""\
            ## Deterministic verification

            Pinned to `abc123`:

            1. **Claim: something is true.**
               `git show abc123:README.md | grep -n "x"`
               Expect: one match.
            """)
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0].claim_num, 1)
        self.assertEqual(cmds[0].seq, 1)
        self.assertEqual(cmds[0].text, 'git show abc123:README.md | grep -n "x"')
        self.assertEqual(cmds[0].expect_text, "Expect: one match.")

    def test_two_commands_each_with_own_expect(self):
        cmds = self._parse("""\
            ## Deterministic verification

            1. **Claim: two facts.**
               `git show abc123:a.py | grep -n "x"`
               Expect: one match.
               `git show abc123:b.py | grep -n "y"`
               Expect: one match.
            """)
        self.assertEqual(len(cmds), 2)
        self.assertEqual([c.seq for c in cmds], [1, 2])
        self.assertEqual(cmds[0].expect_text, "Expect: one match.")
        self.assertEqual(cmds[1].expect_text, "Expect: one match.")

    def test_two_commands_sharing_one_trailing_expect(self):
        # pr-6.md claim 4's shape: gh pr view 3 ..., gh pr view 6 ..., single Expect after both.
        cmds = self._parse("""\
            ## Deterministic verification

            1. **Claim: two PRs are distinct.**
               `gh pr view 3 --json headRefName`
               `gh pr view 6 --json headRefName`
               Expect: different SHAs.
            """)
        self.assertEqual(len(cmds), 2)
        self.assertIsNone(cmds[0].expect_text)
        self.assertEqual(cmds[1].expect_text, "Expect: different SHAs.")

    def test_command_embedded_after_non_expect_prose(self):
        # pr-3.md claim 3's shape: a "Cross-check the convention..." lead-in
        # sentence before the backtick span, not a line starting with a
        # backtick or with "Expect:".
        cmds = self._parse("""\
            ## Deterministic verification

            1. **Claim: a convention is matched.**
               `git show abc123:a.py | grep -n "pattern"`
               Expect: one match.
               Cross-check the convention it's matching: `git show abc123:b.py | grep -n "pattern"`
               Expect: the same pattern already present there.
            """)
        self.assertEqual(len(cmds), 2)
        self.assertEqual(cmds[1].text, 'git show abc123:b.py | grep -n "pattern"')
        self.assertEqual(cmds[1].expect_text, "Expect: the same pattern already present there.")

    def test_claim_boundary_resets_pending_and_numbering(self):
        cmds = self._parse("""\
            ## Deterministic verification

            1. **Claim: first.**
               `git show abc123:a.py | grep -n "x"`
            2. **Claim: second.**
               `git show abc123:b.py | grep -n "y"`
               Expect: one match.
            """)
        self.assertEqual([(c.claim_num, c.seq) for c in cmds], [(1, 1), (2, 1)])
        # claim 1's command never got an Expect: line before claim 2 started.
        self.assertIsNone(cmds[0].expect_text)

    def test_non_command_backtick_spans_are_ignored(self):
        # Expect: lines and claim headers routinely contain backtick spans
        # that are not commands (file names, config keys) — must not be
        # mistaken for a git/gh command.
        cmds = self._parse("""\
            ## Deterministic verification

            1. **Claim: `CONSTRAINTS.md` has headings.**
               `git show abc123:CONSTRAINTS.md | grep -n "^## "`
               Expect: `Runtime prerequisites`, `Integration gaps` — 2 headings.
            """)
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0].text, 'git show abc123:CONSTRAINTS.md | grep -n "^## "')

    def test_no_deterministic_verification_section_returns_empty(self):
        cmds = self._parse("""\
            # PR #99 — no verification section

            ## Summary

            Nothing to see here.
            """)
        self.assertEqual(cmds, [])

    def test_section_stops_at_next_heading(self):
        cmds = self._parse("""\
            ## Deterministic verification

            1. **Claim: first.**
               `git show abc123:a.py | grep -n "x"`
               Expect: one match.

            ## Some other section

            `git show should:not | grep -be picked -up`
            """)
        self.assertEqual(len(cmds), 1)


class WorktreeShapeTest(unittest.TestCase):
    def test_recognizes_documented_worktree_shape(self):
        cmd = (
            'git worktree add /tmp/pr1-check 0b7b7de && cd /tmp/pr1-check && '
            'python3 scripts/test_partition_repo.py -v && python3 scripts/test_spring_signal_scan.py -v; '
            'cd - && git worktree remove /tmp/pr1-check'
        )
        self.assertTrue(v.is_worktree_shaped(cmd))
        match = v.WORKTREE_RE.match(cmd)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("path"), "/tmp/pr1-check")
        self.assertEqual(match.group("sha"), "0b7b7de")
        self.assertEqual(
            match.group("rest"),
            "python3 scripts/test_partition_repo.py -v && python3 scripts/test_spring_signal_scan.py -v",
        )

    def test_recognizes_pipe_through_tail_variant(self):
        # pr-8.md's shape: `rest` itself ends in a masking `| tail -N`.
        cmd = (
            'git worktree add /tmp/pr8-check a0acc76 && cd /tmp/pr8-check && '
            'python3 scripts/test_pipeline_stages.py -v 2>&1 | tail -5; '
            'cd - && git worktree remove /tmp/pr8-check'
        )
        match = v.WORKTREE_RE.match(cmd)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("rest"), 'python3 scripts/test_pipeline_stages.py -v 2>&1 | tail -5')

    def test_unrecognized_shape_does_not_match(self):
        cmd = "git worktree add /tmp/x abc123 && echo hi"  # no cd/rest/cleanup tail
        self.assertTrue(v.is_worktree_shaped(cmd))  # still worktree-ish...
        self.assertIsNone(v.WORKTREE_RE.match(cmd))  # ...but not the safe, structured shape

    def test_plain_git_show_is_not_worktree_shaped(self):
        self.assertFalse(v.is_worktree_shaped('git show abc123:README.md | grep -n "x"'))


class EvaluateTest(unittest.TestCase):
    def test_zero_exit_passes_by_default(self):
        self.assertTrue(v.evaluate(0, "some output\n", "", None))

    def test_nonzero_exit_fails_by_default(self):
        self.assertFalse(v.evaluate(1, "", "", "Expect: one match."))

    def test_no_output_expected_passes_on_empty_stdout_even_if_grep_exit_nonzero(self):
        # grep with zero matches exits 1 on purpose — that IS the pass case
        # when the doc says "Expect: no output".
        self.assertTrue(v.evaluate(1, "", "", "Expect: no output — nothing should match."))

    def test_no_output_expected_fails_on_nonempty_stdout(self):
        self.assertFalse(v.evaluate(0, "unexpected line\n", "", "Expect: empty output."))

    def test_fatal_git_error_fails_even_under_no_output_expectation(self):
        self.assertFalse(
            v.evaluate(128, "", "fatal: invalid object name 'deadbeef'.", "Expect: no output.")
        )


if __name__ == "__main__":
    unittest.main()
