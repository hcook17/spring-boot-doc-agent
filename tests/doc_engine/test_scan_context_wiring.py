"""Tests that ScanContext is wired into ast-grep and CodeQL cache paths."""

import os
import unittest
from pathlib import Path
from unittest import mock

from doc_engine.core.context import FileEntry, ScanContext
from doc_engine.scanning._scanner_astgrep import AstGrepBackend
from doc_engine.scanning.support._codeql_runner import (
    DEFAULT_PACK_DIR,
    _cache_key,
    _repo_content_hash,
)
from tests.conftest import FIXTURE_DIR


class AstGrepScanContextWiringTest(unittest.TestCase):
    def test_run_ast_grep_uses_java_files_from_context(self):
        backend = AstGrepBackend()
        ctx = ScanContext.build(str(FIXTURE_DIR))
        expected_paths = sorted(entry.full_path for entry in ctx.java_files)

        with mock.patch.object(backend, "_find_ast_grep", return_value="/bin/ast-grep"):
            with mock.patch("subprocess.run") as run_mock:
                run_mock.return_value = mock.Mock(returncode=0, stdout="[]", stderr="")
                backend._run_ast_grep(str(FIXTURE_DIR), java_files=ctx.java_files)

        cmd = run_mock.call_args[0][0]
        for path in expected_paths:
            self.assertIn(path, cmd)
        self.assertNotIn(str(FIXTURE_DIR), cmd)

    def test_run_ast_grep_empty_java_files_skips_subprocess(self):
        backend = AstGrepBackend()
        with mock.patch.object(backend, "_find_ast_grep", return_value="/bin/ast-grep"):
            with mock.patch("subprocess.run") as run_mock:
                result = backend._run_ast_grep(str(FIXTURE_DIR), java_files=[])
        self.assertEqual(result, [])
        run_mock.assert_not_called()

    def test_run_ast_grep_falls_back_to_repo_scan_when_path_list_too_long(self):
        backend = AstGrepBackend()
        ctx = ScanContext.build(str(FIXTURE_DIR))
        if not ctx.java_files:
            self.skipTest("fixture has no java files")

        with mock.patch.object(backend, "_find_ast_grep", return_value="/bin/ast-grep"):
            with mock.patch(
                "doc_engine.scanning._scanner_astgrep._PATH_LIST_CHAR_LIMIT", 10,
            ):
                with mock.patch("subprocess.run") as run_mock:
                    run_mock.return_value = mock.Mock(returncode=0, stdout="[]", stderr="")
                    backend._run_ast_grep(str(FIXTURE_DIR), java_files=ctx.java_files)

        cmd = run_mock.call_args[0][0]
        self.assertIn(str(FIXTURE_DIR), cmd)
        for entry in ctx.java_files:
            self.assertNotIn(entry.full_path, cmd)


class CodeQLScanContextWiringTest(unittest.TestCase):
    def test_repo_content_hash_uses_context_signatures(self):
        repo = Path(FIXTURE_DIR)
        ctx = ScanContext.build(str(repo))
        with_hash = _repo_content_hash(repo, scan_context=ctx)
        without_hash = _repo_content_hash(repo, scan_context=None)
        self.assertNotEqual(with_hash, without_hash)

    def test_cache_key_changes_when_context_signature_changes(self):
        repo = Path(FIXTURE_DIR)
        ctx = ScanContext.build(str(repo))
        build_command = "gradlew clean compileJava"
        key_before = _cache_key(repo, DEFAULT_PACK_DIR, build_command, scan_context=ctx)

        if not ctx.java_files:
            self.skipTest("fixture has no java files")
        rel = ctx.java_files[0].rel_path
        ctx.file_signatures[rel] = "mutated-signature"

        key_after = _cache_key(repo, DEFAULT_PACK_DIR, build_command, scan_context=ctx)
        self.assertNotEqual(key_before, key_after)

    def test_cache_key_includes_build_command(self):
        repo = Path(FIXTURE_DIR)
        ctx = ScanContext.build(str(repo))
        key_compile = _cache_key(repo, DEFAULT_PACK_DIR, "gradlew compileJava", scan_context=ctx)
        key_test = _cache_key(repo, DEFAULT_PACK_DIR, "gradlew compileTestJava", scan_context=ctx)
        self.assertNotEqual(key_compile, key_test)


if __name__ == "__main__":
    unittest.main()
