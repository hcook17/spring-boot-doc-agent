#!/usr/bin/env python3
"""Tests for scripts/ci/suite_layout.py."""

from pathlib import Path
import tempfile
import unittest

import suite_layout


class SuiteLayoutTest(unittest.TestCase):
    def test_reads_testpaths_from_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                "[tool.pytest.ini_options]\ntestpaths = [\"tests\"]\n",
                encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "ci").mkdir()
            (root / "tests" / "ci" / "test_a.py").write_text(
                "def test_x():\n    pass\n", encoding="utf-8")
            (root / "scripts").mkdir()
            (root / "scripts" / "test_a.py").write_text(
                "def test_x():\n    pass\n", encoding="utf-8")
            self.assertEqual(suite_layout.suite_roots(root), ["tests"])
            self.assertTrue(suite_layout.uses_pytest_discovery(root))
            paths = suite_layout.suite_paths(root)
            self.assertEqual([p.name for p in paths], ["test_a.py"])
            self.assertEqual(
                suite_layout.suite_file_for_module(root, "a.py"),
                root / "tests" / "ci" / "test_a.py")

    def test_rglob_finds_nested_suites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "tests" / "doc_engine"
            nested.mkdir(parents=True)
            (nested / "test_nested.py").write_text(
                "def test_x():\n    pass\n", encoding="utf-8")
            (root / "tests" / "test_flat.py").write_text(
                "def test_x():\n    pass\n", encoding="utf-8")
            cache = root / "tests" / "__pycache__"
            cache.mkdir()
            (cache / "test_cached.py").write_text(
                "def test_x():\n    pass\n", encoding="utf-8")
            names = [p.name for p in suite_layout.suite_paths(root)]
            self.assertEqual(names, ["test_nested.py", "test_flat.py"])
            self.assertEqual(
                suite_layout.suite_file_for_module(root, "nested.py"),
                nested / "test_nested.py")

    def test_default_roots_without_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(suite_layout.suite_roots(root), ["tests"])
            self.assertFalse(suite_layout.uses_pytest_discovery(root))


if __name__ == "__main__":
    unittest.main(verbosity=2)
