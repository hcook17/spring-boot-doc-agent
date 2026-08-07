"""Tests for CodeQL CLI discovery without machine-local fallbacks."""

import os
import unittest
from pathlib import Path
from unittest import mock

from doc_engine.scanning.support._codeql_runner import CodeQLNotFoundError, find_codeql


class FindCodeqlTest(unittest.TestCase):
    def test_uses_doc_engine_codeql_env(self):
        fake = Path(__file__).resolve()
        with mock.patch.dict(os.environ, {"DOC_ENGINE_CODEQL": str(fake)}, clear=False):
            with mock.patch("doc_engine.scanning.support._codeql_runner.shutil.which", return_value=None):
                self.assertEqual(find_codeql(), fake)

    def test_uses_path_when_env_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DOC_ENGINE_CODEQL", None)
            with mock.patch(
                "doc_engine.scanning.support._codeql_runner.shutil.which",
                return_value=r"C:\tools\codeql\codeql.exe",
            ):
                self.assertEqual(find_codeql(), Path(r"C:\tools\codeql\codeql.exe"))

    def test_raises_when_missing(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DOC_ENGINE_CODEQL", None)
            with mock.patch("doc_engine.scanning.support._codeql_runner.shutil.which", return_value=None):
                with self.assertRaises(CodeQLNotFoundError) as ctx:
                    find_codeql()
        self.assertNotIn("Users\\16145", str(ctx.exception))
        self.assertIn("DOC_ENGINE_CODEQL", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
