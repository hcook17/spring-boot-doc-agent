#!/usr/bin/env python3
"""
Unit tests for capacity_preflight.py.

Two things are checked: the fan-out/threshold arithmetic in
compute_preflight() (pure, in-memory — no need for a real repo), and that
_load_or_build_groups()/_load_or_scan_references() genuinely delegate to
partition_repo.py/spring_signal_scan.py's own functions on a real fixture
tree rather than re-implementing DFS/token-estimation logic — reusing
scripts/test_fixtures/spring_signals/ (the same fixture
test_spring_signal_scan.py, test_pipeline_stages.py, and
test_spring_drift_check.py already share) rather than building a second
fixture tree, per this project's own stated anti-duplication norm
(IMPLEMENTATION_HANDOFF.md item 1/4).

Run with:
    python3 scripts/test_capacity_preflight.py -v
"""

import os
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DIR = os.path.join(SCRIPT_DIR, "test_fixtures", "spring_signals")
sys.path.insert(0, SCRIPT_DIR)

import capacity_preflight  # noqa: E402
import partition_repo  # noqa: E402


def _groups_data(num_groups, max_tokens=120000):
    return {
        "repo_path": "/fake/repo",
        "max_tokens_per_group": max_tokens,
        "num_groups": num_groups,
        "groups": [{"id": i, "files": [f"f{i}.java"], "est_tokens": 100} for i in range(num_groups)],
    }


class FanoutArithmeticTest(unittest.TestCase):
    def test_total_fanout_formula(self):
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(3), references=[],
        )
        self.assertEqual(report["stage_fanout"]["stage1_file_summarizer"], 3)
        self.assertEqual(report["stage_fanout"]["stage2_architect_segment"], 3)
        self.assertEqual(report["stage_fanout"]["stage2_architect_merge"], 1)
        self.assertEqual(report["stage_fanout"]["stage3_gap_analyzer"], 1)
        self.assertEqual(report["stage_fanout"]["stage4_doc_writer"], 14)
        # 2*num_groups + 1 (merge) + 1 (gap-analyzer) + 14 (doc-writer) = 2*3+16 = 22
        self.assertEqual(report["total_fanout"], 22)

    def test_single_group_minimum_fanout(self):
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(1), references=[],
        )
        self.assertEqual(report["total_fanout"], 18)  # 2*1 + 16


class ThresholdWarningTest(unittest.TestCase):
    def test_no_warnings_under_all_thresholds(self):
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(2), references=[],
            group_warn_threshold=15, fanout_warn_threshold=40,
            references_tokens_warn_threshold=500_000,
        )
        self.assertEqual(report["warnings"], [])

    def test_group_count_warning_fires(self):
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(20), references=[],
            group_warn_threshold=15,
        )
        dims = {w["dimension"] for w in report["warnings"]}
        self.assertIn("num_groups", dims)

    def test_fanout_warning_fires(self):
        # 20 groups -> total_fanout = 56, comfortably over a 40 threshold.
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(20), references=[],
            group_warn_threshold=1000,  # suppress the group-count warning so only fanout is under test
            fanout_warn_threshold=40,
        )
        dims = {w["dimension"] for w in report["warnings"]}
        self.assertIn("total_fanout", dims)
        self.assertNotIn("num_groups", dims)

    def test_references_bucket_warning_fires(self):
        big_references = [{"file": "X.java", "line": 1, "text": "x" * 1000} for _ in range(50)]
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(50), references=big_references,
            group_warn_threshold=1000, fanout_warn_threshold=1000,
            references_tokens_warn_threshold=1000,
        )
        dims = {w["dimension"] for w in report["warnings"]}
        self.assertIn("references_bucket_total_across_groups_est_tokens", dims)

    def test_references_bucket_tokens_scale_with_group_count(self):
        references = [{"file": "X.java", "line": 1, "text": "hello world"}]
        report_few = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(2), references=references,
        )
        report_many = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(20), references=references,
        )
        self.assertEqual(report_few["references_bucket_est_tokens"], report_many["references_bucket_est_tokens"])
        self.assertGreater(
            report_many["references_bucket_total_across_groups_est_tokens"],
            report_few["references_bucket_total_across_groups_est_tokens"],
        )


class GenuineDelegationTest(unittest.TestCase):
    """Confirms this script reads partition_repo.py's/spring_signal_scan.py's
    own output rather than re-deriving the numbers a second, independent way."""

    def test_groups_match_partition_repo_direct_run(self):
        preflight_groups = capacity_preflight._load_or_build_groups(
            FIXTURE_DIR, max_tokens=120000, overlap=0.10, groups_file=None,
        )

        all_files = partition_repo.dfs_file_list(
            FIXTURE_DIR, partition_repo.DEFAULT_EXCLUDED_DIRS,
            partition_repo.DEFAULT_EXCLUDED_EXTS, partition_repo.DEFAULT_EXCLUDED_FILES,
        )
        file_tokens = []
        for full in all_files:
            rel = os.path.relpath(full, FIXTURE_DIR)
            tokens, reason = partition_repo.estimate_tokens(full, 2_000_000)
            if reason:
                continue
            file_tokens.append((rel, tokens))
        direct_groups = partition_repo.build_groups(file_tokens, 120000, 0.10)

        self.assertEqual(preflight_groups["num_groups"], len(direct_groups))
        self.assertEqual(preflight_groups["total_files_considered"], len(file_tokens))

    def test_references_bucket_read_from_real_signals_file(self):
        # spring_signal_scan.scan() against the shared fixture repo must
        # produce a `references` bucket (nested under `evidence`, per
        # scan()'s own documented return shape) this script can read.
        import spring_signal_scan
        data = spring_signal_scan.scan(FIXTURE_DIR)
        self.assertIn("references", data["evidence"])
        references = capacity_preflight._load_or_scan_references(FIXTURE_DIR, None)
        self.assertEqual(references, data["evidence"]["references"])


if __name__ == "__main__":
    unittest.main()
