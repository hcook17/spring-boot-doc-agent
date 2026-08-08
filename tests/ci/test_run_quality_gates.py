"""Tests for scripts/ci/run_quality_gates.py — portable hard-gate runner."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import run_quality_gates as qg


class RunQualityGatesTest(unittest.TestCase):
    def test_gate_new_code_coverage_uses_python_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / "coverage.xml"
            xml.write_text("<coverage/>", encoding="utf-8")
            captured: list[list[str]] = []

            def fake_run(command: list[str], *, label: str) -> int:
                captured.append(command)
                return 0

            with mock.patch.object(qg, "_run", side_effect=fake_run):
                code = qg.gate_new_code_coverage("origin/main", xml)
            self.assertEqual(code, 0)
            self.assertEqual(captured[0][0], sys.executable)
            self.assertEqual(captured[0][1:3], ["-m", "diff_cover.diff_cover_tool"])
            self.assertIn(str(xml), captured[0])

    def test_gate_import_cycles_uses_tach_module(self) -> None:
        captured: list[list[str]] = []

        def fake_run(command: list[str], *, label: str) -> int:
            captured.append(command)
            return 0

        with mock.patch.object(qg, "_run", side_effect=fake_run):
            self.assertEqual(qg.gate_import_cycles(), 0)
        self.assertEqual(captured[0][:4], [sys.executable, "-m", "tach", "check"])

    def test_gate_duplication_uses_jscpd_command(self) -> None:
        captured: list[list[str]] = []

        def fake_run(command: list[str], *, label: str) -> int:
            captured.append(command)
            return 0

        with (
            mock.patch.object(
                qg,
                "changed_python_under_packages",
                return_value=["src/doc_engine/a.py", "src/doc_engine/b.py"],
            ),
            mock.patch.object(
                qg,
                "jscpd_command",
                return_value=["/bin/jscpd", "--threshold=3", "a.py", "b.py"],
            ) as jscpd,
            mock.patch.object(qg, "_run", side_effect=fake_run),
        ):
            self.assertEqual(qg.gate_duplication("HEAD~1"), 0)
        jscpd.assert_called_once()
        self.assertEqual(captured[0][0], "/bin/jscpd")

    def test_gate_duplication_skips_when_no_changed_files(self) -> None:
        with mock.patch.object(qg, "changed_python_under_packages", return_value=[]):
            self.assertEqual(qg.gate_duplication("HEAD~1"), 0)

    def test_main_skip_coverage_omits_diff_cover(self) -> None:
        with (
            mock.patch.object(qg, "gate_duplication", return_value=0),
            mock.patch.object(qg, "gate_cognitive_complexity", return_value=0),
            mock.patch.object(qg, "gate_import_cycles", return_value=0),
            mock.patch.object(qg, "gate_new_code_coverage") as cov,
        ):
            code = qg.main(
                ["--compare-ref", "HEAD~1", "--skip-coverage"]
            )
        self.assertEqual(code, 0)
        cov.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
