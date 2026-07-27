#!/usr/bin/env python3
"""
Unit tests for capacity_preflight.py.

Two things are checked: the fan-out/threshold arithmetic in
compute_preflight() (pure, in-memory — no need for a real repo), and that
_load_or_build_groups()/_load_or_build_edges() genuinely delegate to
partition_repo.py/build_cross_group_edges.py's own functions on a real
fixture tree rather than re-implementing DFS/token-estimation/join logic —
reusing
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

import build_cross_group_edges  # noqa: E402
import capacity_preflight  # noqa: E402
import partition_repo  # noqa: E402


def _groups_data(num_groups, max_tokens=120000):
    return {
        "repo_path": "/fake/repo",
        "max_tokens_per_group": max_tokens,
        "num_groups": num_groups,
        "groups": [{"id": i, "files": [f"f{i}.java"], "est_tokens": 100} for i in range(num_groups)],
    }


def _edges_data(num_groups, arcs_per_group=0, arc_width=0):
    """Synthetic cross_group_edges.json, shaped like build_report()'s output.

    arc_width pads each arc so a slice can be made large enough to trip the
    token threshold without needing thousands of rows."""
    return {
        "num_groups": num_groups,
        "groups": {
            str(i): {
                "outbound": [
                    {"from": f"f{i}.java", "to": f"g{j}.java", "confidence": "exact",
                     "pad": "x" * arc_width}
                    for j in range(arcs_per_group)
                ],
                "inbound": [],
                "same_package_outside": [],
            }
            for i in range(num_groups)
        },
        "stats": {},
    }


def _pkg(path, package):
    return {"file": path, "line": 1, "match": f"package {package};", "rule_id": "references__package"}


def _imp(path, qualified):
    return {"file": path, "line": 2, "match": f"import {qualified};", "rule_id": "references__import"}


class FanoutArithmeticTest(unittest.TestCase):
    def test_total_fanout_formula(self):
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(3), edges=_edges_data(3),
        )
        self.assertEqual(report["stage_fanout"]["stage1_file_summarizer"], 3)
        self.assertEqual(report["stage_fanout"]["stage2_architect_segment"], 3)
        self.assertEqual(report["stage_fanout"]["stage2_architect_merge"], 1)
        self.assertEqual(report["stage_fanout"]["stage3_gap_analyzer"], 1)
        self.assertEqual(report["stage_fanout"]["stage3_software_architect_and_testing"], 1)
        self.assertEqual(report["stage_fanout"]["stage4_doc_writer"], 14)
        # 2*num_groups + 1 (merge) + 1 (gap-analyzer) + 1 (software-architect-
        # and-testing) + 14 (doc-writer) = 2*3+17 = 23
        self.assertEqual(report["total_fanout"], 23)

    def test_single_group_minimum_fanout(self):
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(1), edges=_edges_data(1),
        )
        self.assertEqual(report["total_fanout"], 19)  # 2*1 + 17


class ThresholdWarningTest(unittest.TestCase):
    def test_no_warnings_under_all_thresholds(self):
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(2), edges=_edges_data(2),
            group_warn_threshold=15, fanout_warn_threshold=40,
            slice_tokens_warn_threshold=30_000,
        )
        self.assertEqual(report["warnings"], [])

    def test_group_count_warning_fires(self):
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(20), edges=_edges_data(20),
            group_warn_threshold=15,
        )
        dims = {w["dimension"] for w in report["warnings"]}
        self.assertIn("num_groups", dims)

    def test_fanout_warning_fires(self):
        # 20 groups -> total_fanout = 56, comfortably over a 40 threshold.
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(20), edges=_edges_data(20),
            group_warn_threshold=1000,  # suppress the group-count warning so only fanout is under test
            fanout_warn_threshold=40,
        )
        dims = {w["dimension"] for w in report["warnings"]}
        self.assertIn("total_fanout", dims)
        self.assertNotIn("num_groups", dims)

    def test_stage1_slice_warning_fires(self):
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(50),
            edges=_edges_data(50, arcs_per_group=10, arc_width=1000),
            group_warn_threshold=1000, fanout_warn_threshold=1000,
            slice_tokens_warn_threshold=1000,
        )
        dims = {w["dimension"] for w in report["warnings"]}
        self.assertIn("stage1_slice_est_tokens_max", dims)

    def test_warning_keys_on_the_max_not_the_sum(self):
        # The threshold deliberately guards the largest single dispatch, not
        # the whole-run total: a context window is breached by one dispatch.
        # Many small slices whose sum is large must NOT warn.
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(50),
            edges=_edges_data(50, arcs_per_group=1, arc_width=100),
            group_warn_threshold=1000, fanout_warn_threshold=1000,
            slice_tokens_warn_threshold=1000,
        )
        self.assertGreater(report["stage1_slice_est_tokens_total"], 1000)
        self.assertLess(report["stage1_slice_est_tokens_max"], 1000)
        self.assertEqual(report["warnings"], [])

    def test_splitting_the_same_repo_into_more_groups_does_not_multiply_cost(self):
        """The inverse of what this file used to assert.

        The deleted `test_references_bucket_tokens_scale_with_group_count`
        pinned the broadcast model as an invariant: per-dispatch payload
        constant, total strictly rising with group count — i.e. cost = |R| x g.
        Commit abd3ade replaced the broadcast with a partitioned join, so that
        relationship no longer holds, and the test kept passing anyway because
        it exercised capacity_preflight's own arithmetic rather than the
        pipeline's behavior. It was defending code that had already been
        removed.

        What actually holds now: shipped volume is bounded by the *cut*, not
        by the reference count times the group count. Same files, same
        imports, more groups -> more arcs cut, but each group ships only its
        own boundary, and the total stays far under the broadcast equivalent.
        """
        refs = [_pkg(f"p{i}/C{i}.java", f"p{i}") for i in range(8)]
        refs += [_imp(f"p{i}/C{i}.java", f"p{i + 1}.C{i + 1}") for i in range(7)]
        files = [f"p{i}/C{i}.java" for i in range(8)]

        def report_for(group_sizes):
            groups = []
            start = 0
            for n in group_sizes:
                groups.append({"id": len(groups), "files": files[start:start + n], "est_tokens": 100})
                start += n
            groups_data = {"repo_path": "/fake/repo", "max_tokens_per_group": 120000,
                           "num_groups": len(groups), "groups": groups}
            edges = build_cross_group_edges.build_report(
                groups_data, {"evidence": {"references": refs}})
            return capacity_preflight.compute_preflight(
                "/fake/repo", groups_data=groups_data, edges=edges,
                group_warn_threshold=1000, fanout_warn_threshold=1000)

        two = report_for([4, 4])
        eight = report_for([1] * 8)

        # More groups cuts more arcs, so total shipped does rise ...
        self.assertGreaterEqual(eight["stage1_slice_est_tokens_total"],
                                two["stage1_slice_est_tokens_total"])
        # ... but the per-dispatch payload does NOT stay constant the way a
        # broadcast's would, which is the actual behavioral difference.
        self.assertLess(eight["stage1_slice_est_tokens_max"],
                        eight["stage1_slice_est_tokens_total"])
        # And the join's own accounting must agree it beat broadcasting.
        stats = eight["edge_join_stats"]
        self.assertLess(stats["rows_shipped"], stats["broadcast_rows_avoided"])


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

    def test_edges_match_build_cross_group_edges_direct_run(self):
        # _load_or_build_edges() must hand off to build_report() rather than
        # re-deriving the package/import join a second way.
        import spring_signal_scan
        data = spring_signal_scan.scan(FIXTURE_DIR)
        self.assertIn("references", data["evidence"])

        groups_data = capacity_preflight._load_or_build_groups(
            FIXTURE_DIR, max_tokens=120000, overlap=0.10, groups_file=None,
        )
        direct = build_cross_group_edges.build_report(groups_data, data)
        via_preflight = capacity_preflight._load_or_build_edges(
            FIXTURE_DIR, None, groups_data, None,
        )
        self.assertEqual(via_preflight["groups"], direct["groups"])
        self.assertEqual(via_preflight["stats"], direct["stats"])


class PathSeparatorTest(unittest.TestCase):
    """compute_preflight() emitted os-native relative paths while everything
    it is joined against emits forward slashes -- the third occurrence of a
    bug already fixed in spring_drift_check.tier1_scan() and in
    partition_repo.main().

    Note on what runs where, stated rather than left implicit: the assertions
    that merely look for a backslash are only *non-vacuous on Windows*, since
    os.path.relpath never produces one on POSIX. That is exactly why the
    normalization was extracted into partition_repo.to_posix() -- the first
    test below feeds it a backslash-bearing string directly and therefore
    fails on the pre-fix code on every platform, CI included."""

    def test_to_posix_rewrites_separators_on_every_platform(self):
        self.assertEqual(partition_repo.to_posix(r"src\main\java\Foo.java"),
                         "src/main/java/Foo.java")

    def test_to_posix_leaves_forward_slashes_alone(self):
        self.assertEqual(partition_repo.to_posix("src/main/java/Foo.java"),
                         "src/main/java/Foo.java")

    def test_relpath_posix_never_returns_a_backslash(self):
        nested = os.path.join(FIXTURE_DIR, "src", "main")
        self.assertNotIn("\\", partition_repo.relpath_posix(nested, FIXTURE_DIR))

    def test_preflight_group_files_carry_no_backslashes(self):
        groups = capacity_preflight._load_or_build_groups(
            FIXTURE_DIR, max_tokens=120000, overlap=0.10, groups_file=None,
        )
        offenders = [f for g in groups["groups"] for f in g["files"] if "\\" in f]
        self.assertEqual(offenders, [], f"backslash-bearing paths: {offenders[:5]}")

    def test_preflight_paths_match_the_scanner_they_are_joined_against(self):
        """The invariant that actually matters. capacity_preflight's group
        file lists are joined by path against spring_signals.json inside
        build_report(); if the two sides spell the same file differently the
        join silently yields nothing, which is how this stayed invisible."""
        import spring_signal_scan
        scanned = spring_signal_scan.scan(FIXTURE_DIR)
        scanned_files = {row["file"] for rows in scanned["evidence"].values()
                         for row in rows if isinstance(row, dict) and "file" in row}

        groups = capacity_preflight._load_or_build_groups(
            FIXTURE_DIR, max_tokens=120000, overlap=0.10, groups_file=None,
        )
        grouped_files = {f for g in groups["groups"] for f in g["files"]}

        # Every file the scanner produced evidence for must be spelled
        # identically on the partitioner's side. A separator mismatch makes
        # this intersection empty rather than raising.
        self.assertTrue(scanned_files, "fixture produced no evidence rows at all")
        self.assertTrue(scanned_files & grouped_files,
                        "no scanned file matched any grouped file -- the join "
                        "these two artifacts depend on produces nothing")


if __name__ == "__main__":
    unittest.main()
