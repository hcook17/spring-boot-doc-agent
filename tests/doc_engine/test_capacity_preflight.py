#!/usr/bin/env python3
"""
Unit tests for capacity_preflight.py.

Two things are checked: the fan-out/threshold arithmetic in
compute_preflight() (pure, in-memory — no need for a real repo), and that
_load_or_build_groups()/_load_or_build_edges() genuinely delegate to
partition_repo.py/build_cross_group_edges.py's own functions on a real
fixture tree rather than re-implementing DFS/token-estimation/join logic —
reusing
scripts/fixtures/spring_signals/ (the same fixture
tests/doc_engine/test_spring_signal_scan.py, tests/doc_engine/test_pipeline_stages.py, and
tests/doc_engine/test_spring_drift_check.py already share) rather than building a second
fixture tree, per this project's own stated anti-duplication norm
(IMPLEMENTATION_HANDOFF.md item 1/4).

Run with:
    pytest tests/doc_engine/test_capacity_preflight.py -v
"""

import os
import sys
import unittest
from tests.conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH
from doc_engine.tools import (
    build_cross_group_edges,
    capacity_preflight,
    partition_repo,
    spring_signal_scan,
)

SCRIPT_DIR = SCRIPTS_DIR


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


class Stage4PartialProxyTest(unittest.TestCase):
    """L2 honesty: Stage-0 proxy mirrors pipeline SoR, does not claim full bound."""

    def test_stage4_fanout_tracks_valid_doc_files(self):
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(2), edges=_edges_data(2),
        )
        self.assertEqual(
            report["stage_fanout"]["stage4_doc_writer"],
            len(capacity_preflight.VALID_DOC_FILES),
        )
        self.assertEqual(
            capacity_preflight.STAGE4_FIXED_FANOUT,
            len(capacity_preflight.VALID_DOC_FILES),
        )

    def test_stage0_invocation_mirror_omits_interview(self):
        """Mirror stages.py capacity_preflight argv: groups + signals, no interview."""
        groups = _groups_data(3)
        for g in groups["groups"]:
            g["est_tokens"] = 1_000
        report = capacity_preflight.compute_preflight(
            "/fake/repo",
            groups_data=groups,
            edges=_edges_data(3),
            signals_data={"evidence": {"references": []}},
            group_warn_threshold=1000,
            fanout_warn_threshold=1000,
            stage4_shared_tokens_warn_threshold=10_000_000,
        )
        self.assertEqual(report["stage4_metric_kind"], "partial_proxy_pre_stage4")
        self.assertIn("interview_answers", report["stage4_omitted_not_estimated"])
        self.assertIn(
            "architecture_merge_beyond_summary_proxy",
            report["stage4_omitted_not_estimated"],
        )
        self.assertIn("stage4_return_payloads", report["stage4_omitted_not_estimated"])
        self.assertFalse(report["stage4_return_payloads_estimated"])
        self.assertFalse(report["stage4_signals_omitted"])
        self.assertNotEqual(report["stage4_metric_kind"], "upper_bound")
        # Numeric fields may still say upper_bound in the name; kind must not.
        self.assertIn("partial_proxy", report["stage4_metric_kind"])

    def test_signals_omitted_flag_when_no_signals(self):
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=_groups_data(2), edges=_edges_data(2),
            signals_data=None,
            group_warn_threshold=1000, fanout_warn_threshold=1000,
            stage4_shared_tokens_warn_threshold=10_000_000,
        )
        self.assertTrue(report["stage4_signals_omitted"])
        self.assertEqual(report["stage4_signals_est_tokens"], 0)

    def test_signals_increase_stage4_proxy(self):
        groups = _groups_data(2)
        for g in groups["groups"]:
            g["est_tokens"] = 100
        bare = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=groups, edges=_edges_data(2),
            group_warn_threshold=1000, fanout_warn_threshold=1000,
            stage4_shared_tokens_warn_threshold=10_000_000,
        )
        with_signals = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=groups, edges=_edges_data(2),
            signals_data={"evidence": {"pad": "y" * 4000}},
            group_warn_threshold=1000, fanout_warn_threshold=1000,
            stage4_shared_tokens_warn_threshold=10_000_000,
        )
        self.assertGreater(
            with_signals["stage4_shared_pool_upper_bound_est_tokens"],
            bare["stage4_shared_pool_upper_bound_est_tokens"],
        )
        self.assertGreater(with_signals["stage4_signals_est_tokens"], 0)

    def test_stage4_warning_fires_when_slice_is_quiet(self):
        """Polarity: Stage-1 slice under threshold must not hide Stage-4 proxy."""
        groups = _groups_data(5)
        for g in groups["groups"]:
            g["est_tokens"] = 25_000  # shared proxy = 125_000 > 80_000
        report = capacity_preflight.compute_preflight(
            "/fake/repo",
            groups_data=groups,
            edges=_edges_data(5, arcs_per_group=0),
            group_warn_threshold=1000,
            fanout_warn_threshold=1000,
            slice_tokens_warn_threshold=30_000,
            stage4_shared_tokens_warn_threshold=80_000,
        )
        dims = {w["dimension"] for w in report["warnings"]}
        self.assertNotIn("stage1_slice_est_tokens_max", dims)
        self.assertIn("stage4_shared_pool_upper_bound_est_tokens", dims)
        stage4_warn = next(
            w for w in report["warnings"]
            if w["dimension"] == "stage4_shared_pool_upper_bound_est_tokens"
        )
        self.assertIn("partial_proxy_pre_stage4", stage4_warn["message"])

    def test_stage4_warning_absent_under_threshold(self):
        groups = _groups_data(2)
        for g in groups["groups"]:
            g["est_tokens"] = 100
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=groups, edges=_edges_data(2),
            group_warn_threshold=1000, fanout_warn_threshold=1000,
            stage4_shared_tokens_warn_threshold=80_000,
        )
        dims = {w["dimension"] for w in report["warnings"]}
        self.assertNotIn("stage4_shared_pool_upper_bound_est_tokens", dims)

    def test_omitted_list_matches_pipeline_doc_writer_gap(self):
        """Omitted set must include interview — a real doc_writer input_artifact."""
        from doc_engine.pipeline.stages import build_stage_specs, StageKind
        from doc_engine.pipeline.artifacts import ARTIFACT_FILENAMES

        doc_writer = next(
            s for s in build_stage_specs()
            if s.name == "doc_writer" and s.kind == StageKind.GENERATIVE
        )
        self.assertIn(ARTIFACT_FILENAMES["interview_answers"], doc_writer.input_artifacts)
        self.assertIn(
            "interview_answers",
            capacity_preflight.STAGE4_PROXY_OMITTED,
        )


