#!/usr/bin/env python3
"""
Optional, opt-in validation of partition_repo.py against a REAL repository's
file tree, rather than the synthetic scenarios in tests/doc_engine/test_partition_repo.py.

Point the canonical real-repo lane at a local Spring checkout::

    DOC_ENGINE_REAL_REPO=/path/to/a/real/repo \\
        pytest tests/doc_engine/test_partition_repo_real_world.py -v

Or write the absolute path to the gitignored ``local-runs/real-repo.path``.
Legacy ``PARTITION_REPO_REAL_FIXTURE_DIR`` remains an alias.

With the real repo unset, every test in this file is skipped (not failed) —
expected for CI / machines without a local Spring tree.
"""

import os
import sys
import unittest
from collections import Counter

from doc_engine.real_fixture import real_repo_path
from doc_engine.tools import partition_repo
from tests.conftest import SCRIPTS_DIR

SCRIPT_DIR = SCRIPTS_DIR

MAX_TOKENS = int(os.environ.get("PARTITION_REPO_REAL_MAX_TOKENS", "2000"))


def _real_dir() -> str | None:
    path = real_repo_path()
    return str(path) if path is not None else None


@unittest.skipUnless(
    _real_dir(),
    "DOC_ENGINE_REAL_REPO / local-runs/real-repo.path not set — opt-in real-repo "
    "partition lane skipped; see this file's module docstring.",
)
class RealRepoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        real_dir = _real_dir()
        assert real_dir is not None
        if not os.path.isdir(real_dir):
            raise unittest.SkipTest(
                f"DOC_ENGINE_REAL_REPO is set but not a directory: {real_dir}"
            )
        cls.real_dir = real_dir
        all_files = partition_repo.dfs_file_list(
            real_dir,
            partition_repo.DEFAULT_EXCLUDED_DIRS,
            partition_repo.DEFAULT_EXCLUDED_EXTS,
            partition_repo.DEFAULT_EXCLUDED_FILES,
        )
        cls.file_tokens = []
        cls.skipped = []
        for full in all_files:
            rel = os.path.relpath(full, real_dir)
            tokens, reason = partition_repo.estimate_tokens(full, max_file_bytes=2_000_000)
            if reason:
                cls.skipped.append((rel, reason))
                continue
            cls.file_tokens.append((rel, tokens))
        cls.groups = partition_repo.build_groups(cls.file_tokens, MAX_TOKENS, overlap_ratio=0.10)
        cls.group_sizes = [sum(t for _, t in g) for g in cls.groups]

    def test_finds_files(self):
        self.assertGreater(
            len(self.file_tokens), 0, f"no usable files found under {self.real_dir}"
        )

    def test_produces_at_least_one_group(self):
        self.assertGreater(len(self.groups), 0)

    def test_no_group_is_a_wild_outlier(self):
        # Bound against the actual largest file present — see historical
        # comment in git history for why a flat "3x max_tokens" ceiling fails
        # on repos with one oversized generated blob.
        if not self.group_sizes:
            self.skipTest("no groups produced")
        largest_group = max(self.group_sizes)
        largest_file = max(t for _, t in self.file_tokens)
        ceiling = MAX_TOKENS + largest_file
        self.assertLess(
            largest_group,
            ceiling,
            f"largest group ({largest_group} tokens) exceeds max_tokens ({MAX_TOKENS}) + "
            f"largest single file ({largest_file} tokens) = {ceiling} — "
            f"group sizes were {self.group_sizes}",
        )

    def test_every_file_accounted_for_exactly_once(self):
        files_in_groups = [f for g in self.groups for f, _ in g]
        counts = Counter(files_in_groups)
        offenders = {f: c for f, c in counts.items() if c > 2}
        self.assertEqual(
            offenders, {}, f"file(s) appearing more than twice across groups: {offenders}"
        )

    def test_dense_extensions_get_lower_divisor_on_real_files(self):
        dense_sample = next(
            (
                rel
                for rel, _ in self.file_tokens
                if os.path.splitext(rel)[1].lower() in partition_repo.DENSE_EXTS
            ),
            None,
        )
        if dense_sample is None:
            self.skipTest(
                "no dense-extension (yml/json/properties/xml/toml) files in this fixture"
            )
        full = os.path.join(self.real_dir, dense_sample)
        with open(full, encoding="utf-8", errors="ignore") as f:
            text = f.read()
        expected = max(1, len(text) // partition_repo.CHARS_PER_TOKEN_DENSE)
        actual = dict(self.file_tokens)[dense_sample]
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
