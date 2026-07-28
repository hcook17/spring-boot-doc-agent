#!/usr/bin/env python3
"""Contract for hooks/deny_text_search.py, the PreToolUse gate that keeps
agents on structural search.

Sibling suites do not cover this. test_check_repo_claims.py checks the *static*
half of the same policy -- that no agent definition declares Grep -- which is a
different failure surface: an agent can lose the Grep tool and still shell out
to `grep` through Bash. This suite covers the runtime half.

The assertion that earns this file its place is
test_ast_grep_is_never_blocked: `ast-grep` contains the substring `grep`, so
the naive implementation of this hook blocks the exact tool the policy
mandates. That is a self-defeating gate, and it is one substring test away at
all times.

Run with: python3 scripts/test_deny_text_search.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

sys.path.insert(0, str(REPO_ROOT / "adapters" / "claude" / "hooks"))

import deny_text_search as dts  # noqa: E402


def denies(tool: str, command: str = "") -> bool:
    return dts.decide({"tool_name": tool, "tool_input": {"command": command}})["deny"]


class TestGrepTool(unittest.TestCase):
    def test_grep_tool_is_denied(self) -> None:
        self.assertTrue(denies("Grep"))

    def test_unrelated_tools_pass(self) -> None:
        for tool in ("Read", "Glob", "Write", "Edit"):
            self.assertFalse(denies(tool), tool)


class TestAstGrepIsNeverBlocked(unittest.TestCase):
    """The self-defeat guard. Each of these contains the substring 'grep'."""

    SANCTIONED = (
        "ast-grep run -l java -p '@Entity' src",
        "ast-grep scan --rule src/doc_engine/scanning/resources/spring_ast_grep_rules.yml .",
        "ast-grep test",
        "ast-grep --version",
        "cat f.java | ast-grep run --stdin -l java -p '@X'",
        "python scripts/spring_signal_scan.py .",
    )

    def test_ast_grep_is_never_blocked(self) -> None:
        for command in self.SANCTIONED:
            self.assertFalse(denies("Bash", command), command)


class TestTextSearchIsBlocked(unittest.TestCase):
    BLOCKED = (
        "grep -rn foo .",
        "egrep foo f",
        "fgrep foo f",
        "rg foo",
        "cat f | grep foo",
        "ls && grep foo f",
        "/usr/bin/grep foo f",
        "FOO=1 grep foo f",
        "sudo grep foo f",
        "python x.py; grep foo f",
    )

    def test_each_form_is_blocked(self) -> None:
        for command in self.BLOCKED:
            self.assertTrue(denies("Bash", command), command)

    def test_unrelated_bash_passes(self) -> None:
        for command in ("python -m unittest", "git status", "ls -la"):
            self.assertFalse(denies("Bash", command), command)


class TestHeredocBodiesAreData(unittest.TestCase):
    """Regression. This hook blocked its own author mid-session: a heredoc
    carrying a session-log entry quoted a steering prompt whose line began
    with the word "grep", and since a newline is a segment separator, prose
    was tokenized as a command. Text is not executable -- the same category
    of mistake that got verify_llms_docs.py deleted."""

    def test_prose_beginning_with_grep_inside_a_heredoc_is_not_a_command(self) -> None:
        command = (
            "python - <<'PY'\n"
            "entry = '''\n"
            "grep against a consistent per-entry Tags: line, versus an index\n"
            "'''\n"
            "PY"
        )
        self.assertFalse(denies("Bash", command))

    def test_a_real_grep_after_a_heredoc_is_still_caught(self) -> None:
        """Stripping the body must not blind the check to what follows it."""
        command = (
            "python - <<'PY'\n"
            "print(1)\n"
            "PY\n"
            "grep -rn foo ."
        )
        self.assertTrue(denies("Bash", command))

    def test_an_unquoted_heredoc_tag_is_handled(self) -> None:
        self.assertFalse(denies("Bash", "cat <<EOF\ngrep is a word here\nEOF"))


class TestFailOpen(unittest.TestCase):
    def test_unparseable_payload_does_not_block(self) -> None:
        """A hook that cannot read its input must not wedge the session. This
        is a deliberate choice, not an oversight: the static gate in
        check_repo_claims.py is the control that cannot be failed open."""
        self.assertFalse(dts.decide({})["deny"])

    def test_missing_command_key_does_not_block(self) -> None:
        self.assertFalse(dts.decide({"tool_name": "Bash"})["deny"])


class TestDenialExplainsTheAlternative(unittest.TestCase):
    def test_reason_names_ast_grep_and_both_traps(self) -> None:
        """A gate that only says 'no' trains the reader to route around it."""
        reason = dts.decide({"tool_name": "Grep"})["reason"]
        self.assertIn("ast-grep", reason)
        self.assertIn("$$$", reason)
        self.assertIn("UNPROVEN", reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
