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

import os
import shutil
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

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
        # share to absorb. Verified by hand against both the old and new
        # build_groups() implementations before being locked in here — see
        # the review doc's "Resolution, part 3" for the full trace.
        file_tokens = [(f"small{i}.txt", 20) for i in range(6)] + [(f"big{i}.txt", 90) for i in range(12)]
        max_tokens = 100

        groups = partition_repo.build_groups(file_tokens, max_tokens, overlap_ratio=0.10)
        group_sizes = [sum(t for _, t in g) for g in groups]

        # The old code produced a final group of 270 tokens here — 2.7x
        # max_tokens, and dramatically larger than every other group in the
        # same run (all 180 or smaller). That's the bug: not that groups
        # can ever slightly exceed max_tokens (they can, everywhere, since
        # this partitions at file granularity and can't split a file
        # mid-token — see the module docstring), but that the *last* group
        # specifically had no ceiling at all, unlike every other group.
        self.assertEqual(group_sizes, [100, 130, 180, 180, 180, 180, 180, 180, 180, 180, 180, 180, 180, 90])
        self.assertEqual(max(group_sizes), 180, "final group must not be an outlier vs. the rest of the distribution")
        self.assertNotEqual(max(group_sizes), 270, "this is the exact unbounded-last-group value the old code produced")

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
        # Here, small.txt + giant.txt (900 tokens, 9x max_tokens) close the
        # first group. Carrying giant.txt whole into the next group isn't
        # "a bit of overlap" - it's a duplicate of the entire file, and
        # because that next group now starts already past max_tokens before
        # a single new file is added, it closes again immediately and
        # re-carries giant.txt again. Verified against the unfixed
        # build_groups(): this exact scenario produced 3 groups with
        # giant.txt in every one of them, instead of the 2 groups / 1
        # occurrence asserted below.
        file_tokens = [("small.txt", 50), ("giant.txt", 900), ("after.txt", 30)]
        groups = partition_repo.build_groups(file_tokens, max_tokens=100, overlap_ratio=0.10)
        files_in_groups = [f for g in groups for f, _ in g]

        self.assertEqual(
            files_in_groups.count("giant.txt"), 1,
            "an oversized trailing file must not be duplicated into subsequent "
            f"groups via overlap carry; got groups: {[[f for f, _ in g] for g in groups]}",
        )
        self.assertEqual(len(groups), 2)
        self.assertEqual([f for f, _ in groups[1]], ["after.txt"])


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


if __name__ == "__main__":
    unittest.main()
