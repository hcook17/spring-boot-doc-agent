"""Benchmark: ast-grep vs text search on the Spring signals fixture.

Proves the mandate is about citation precision, not agent convenience.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests.conftest import FIXTURE_DIR, REPO_ROOT


class SearchMethodologyBenchmarkTest(unittest.TestCase):
    """Fixture-backed cases that justify the no-grep policy for agents."""

    FIXTURE = FIXTURE_DIR

    def _java_files(self) -> list[Path]:
        return list(self.FIXTURE.rglob("*.java"))

    def test_fixture_has_java_sources(self) -> None:
        self.assertGreater(len(self._java_files()), 0)

    def test_ast_grep_column_with_args_matches_fixture(self) -> None:
        if not shutil.which("ast-grep"):
            self.skipTest("ast-grep not on PATH")
        proc = subprocess.run(
            [
                "ast-grep", "run", "-l", "java", "-p", "@Column($$$)",
                str(self.FIXTURE),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(
            (proc.stdout or "").strip(),
            "expected @Column($$$) to match something in the fixture",
        )

    def test_fixture_documents_entity_scan_false_positive_guard(self) -> None:
        """Misc.java guards against @EntityScan being misread as @Entity (regex era)."""
        misc = self.FIXTURE / "src" / "main" / "java" / "com" / "example" / "billing" / "Misc.java"
        text = misc.read_text(encoding="utf-8")
        self.assertIn("@EntityScan", text)
        self.assertIn("must NOT be picked up", text)

    def test_deny_text_search_blocks_grep_tool(self) -> None:
        hooks = REPO_ROOT / "adapters" / "claude" / "hooks"
        sys.path.insert(0, str(hooks))
        import deny_text_search as dts  # noqa: E402

        self.assertTrue(dts.decide({"tool_name": "Grep"})["deny"])
        self.assertFalse(
            dts.decide({
                "tool_name": "Bash",
                "tool_input": {"command": "ast-grep run -l java -p '@Entity' ."},
            })["deny"],
        )


if __name__ == "__main__":
    unittest.main()
