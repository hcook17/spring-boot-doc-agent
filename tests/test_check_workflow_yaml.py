"""Tests for scripts/check_workflow_yaml.py — #57-class YAML parse gate."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from check_workflow_yaml import check_workflows


class WorkflowYamlParseTest(unittest.TestCase):
    def test_committed_workflows_parse(self):
        self.assertEqual(check_workflows(), [])

    def test_unquoted_colon_in_step_name_is_caught(self):
        """Reproduction of the PR #57 Actions failure shape."""
        bad = (
            "name: CI\n"
            "on: [push]\n"
            "jobs:\n"
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: check (advisory: broken)\n"
            "        run: echo hi\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.yml"
            path.write_text(bad, encoding="utf-8")
            errors = check_workflows(Path(tmp))
        self.assertTrue(errors, msg="expected parse failure for unquoted colon")
        self.assertTrue(any("bad.yml" in e for e in errors))

    def test_quoted_colon_in_step_name_passes(self):
        good = (
            "name: CI\n"
            "on: [push]\n"
            "jobs:\n"
            "  test:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            '      - name: "check (advisory: ok)"\n'
            "        run: echo hi\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "good.yml"
            path.write_text(good, encoding="utf-8")
            self.assertEqual(check_workflows(Path(tmp)), [])


if __name__ == "__main__":
    unittest.main()
