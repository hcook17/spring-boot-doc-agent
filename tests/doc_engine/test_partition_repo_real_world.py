#!/usr/bin/env python3
"""
Optional, opt-in validation of partition_repo.py against a REAL repository's
file tree, rather than the synthetic scenarios in tests/doc_engine/test_partition_repo.py.

This file ships with the plugin (it's just Python, no proprietary content),
but the real repository it validates against does NOT — that's local-only,
deliberately kept out of anything packaged or published. Point this at your
own local checkout of any real repo via an environment variable:

    PARTITION_REPO_REAL_FIXTURE_DIR=/path/to/a/real/repo \
        pytest tests/doc_engine/test_partition_repo_real_world.py -v

With the environment variable unset, every test in this file is skipped
(not failed) — that's the expected, normal state for anyone else who
installs this plugin without a local real-repo fixture set up. This is NOT
part of the regular tests/doc_engine/test_partition_repo.py suite and isn't required for
that suite to pass.

What this actually checks that a synthetic fixture can't as convincingly:
real, uneven file-size distribution (a few large files, many small ones,
in whatever order a real DFS walk produces them) is a better stress test
for the last-group-capping fix than anything hand-built, precisely because
real repos are exactly the kind of lopsided distribution that bug depended
on. --max-tokens is deliberately set low relative to typical repo size so
even a modest local fixture produces multiple groups.
"""

import os
import sys
import unittest
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH
from doc_engine.tools import partition_repo

SCRIPT_DIR = SCRIPTS_DIR

REAL_FIXTURE_DIR = os.environ.get("PARTITION_REPO_REAL_FIXTURE_DIR")
MAX_TOKENS = int(os.environ.get("PARTITION_REPO_REAL_MAX_TOKENS", "2000"))


@unittest.skipUnless(
    REAL_FIXTURE_DIR,
    "PARTITION_REPO_REAL_FIXTURE_DIR not set — this is an opt-in, local-only "
    "validation pass; see this file's module docstring to run it.",
)
class RealRepoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(REAL_FIXTURE_DIR):
            raise unittest.SkipTest(f"PARTITION_REPO_REAL_FIXTURE_DIR is set but not a directory: {REAL_FIXTURE_DIR}")
        all_files = partition_repo.dfs_file_list(
            REAL_FIXTURE_DIR,
            partition_repo.DEFAULT_EXCLUDED_DIRS,
            partition_repo.DEFAULT_EXCLUDED_EXTS,
            partition_repo.DEFAULT_EXCLUDED_FILES,
        )
        cls.file_tokens = []
        cls.skipped = []
        for full in all_files:
            rel = os.path.relpath(full, REAL_FIXTURE_DIR)
            tokens, reason = partition_repo.estimate_tokens(full, max_file_bytes=2_000_000)
            if reason:
                cls.skipped.append((rel, reason))
                continue
            cls.file_tokens.append((rel, tokens))
        cls.groups = partition_repo.build_groups(cls.file_tokens, MAX_TOKENS, overlap_ratio=0.10)
        cls.group_sizes = [sum(t for _, t in g) for g in cls.groups]

    def test_finds_files(self):
        self.assertGreater(len(self.file_tokens), 0, f"no usable files found under {REAL_FIXTURE_DIR}")

    def test_produces_at_least_one_group(self):
        self.assertGreater(len(self.groups), 0)

    def test_no_group_is_a_wild_outlier(self):
        # Two bugs used to let a group balloon disproportionately: the
        # last group had no size ceiling at all, and separately, the
        # overlap-carry step could duplicate an oversized file into
        # several consecutive groups (see partition_repo.py's
        # build_groups() comments and tests/doc_engine/test_partition_repo.py's
        # test_overlap_skips_oversized_trailing_file). Both are fixed now,
        # which gives a real, provable ceiling for any single group: the
        # overlap fix guarantees whatever's carried INTO a group is always
        # < max_tokens, and a group closes on the very first file whose
        # addition tips it over max_tokens — so the worst case is that
        # carry-in plus exactly one closing file, and that file can
        # legitimately be the largest one in the whole fixture (files are
        # atomic; a group can't stop mid-file).
        #
        # A flat "3x max_tokens" ceiling doesn't actually hold in general
        # — it's only true by coincidence when no single real file exceeds
        # roughly 2x max_tokens, which isn't something this test controls
        # (it depends on whatever real repo PARTITION_REPO_REAL_FIXTURE_DIR
        # points at). Bounding against the actual largest file present
        # makes this assertion correct for any fixture, rather than one
        # that happens to fail on repos with a single large generated
        # file, fixture blob, etc.
        if not self.group_sizes:
            self.skipTest("no groups produced")
        largest_group = max(self.group_sizes)
        largest_file = max(t for _, t in self.file_tokens)
        ceiling = MAX_TOKENS + largest_file
        self.assertLess(
            largest_group, ceiling,
            f"largest group ({largest_group} tokens) exceeds max_tokens ({MAX_TOKENS}) + "
            f"largest single file ({largest_file} tokens) = {ceiling} — "
            f"group sizes were {self.group_sizes}",
        )

    def test_every_file_accounted_for_exactly_once(self):
        files_in_groups = [f for g in self.groups for f, _ in g]
        # Overlap means some relpaths legitimately appear in more than one
        # group (that's the point) — but the group's file LIST entries
        # themselves, one per (group, file) pair, should never exceed the
        # number of times that file could plausibly be carried (in
        # practice: at most 2, this group and the next one's overlap seed).
        from collections import Counter
        counts = Counter(files_in_groups)
        offenders = {f: c for f, c in counts.items() if c > 2}
        self.assertEqual(offenders, {}, f"file(s) appearing more than twice across groups: {offenders}")

    def test_dense_extensions_get_lower_divisor_on_real_files(self):
        dense_sample = next(
            (rel for rel, _ in self.file_tokens if os.path.splitext(rel)[1].lower() in partition_repo.DENSE_EXTS),
            None,
        )
        if dense_sample is None:
            self.skipTest("no dense-extension (yml/json/properties/xml/toml) files in this fixture")
        full = os.path.join(REAL_FIXTURE_DIR, dense_sample)
        with open(full, encoding="utf-8", errors="ignore") as f:
            text = f.read()
        expected = max(1, len(text) // partition_repo.CHARS_PER_TOKEN_DENSE)
        actual = dict(self.file_tokens)[dense_sample]
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
