"""Tests that ScanContext is wired into ast-grep and CodeQL cache paths."""

import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest import mock

from doc_engine.core.context import FileEntry, ScanContext
from doc_engine.scanning._scanner_astgrep import (
    AstGrepBackend,
    chunk_paths_for_argv,
)
from doc_engine.scanning.support._codeql_runner import (
    DEFAULT_PACK_DIR,
    _cache_key,
    _repo_content_hash,
)
from tests.conftest import FIXTURE_DIR


class ChunkPathsForArgvTest(unittest.TestCase):
    def test_single_chunk_when_under_budget(self):
        base = ["ast-grep", "scan"]
        paths = ["a.java", "b.java"]
        chunks = chunk_paths_for_argv(base, paths, limit=10_000)
        self.assertEqual(chunks, [paths])

    def test_splits_when_over_budget(self):
        base = ["ast-grep"]  # len 8 + 1 = 9
        # Each path costs len+1; budget after base ≈ 20 → one short path per chunk.
        paths = ["abcdefghij.java", "klmnopqrst.java", "uvwxyz0123.java"]
        chunks = chunk_paths_for_argv(base, paths, limit=30)
        self.assertEqual(len(chunks), 3)
        self.assertEqual([p for chunk in chunks for p in chunk], paths)

    def test_oversized_solo_path_still_emitted(self):
        base = ["ast-grep"]
        huge = "x" * 100
        chunks = chunk_paths_for_argv(base, [huge, "ok.java"], limit=20)
        self.assertEqual(chunks[0], [huge])
        self.assertIn(["ok.java"], chunks)


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

    def test_run_ast_grep_chunks_paths_instead_of_repo_root_fallback(self):
        backend = AstGrepBackend()
        ctx = ScanContext.build(str(FIXTURE_DIR))
        if len(ctx.java_files) < 2:
            self.skipTest("fixture needs >=2 java files to observe chunking")

        with mock.patch.object(backend, "_find_ast_grep", return_value="/bin/ast-grep"):
            with mock.patch(
                "doc_engine.scanning._scanner_astgrep._PATH_LIST_CHAR_LIMIT", 10,
            ):
                with mock.patch("subprocess.run") as run_mock:
                    run_mock.return_value = mock.Mock(returncode=0, stdout="[]", stderr="")
                    backend._run_ast_grep(str(FIXTURE_DIR), java_files=ctx.java_files)

        self.assertGreater(run_mock.call_count, 1)
        seen = []
        for call in run_mock.call_args_list:
            cmd = call[0][0]
            self.assertNotEqual(cmd[-1], str(FIXTURE_DIR))
            # Every argv after the base flags is an inventory path, not repo root.
            for entry in ctx.java_files:
                if entry.full_path in cmd:
                    seen.append(entry.full_path)
        self.assertEqual(sorted(set(seen)), sorted(e.full_path for e in ctx.java_files))

    def test_chunking_warns_and_never_mentions_repo_root_fallback(self):
        backend = AstGrepBackend()
        ctx = ScanContext.build(str(FIXTURE_DIR))
        if len(ctx.java_files) < 2:
            self.skipTest("fixture needs >=2 java files to observe chunking")

        err = io.StringIO()
        with mock.patch.object(backend, "_find_ast_grep", return_value="/bin/ast-grep"):
            with mock.patch(
                "doc_engine.scanning._scanner_astgrep._PATH_LIST_CHAR_LIMIT", 10,
            ):
                with mock.patch("subprocess.run") as run_mock:
                    run_mock.return_value = mock.Mock(returncode=0, stdout="[]", stderr="")
                    with contextlib.redirect_stderr(err):
                        backend._run_ast_grep(str(FIXTURE_DIR), java_files=ctx.java_files)

        text = err.getvalue()
        self.assertIn("preserve ScanContext inventory", text)
        self.assertNotIn("scanning repo root instead", text)

    def test_chunked_matches_equivalent_to_single_invocation(self):
        """Path-list vs artificially-budgeted batches: same concatenated matches."""
        backend = AstGrepBackend()
        entries = [
            FileEntry(
                full_path=f"/repo/F{i}.java",
                rel_path=f"F{i}.java",
                name=f"F{i}.java",
                ext=".java",
            )
            for i in range(4)
        ]

        def _stdout_for_cmd(cmd, **_kwargs):
            files = [p for p in cmd if str(p).endswith(".java")]
            payload = [{"file": f, "ruleId": "persistence__entity"} for f in files]
            return mock.Mock(returncode=0, stdout=json.dumps(payload), stderr="")

        with mock.patch.object(backend, "_find_ast_grep", return_value="/bin/ast-grep"):
            with mock.patch(
                "doc_engine.scanning._scanner_astgrep._PATH_LIST_CHAR_LIMIT", 2**31,
            ):
                with mock.patch("subprocess.run", side_effect=_stdout_for_cmd) as one_mock:
                    single = backend._run_ast_grep("/repo", java_files=entries)
            with mock.patch(
                "doc_engine.scanning._scanner_astgrep._PATH_LIST_CHAR_LIMIT", 40,
            ):
                with mock.patch("subprocess.run", side_effect=_stdout_for_cmd) as many_mock:
                    chunked = backend._run_ast_grep("/repo", java_files=entries)

        self.assertEqual(one_mock.call_count, 1)
        self.assertGreater(many_mock.call_count, 1)
        self.assertEqual(single, chunked)
        self.assertEqual([m["file"] for m in single], [e.full_path for e in entries])

    def test_run_ast_grep_none_inventory_uses_repo_root(self):
        """Legacy path: java_files is None still scans repo root intentionally."""
        backend = AstGrepBackend()
        with mock.patch.object(backend, "_find_ast_grep", return_value="/bin/ast-grep"):
            with mock.patch("subprocess.run") as run_mock:
                run_mock.return_value = mock.Mock(returncode=0, stdout="[]", stderr="")
                backend._run_ast_grep(str(FIXTURE_DIR), java_files=None)

        cmd = run_mock.call_args[0][0]
        self.assertEqual(cmd[-1], str(FIXTURE_DIR))
        self.assertTrue(any(part == "--globs" for part in cmd))

    def test_run_ast_grep_bisects_on_winerror_206(self):
        backend = AstGrepBackend()
        entries = [
            FileEntry(
                full_path=f"/repo/A{i}.java",
                rel_path=f"A{i}.java",
                name=f"A{i}.java",
                ext=".java",
            )
            for i in range(4)
        ]
        win_exc = OSError(22, "filename or extension is too long")
        win_exc.winerror = 206

        # First call: whole inventory hits WinError 206; subsequent halves succeed.
        responses = [
            win_exc,
            mock.Mock(returncode=0, stdout='[{"file":"/repo/A0.java"}]', stderr=""),
            mock.Mock(returncode=0, stdout='[{"file":"/repo/A2.java"}]', stderr=""),
        ]

        def _run(cmd, **_kwargs):
            item = responses.pop(0)
            if isinstance(item, OSError):
                raise item
            return item

        with mock.patch.object(backend, "_find_ast_grep", return_value="/bin/ast-grep"):
            with mock.patch("subprocess.run", side_effect=_run) as run_mock:
                matches = backend._run_ast_grep("/repo", java_files=entries)

        self.assertEqual(run_mock.call_count, 3)
        self.assertEqual(len(matches), 2)
        for call in run_mock.call_args_list:
            cmd = call[0][0]
            # Inventory paths only — never a bare repo-root argv.
            self.assertTrue(any(str(p).endswith(".java") for p in cmd))
            self.assertNotEqual(cmd[-1], "/repo")


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
