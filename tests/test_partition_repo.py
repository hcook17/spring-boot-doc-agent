#!/usr/bin/env python3
"""
Unit tests for partition_repo.py — no external fixtures needed for the
build_groups() tests (they work against in-memory (relpath, tokens) lists,
which is what build_groups() actually consumes), plus a handful of tiny,
fully-synthetic on-disk files for estimate_tokens()'s extension-based
divisor selection.

For an optional, opt-in validation pass against a real repository's actual
file tree and token distribution (closer to what this script sees in
practice than any hand-built scenario), see
test_partition_repo_real_world.py — deliberately a separate file, gated
behind an environment variable, and not something this file depends on.

Run with:
    python3 scripts/test_partition_repo.py -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH

SCRIPT_DIR = SCRIPTS_DIR
import partition_repo  # noqa: E402


class BuildGroupsTest(unittest.TestCase):
    def test_single_group_when_everything_fits(self):
        file_tokens = [("a.py", 10), ("b.py", 20), ("c.py", 30)]
        groups = partition_repo.build_groups(file_tokens, max_tokens=1000, overlap_ratio=0.10)
        self.assertEqual(len(groups), 1)
        self.assertEqual([f for f, _ in groups[0]], ["a.py", "b.py", "c.py"])

    def test_empty_input(self):
        self.assertEqual(partition_repo.build_groups([], max_tokens=1000, overlap_ratio=0.10), [])

    def test_final_group_no_longer_unbounded(self):
        # Regression test for the exact bug the original review flagged:
        # "is_last_group_being_filled suppresses the size ceiling for the
        # final group." Six small (20-token) files up front let the early
        # groups close cheaply; twelve medium (90-token) files in the tail
        # give whichever group is presumed "last" far more than its fair
        # share to absorb.
        #
        # Since this test's original assertions were written, build_groups()
        # was swapped from check-after-append to check-before-append
        # ("strict") semantics — see the module docstring and the strict
        # replacement's own docstring for why. Under strict mode this exact
        # scenario (the handoff's own "Scenario A") now produces 15 groups
        # sized [100,40,20,90,90,90,90,90,90,90,90,90,90,90,90] instead of
        # the old algorithm's 14 groups with a 180-token final group — a
        # different shape, but the same underlying invariant this test
        # exists to protect (the last group is never an outlier vs. the
        # rest of the distribution) still holds, now with an even tighter
        # bound (max_tokens itself, not 1.8x it).
        file_tokens = [(f"small{i}.txt", 20) for i in range(6)] + [(f"big{i}.txt", 90) for i in range(12)]
        max_tokens = 100

        groups = partition_repo.build_groups(file_tokens, max_tokens, overlap_ratio=0.10)
        group_sizes = [sum(t for _, t in g) for g in groups]

        self.assertEqual(group_sizes, [100, 40, 20, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90, 90])
        self.assertEqual(max(group_sizes), max_tokens, "final group must not be an outlier vs. the rest of the distribution")
        self.assertNotEqual(max(group_sizes), 270, "this is the exact unbounded-last-group value the pre-strict-swap code produced")

    def test_single_oversized_file_forms_its_own_group(self):
        # Can't split a file's tokens across groups — a single file bigger
        # than max_tokens must still end up somewhere, alone if necessary.
        # (Pre-existing behavior, unrelated to the last-group fix; guarded
        # here so a future change to the closing condition doesn't quietly
        # break it.)
        file_tokens = [("normal.py", 10), ("huge_generated.py", 5000)]
        groups = partition_repo.build_groups(file_tokens, max_tokens=100, overlap_ratio=0.10)
        files_in_groups = [f for g in groups for f, _ in g]
        self.assertIn("huge_generated.py", files_in_groups)

    def test_overlap_carries_trailing_files_into_next_group(self):
        file_tokens = [(f"f{i}.py", 10) for i in range(20)]
        groups = partition_repo.build_groups(file_tokens, max_tokens=100, overlap_ratio=0.10)
        self.assertGreater(len(groups), 1)
        first_group_files = [f for f, _ in groups[0]]
        second_group_files = [f for f, _ in groups[1]]
        overlap_files = set(first_group_files) & set(second_group_files)
        self.assertTrue(overlap_files, "expected at least one file carried from group 1 into group 2")

    def test_overlap_skips_oversized_trailing_file(self):
        # Regression test for a real bug found by validating build_groups()
        # against a real repo's file tree (see the review doc's "Resolution,
        # part 3"): the overlap-carry loop's stopping condition (`carried >=
        # overlap_budget`) is checked using the value of `carried` from
        # BEFORE the candidate item is added, so as long as the small items
        # scanned so far still leave it under budget, the loop takes one
        # more step back and force-includes whatever's there next - even a
        # single file far bigger than the entire next group's budget.
        #
        # Here, small.txt + giant.txt (900 tokens, 9x max_tokens) used to
        # close the first group under check-after-append. Carrying
        # giant.txt whole into the next group isn't "a bit of overlap" -
        # it's a duplicate of the entire file, and because that next group
        # now starts already past max_tokens before a single new file is
        # added, it closes again immediately and re-carries giant.txt
        # again. Verified against the unfixed build_groups(): this exact
        # scenario produced 3 groups with giant.txt in every one of them.
        #
        # Since this test was written, build_groups() was swapped to
        # check-before-append ("strict") semantics — see the module
        # docstring. Under strict mode, small.txt and giant.txt can no
        # longer even share a group (50 + 900 > 100), so each of the three
        # files ends up alone: [small.txt], [giant.txt], [after.txt]. The
        # duplication invariant this test protects still holds (giant.txt
        # appears exactly once, not chain-duplicated across groups) — the
        # group count changed because strict mode isolates the oversized
        # file instead of merging it with a small neighbor first.
        file_tokens = [("small.txt", 50), ("giant.txt", 900), ("after.txt", 30)]
        groups = partition_repo.build_groups(file_tokens, max_tokens=100, overlap_ratio=0.10)
        files_in_groups = [f for g in groups for f, _ in g]

        self.assertEqual(
            files_in_groups.count("giant.txt"), 1,
            "an oversized trailing file must not be duplicated into subsequent "
            f"groups via overlap carry; got groups: {[[f for f, _ in g] for g in groups]}",
        )
        self.assertEqual(len(groups), 3)
        self.assertEqual([[f for f, _ in g] for g in groups], [["small.txt"], ["giant.txt"], ["after.txt"]])

    def test_strict_mode_zero_progress_guard_prevents_infinite_loop(self):
        """A group whose entire content gets carried forward unchanged,
        followed by a file that still doesn't fit even against that full
        carry, must not retry against unchanged state forever. Regression
        for the infinite loop found while porting build_groups() to
        check-before-append (strict) semantics."""
        file_tokens = [("only.txt", 90), ("trigger.txt", 95)]
        groups = partition_repo.build_groups(file_tokens, max_tokens=100, overlap_ratio=0.10)
        all_files = [f for g in groups for f, _ in g]
        self.assertIn("only.txt", all_files)
        self.assertIn("trigger.txt", all_files)
        for g in groups:
            total = sum(t for _, t in g)
            if total > 100:
                self.assertEqual(len(g), 1, f"group exceeds max_tokens with more than one file: {g}")


class EstimateTokensTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name, content):
        path = os.path.join(self.tmpdir, name)
        with open(path, "w") as f:
            f.write(content)
        return path

    def test_dense_extension_uses_lower_divisor(self):
        # Same content, different extension -> different token estimate.
        # This is the actual fix: structured-data formats (yml/json/etc.)
        # measured meaningfully denser than chars/4 assumes (see the
        # CHARS_PER_TOKEN_DENSE comment in partition_repo.py for the
        # calibration data) - the old flat chars/4 under-counted them.
        content = "x" * 400  # 400 chars
        java_path = self._write("Sample.java", content)
        yml_path = self._write("sample.yml", content)

        java_tokens, _ = partition_repo.estimate_tokens(java_path, max_file_bytes=10_000)
        yml_tokens, _ = partition_repo.estimate_tokens(yml_path, max_file_bytes=10_000)

        self.assertEqual(java_tokens, 400 // partition_repo.CHARS_PER_TOKEN_DEFAULT)
        self.assertEqual(yml_tokens, 400 // partition_repo.CHARS_PER_TOKEN_DENSE)
        self.assertGreater(yml_tokens, java_tokens, "same content should estimate MORE tokens under the dense divisor")

    def test_all_dense_extensions_recognized(self):
        content = "a" * 100
        for ext in sorted(partition_repo.DENSE_EXTS):
            path = self._write(f"sample{ext}", content)
            tokens, reason = partition_repo.estimate_tokens(path, max_file_bytes=10_000)
            self.assertIsNone(reason)
            self.assertEqual(tokens, 100 // partition_repo.CHARS_PER_TOKEN_DENSE, f"extension {ext} not using dense divisor")

    def test_binary_file_skipped(self):
        path = os.path.join(self.tmpdir, "binary.dat")
        with open(path, "wb") as f:
            f.write(b"\x00\x01\x02\x03" * 100)
        tokens, reason = partition_repo.estimate_tokens(path, max_file_bytes=10_000)
        self.assertEqual(tokens, 0)
        self.assertEqual(reason, "binary")

    def test_oversized_file_skipped(self):
        path = self._write("big.txt", "x" * 1000)
        tokens, reason = partition_repo.estimate_tokens(path, max_file_bytes=500)
        self.assertEqual(tokens, 0)
        self.assertIn("too-large", reason)


class RespectGitignoreOptInTest(unittest.TestCase):
    """--respect-gitignore is additive-only: default behavior (flag/spec
    omitted) must be unaffected, and a directory not covered by the
    hardcoded DEFAULT_EXCLUDED_DIRS floor should only disappear when the
    repo's own .gitignore excludes it AND the caller opts in."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, "scratch"))
        with open(os.path.join(self.tmpdir, "scratch", "notes.txt"), "w") as f:
            f.write("not source")
        with open(os.path.join(self.tmpdir, "kept.txt"), "w") as f:
            f.write("kept")
        with open(os.path.join(self.tmpdir, ".gitignore"), "w") as f:
            f.write("scratch/\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _relpaths(self, gitignore_spec):
        files = partition_repo.dfs_file_list(
            self.tmpdir,
            partition_repo.DEFAULT_EXCLUDED_DIRS,
            partition_repo.DEFAULT_EXCLUDED_EXTS,
            partition_repo.DEFAULT_EXCLUDED_FILES,
            gitignore_spec=gitignore_spec,
        )
        return {os.path.relpath(f, self.tmpdir).replace("\\", "/") for f in files}

    def test_scratch_dir_included_without_opt_in(self):
        self.assertEqual(self._relpaths(gitignore_spec=None), {".gitignore", "kept.txt", "scratch/notes.txt"})

    def test_scratch_dir_excluded_with_opt_in(self):
        from _shared_excludes import load_gitignore_spec
        spec = load_gitignore_spec(self.tmpdir)
        self.assertIsNotNone(spec, "pathspec must be installed for this test to be meaningful")
        self.assertEqual(self._relpaths(gitignore_spec=spec), {".gitignore", "kept.txt"})


class EmittedPathSeparatorTest(unittest.TestCase):
    """groups.json's `files` are joined by path against spring_signals.json's
    `file` fields -- Stage 1 slices the evidence by which group each cited file
    falls in. spring_signal_scan.py normalizes every path it emits to forward
    slashes, so partition_repo.py must too.

    Regression: it did not. `main()` used a raw os.path.relpath(), so on Windows
    every nested path came out with backslashes and matched nothing. The failure
    was silent -- Stage 1 subagents received an empty evidence slice rather than
    an error, quietly defeating the "don't rediscover what ast-grep already
    found" design. Caught only by a real end-to-end run against spring-petclinic,
    where 54 of 55 cited files matched no group.

    Third instance of this same bug class in this repo; see spring_drift_check.py's
    tier1_scan() and claude/session-log.md."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        nested = os.path.join(self.tmpdir, "src", "main", "java", "com", "example")
        os.makedirs(nested)
        with open(os.path.join(nested, "Thing.java"), "w") as f:
            f.write("class Thing {}\n")
        with open(os.path.join(self.tmpdir, "root.txt"), "w") as f:
            f.write("root\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_partition(self):
        out = os.path.join(self.tmpdir, "groups.json")
        script = os.path.join(str(SCRIPTS_DIR), "partition_repo.py")
        subprocess.run(
            [sys.executable, script, self.tmpdir, "--out", out],
            check=True, capture_output=True, text=True,
        )
        with open(out) as f:
            return json.load(f)

    def test_emitted_paths_use_forward_slashes(self):
        data = self._run_partition()
        emitted = [f for g in data["groups"] for f in g["files"]]
        self.assertTrue(emitted, "partition produced no files")
        offenders = [f for f in emitted if "\\" in f]
        self.assertEqual(offenders, [], f"backslashes in emitted paths: {offenders}")

    def test_nested_path_matches_signal_scan_style_key(self):
        # The exact join Stage 1 performs, on the shape that actually broke.
        data = self._run_partition()
        emitted = {f for g in data["groups"] for f in g["files"]}
        self.assertIn("src/main/java/com/example/Thing.java", emitted)


if __name__ == "__main__":
    unittest.main()