class Stage4MeasuredCalibrationTest(unittest.TestCase):
    """L2b: on-disk Stage-4 inputs; returns still unestimated; default 80k unchanged."""

    def test_measured_includes_interview_and_flags_returns(self):
        summaries = [{"file": "a.java", "summary": "x" * 400}]
        interview = {"q1": "answer " * 50}
        signals = {"evidence": {"references": [{"pad": "z" * 200}]}}
        measured = capacity_preflight.measure_stage4_shared_pool_tokens(
            summaries, interview_answers=interview, signals_data=signals,
        )
        self.assertEqual(measured["metric_kind"], "measured_stage4_inputs")
        self.assertIn("summaries", measured["included_now"])
        self.assertIn("interview_answers", measured["included_now"])
        self.assertIn("spring_signals", measured["included_now"])
        self.assertFalse(measured["interview_answers_omitted"])
        self.assertFalse(measured["signals_omitted"])
        self.assertIn("stage4_return_payloads", measured["omitted_not_estimated"])
        self.assertNotIn("interview_answers", measured["omitted_not_estimated"])
        self.assertFalse(measured["return_payloads_estimated"])
        self.assertGreater(measured["interview_answers_est_tokens"], 0)
        self.assertGreater(measured["shared_pool_upper_bound_est_tokens"],
                           measured["summaries_est_tokens"])

    def test_measured_omits_interview_when_absent(self):
        measured = capacity_preflight.measure_stage4_shared_pool_tokens(
            [{"file": "a.java", "summary": "short"}],
        )
        self.assertTrue(measured["interview_answers_omitted"])
        self.assertEqual(measured["interview_answers_est_tokens"], 0)
        self.assertIn("interview_answers", measured["omitted_not_estimated"])
        self.assertIn("stage4_return_payloads", measured["omitted_not_estimated"])
        self.assertTrue(measured["signals_omitted"])

    def test_calibration_warns_on_measured_pool(self):
        # Pad enough that chars/N exceeds a low threshold.
        summaries = [{"pad": "y" * 20_000}]
        report = capacity_preflight.compute_stage4_calibration(
            "/fake/repo",
            summaries_data=summaries,
            interview_answers={"a": "b" * 1000},
            signals_data={"evidence": {}},
            stage4_shared_tokens_warn_threshold=100,
        )
        self.assertEqual(report["mode"], "stage4_calibration")
        self.assertEqual(report["stage4_metric_kind"], "measured_stage4_inputs")
        dims = {w["dimension"] for w in report["warnings"]}
        self.assertIn("stage4_shared_pool_upper_bound_est_tokens", dims)
        self.assertIn("measured_stage4_inputs", report["warnings"][0]["message"])
        self.assertFalse(report["stage4_return_payloads_estimated"])

    def test_proxy_comparison_from_groups(self):
        groups = _groups_data(2)
        for g in groups["groups"]:
            g["est_tokens"] = 5_000
        summaries = [{"pad": "s" * 400}]
        report = capacity_preflight.compute_stage4_calibration(
            "/fake/repo",
            summaries_data=summaries,
            interview_answers={"pad": "i" * 400},
            signals_data={"evidence": {"pad": "z" * 2000}},
            groups_data=groups,
            stage4_shared_tokens_warn_threshold=10_000_000,
        )
        cmp_ = report["stage4_proxy_comparison"]
        self.assertIsNotNone(cmp_)
        self.assertEqual(cmp_["proxy_metric_kind"], "partial_proxy_pre_stage4")
        self.assertEqual(cmp_["measured_metric_kind"], "measured_stage4_inputs")
        self.assertEqual(cmp_["proxy_source"], "groups_est_tokens_proxy")
        # Groups-path proxy excludes signals so the ratio is about summaries.
        self.assertEqual(cmp_["stage0_proxy_shared_est_tokens"], 10_000)
        self.assertGreater(cmp_["measured_shared_est_tokens"], 0)
        self.assertIsNotNone(cmp_["measured_over_proxy_ratio"])
        self.assertNotIn(
            "stage4_proxy_comparison_source",
            {w["dimension"] for w in report["warnings"]},
        )

    def test_proxy_comparison_from_stage0_report(self):
        stage0 = {
            "stage4_metric_kind": "partial_proxy_pre_stage4",
            "stage4_summaries_est_tokens": 1000,
            "stage4_signals_est_tokens": 100,
            "stage4_shared_pool_upper_bound_est_tokens": 1100,
        }
        report = capacity_preflight.compute_stage4_calibration(
            "/fake/repo",
            summaries_data=[{"x": "y" * 800}],
            stage0_preflight_report=stage0,
            stage4_shared_tokens_warn_threshold=10_000_000,
        )
        cmp_ = report["stage4_proxy_comparison"]
        self.assertEqual(cmp_["stage0_proxy_shared_est_tokens"], 1100)
        self.assertEqual(cmp_["measured_metric_kind"], "measured_stage4_inputs")
        self.assertEqual(cmp_["proxy_source"], "stage0_preflight_report")

    def test_both_proxy_sources_prefers_stage0_report_and_warns(self):
        groups = _groups_data(2)
        for g in groups["groups"]:
            g["est_tokens"] = 50_000  # would dominate if wrongly chosen
        stage0 = {
            "stage4_metric_kind": "partial_proxy_pre_stage4",
            "stage4_summaries_est_tokens": 1000,
            "stage4_signals_est_tokens": 0,
            "stage4_shared_pool_upper_bound_est_tokens": 1000,
        }
        report = capacity_preflight.compute_stage4_calibration(
            "/fake/repo",
            summaries_data=[{"x": "y" * 100}],
            groups_data=groups,
            stage0_preflight_report=stage0,
            stage4_shared_tokens_warn_threshold=10_000_000,
        )
        cmp_ = report["stage4_proxy_comparison"]
        self.assertEqual(cmp_["proxy_source"], "stage0_preflight_report")
        self.assertEqual(cmp_["stage0_proxy_shared_est_tokens"], 1000)
        dims = {w["dimension"] for w in report["warnings"]}
        self.assertIn("stage4_proxy_comparison_source", dims)

    def test_default_stage4_threshold_unchanged(self):
        """L2b must not silently recalibrate the Stage-0 / L2b default (80k)."""
        import inspect

        for fn in (
            capacity_preflight.compute_preflight,
            capacity_preflight.compute_stage4_calibration,
        ):
            default = inspect.signature(fn).parameters[
                "stage4_shared_tokens_warn_threshold"
            ].default
            self.assertEqual(default, 80_000, msg=fn.__name__)

        groups = _groups_data(2)
        for g in groups["groups"]:
            g["est_tokens"] = 100
        report = capacity_preflight.compute_preflight(
            "/fake/repo", groups_data=groups, edges=_edges_data(2),
            group_warn_threshold=1000, fanout_warn_threshold=1000,
        )
        self.assertEqual(report["stage4_metric_kind"], "partial_proxy_pre_stage4")
        self.assertNotIn(
            "stage4_shared_pool_upper_bound_est_tokens",
            {w["dimension"] for w in report["warnings"]},
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

    def test_edges_match_build_cross_group_edges_direct_run(self):
        # _load_or_build_edges() must hand off to build_report() rather than
        # re-deriving the package/import join a second way.
        data = spring_signal_scan.scan(
            FIXTURE_DIR, scanners=["filesystem", "ast-grep"],
        )
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
        scanned = spring_signal_scan.scan(FIXTURE_DIR, scanners=["filesystem", "ast-grep"])
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
