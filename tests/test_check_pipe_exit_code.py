#!/usr/bin/env python3
"""Contract for .claude/hooks/check_pipe_exit_code.py, the PreToolUse(Bash)
gate that blocks a masked exit code after piping a build/test tool into a
filter that discards its own exit status.

Not covered by any sibling suite before this one existed. This hook shipped
2026-07-25 from .claude/hooks/, and hooks/require_hardened_tests.py's own
missing-test check only looked at scripts/ at the time, so nothing ever
required this file to have one -- the same gap test_require_hardened_tests.py
now closes for the next hook. This suite closes it for this hook specifically.

The load-bearing case is the heredoc one. This hook's own docstring records
that it blocked its author writing that exact docstring into
claude/tool-quirks.md: a heredoc body quoting "gradle ... | tail" as prose
was read by an unstripped regex as a live command. deny_text_search.py hit
and fixed the identical mistake for a different matcher.

Run with: python3 scripts/test_check_pipe_exit_code.py -v
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from typing import Dict
from unittest import mock
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / ".claude" / "hooks"))

import check_pipe_exit_code as gate  # noqa: E402


def denies(command: str) -> bool:
    return gate.is_risky(command)


def run_hook(payload: Dict[str, object]) -> str:
    """Run main() end to end over a JSON payload and return whatever it
    printed."""
    captured = io.StringIO()
    with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
         mock.patch.object(sys, "stdout", captured):
        gate.main()
    return captured.getvalue()


BUILD_TOOLS = (
    "gradle build", "./gradlew test", "mvn test", "./mvnw verify",
    "npm test", "pytest", "python3 -m unittest", "cargo test",
    "go test ./...", "dotnet test", "make test",
)

MASKING_FILTERS = (
    "tail -30", "head -5", "grep foo", "wc -l", "sed -n 1p", "awk '{print}'",
)


class BuildToolPipedIntoMaskingFilterTest(unittest.TestCase):
    """The core positive case, exhaustive over the documented cross product:
    every recognized build/test tool piped into every recognized
    exit-code-masking filter must be flagged."""

    def test_every_build_tool_piped_into_every_masking_filter_is_risky(self) -> None:
        for tool in BUILD_TOOLS:
            for filt in MASKING_FILTERS:
                command = f"{tool} | {filt}"
                self.assertTrue(denies(command), command)


class PythonUnittestRegressionTest(unittest.TestCase):
    """claude/tool-quirks.md (2026-07-26) records this exact miss for real:
    `python3 -m unittest discover -s scripts -p "test_*.py" 2>&1 | tail -20`
    passed unflagged, and a real failing suite was masked by `tail`'s own
    exit 0 -- the precise incident this hook exists to prevent, for the
    command this repo's own suites are invoked with constantly."""

    def test_python_m_unittest_discover_piped_into_tail_is_risky(self) -> None:
        self.assertTrue(denies(
            'python3 -m unittest discover -s scripts -p "test_*.py" 2>&1 | tail -20'))

    def test_bare_python_m_unittest_is_risky(self) -> None:
        self.assertTrue(denies("python3 -m unittest | tail -5"))


class EscapeHatchTest(unittest.TestCase):
    def test_pipestatus_suppresses_it(self) -> None:
        self.assertFalse(
            denies("gradle build | tail -30; echo ${PIPESTATUS[0]}"))

    def test_pipefail_suppresses_it(self) -> None:
        self.assertFalse(
            denies("set -o pipefail; gradle build | tail -30"))

    def test_escape_hatch_is_case_insensitive(self) -> None:
        self.assertFalse(denies("gradle build | tail -30 # PipeFail handled"))


class NotRiskyTest(unittest.TestCase):
    def test_masking_filter_with_no_build_tool_is_not_risky(self) -> None:
        self.assertFalse(denies("cat foo.txt | tail -30"))

    def test_build_tool_with_no_masking_filter_is_not_risky(self) -> None:
        self.assertFalse(denies("gradle build > out.log 2>&1"))

    def test_build_tool_piped_into_a_non_masking_command_is_not_risky(self) -> None:
        self.assertFalse(denies("pytest | tee out.log"))

    def test_empty_command_is_not_risky(self) -> None:
        self.assertFalse(denies(""))


class HeredocBodiesAreDataTest(unittest.TestCase):
    """Regression: this hook blocked its own author writing this exact
    docstring's earlier draft into claude/tool-quirks.md, because the
    heredoc body quoted "gradle ... | tail" as prose and an unstripped regex
    read the quotation as a live command."""

    def test_prose_quoting_the_bug_inside_a_heredoc_is_not_risky(self) -> None:
        command = (
            "cat >> claude/tool-quirks.md <<'QUIRK'\n"
            "gradle stage0Oracle --console=plain | tail -30\n"
            "echo \"GRADLE_EXIT=$?\"\n"
            "QUIRK"
        )
        self.assertFalse(denies(command))

    def test_a_real_risky_command_after_a_heredoc_is_still_caught(self) -> None:
        command = (
            "cat >> notes.md <<'EOF'\n"
            "some notes\n"
            "EOF\n"
            "gradle build | tail -30"
        )
        self.assertTrue(denies(command))

    def test_an_unquoted_heredoc_tag_is_handled(self) -> None:
        self.assertFalse(denies(
            "cat <<EOF\ngradle build | tail -30 is just an example\nEOF"))


class FailSafeTest(unittest.TestCase):
    """A hook that cannot read its input, or sees no command, must not
    block -- the same posture hooks/deny_text_search.py and
    hooks/require_hardened_tests.py both take."""

    def test_unparseable_json_does_not_block(self) -> None:
        captured = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO("not json")), \
             mock.patch.object(sys, "stdout", captured):
            self.assertEqual(gate.main(), 0)
        self.assertEqual(captured.getvalue(), "")

    def test_missing_command_key_does_not_block(self) -> None:
        self.assertEqual(
            run_hook({"tool_name": "Bash", "tool_input": {}}), "")

    def test_missing_tool_input_key_does_not_block(self) -> None:
        self.assertEqual(run_hook({"tool_name": "Bash"}), "")


class DenialMessageTest(unittest.TestCase):
    """A gate that only says no teaches people to route around it -- the
    reason must name a working alternative."""

    def test_a_risky_command_produces_a_deny_decision(self) -> None:
        output = run_hook({
            "tool_name": "Bash",
            "tool_input": {"command": "gradle build | tail -30"},
        })
        payload = json.loads(output)["hookSpecificOutput"]
        self.assertEqual(payload["hookEventName"], "PreToolUse")
        self.assertEqual(payload["permissionDecision"], "deny")
        reason = payload["permissionDecisionReason"]
        self.assertIn("PIPESTATUS", reason)
        self.assertIn("pipefail", reason)

    def test_a_safe_command_produces_no_output(self) -> None:
        self.assertEqual(
            run_hook({"tool_name": "Bash", "tool_input": {"command": "git status"}}),
            "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
