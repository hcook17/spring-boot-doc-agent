#!/usr/bin/env python3
"""
Unit tests for build_cross_group_edges.py.

Each test corresponds to one of the ways this join is easy to get wrong, so
the file reads as a list of the traps rather than a list of functions:

  cover semantics     — the grouping overlaps, so "cut" is a set-intersection
                        predicate, not owner(u) != owner(v)
  join key            — resolve to a type, not a package, or the join goes
                        many-to-many and the arc count inflates
  prefix shortening   — static-member and nested-class imports resolve to
                        nothing on a single rsplit, and vanish silently
  clique avoidance    — same-package is an equivalence relation; k files
                        across two groups is O(k) adjacency, not O(k^2) pairs

Run with:
    python3 scripts/test_build_cross_group_edges.py -v
"""

import json
import os
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import build_cross_group_edges as b  # noqa: E402


def pkg_row(path, package):
    return {"file": path, "line": 1, "match": f"package {package};", "rule_id": "references__package"}


def imp_row(path, qualified, static=False):
    kw = "import static " if static else "import "
    return {"file": path, "line": 2, "match": f"{kw}{qualified};", "rule_id": "references__import"}


def make(groups, references, repo_path="/repo"):
    groups_data = {"repo_path": repo_path,
                   "groups": [{"id": i, "files": fs, "est_tokens": 1} for i, fs in enumerate(groups)]}
    return b.build_report(groups_data, {"evidence": {"references": references}})


class CoverSemanticsTest(unittest.TestCase):
    """partition_repo.py overlaps adjacent groups, so a file can be in two."""

    def test_arc_inside_one_group_is_not_cut(self):
        r = make([["a/A.java", "a/B.java"], ["c/C.java"]],
                 [pkg_row("a/A.java", "a"), pkg_row("a/B.java", "a"), imp_row("a/A.java", "a.B")])
        self.assertEqual(r["stats"].get("cut_arcs", 0), 0)

    def test_shared_file_makes_arc_not_cut(self):
        # B is in BOTH groups, so no arc touching it is cut, even though the
        # two groups differ. A file->group scalar map gets this wrong.
        r = make([["a/A.java", "a/B.java"], ["a/B.java", "c/C.java"]],
                 [pkg_row("a/A.java", "a"), pkg_row("a/B.java", "a"), imp_row("c/C.java", "a.B")])
        self.assertEqual(r["stats"].get("cut_arcs", 0), 0,
                         "B is covered by both groups; the arc is internal to group 1")

    def test_is_cut_predicate_uses_set_intersection(self):
        memb = {"u": {0, 1}, "v": {1}, "w": {2}}
        self.assertFalse(b.is_cut(memb, "u", "v"))
        self.assertTrue(b.is_cut(memb, "u", "w"))


class JoinKeyTest(unittest.TestCase):
    """Resolve to a type, not a package."""

    def setUp(self):
        self.refs = [
            pkg_row("a/Foo.java", "a"), pkg_row("a/Bar.java", "a"), pkg_row("a/Baz.java", "a"),
            pkg_row("z/Z.java", "z"),
        ]

    def test_named_import_resolves_to_one_file(self):
        r = make([["z/Z.java"], ["a/Foo.java", "a/Bar.java", "a/Baz.java"]],
                 self.refs + [imp_row("z/Z.java", "a.Foo")])
        self.assertEqual(r["stats"]["cut_arcs"], 1, "must not fan out to all three files in package a")
        self.assertEqual(r["stats"]["confidence_exact"], 1)
        self.assertEqual(r["groups"]["0"]["outbound"][0]["to"], "a/Foo.java")

    def test_wildcard_import_fans_out_and_is_marked(self):
        r = make([["z/Z.java"], ["a/Foo.java", "a/Bar.java", "a/Baz.java"]],
                 self.refs + [imp_row("z/Z.java", "a.*")])
        self.assertEqual(r["stats"]["cut_arcs"], 3)
        self.assertEqual(r["stats"]["confidence_package-fanout"], 3)

    def test_third_party_import_is_unresolved_not_an_arc(self):
        r = make([["z/Z.java"], ["a/Foo.java"]],
                 self.refs + [imp_row("z/Z.java", "org.springframework.stereotype.Service")])
        self.assertEqual(r["stats"].get("cut_arcs", 0), 0)
        self.assertEqual(r["stats"]["unresolved_imports"], 1)


class PrefixShorteningTest(unittest.TestCase):
    """The regression that matters most: a single rsplit drops these
    entirely, silently under-reporting the cut."""

    def setUp(self):
        self.refs = [pkg_row("a/Foo.java", "a"), pkg_row("z/Z.java", "z")]
        self.groups = [["z/Z.java"], ["a/Foo.java"]]

    def test_static_member_import_resolves(self):
        # `import static a.Foo.BAR` -> (a.Foo, BAR) fails -> (a, Foo) resolves.
        r = make(self.groups, self.refs + [imp_row("z/Z.java", "a.Foo.BAR", static=True)])
        self.assertEqual(r["stats"]["cut_arcs"], 1)
        self.assertEqual(r["groups"]["0"]["outbound"][0]["to"], "a/Foo.java")
        self.assertTrue(r["groups"]["0"]["outbound"][0]["static_import"])

    def test_nested_class_import_resolves(self):
        r = make(self.groups, self.refs + [imp_row("z/Z.java", "a.Foo.Inner")])
        self.assertEqual(r["stats"]["cut_arcs"], 1)
        self.assertEqual(r["groups"]["0"]["outbound"][0]["to"], "a/Foo.java")

    def test_resolve_targets_reports_confidence(self):
        decl, stem, _ = b.parse_references(self.refs)
        self.assertEqual(b.resolve_targets("a.Foo", decl, stem), (["a/Foo.java"], "exact"))
        self.assertEqual(b.resolve_targets("a.Foo.BAR", decl, stem), (["a/Foo.java"], "exact"))
        self.assertEqual(b.resolve_targets("a.*", decl, stem), (["a/Foo.java"], "package-fanout"))
        self.assertEqual(b.resolve_targets("nope.Nope", decl, stem), ([], "unresolved"))


class CliqueAvoidanceTest(unittest.TestCase):
    """Same-package is an equivalence relation. k files split across two
    groups has O(k^2) cross pairs but only O(k) members to name."""

    def test_same_package_split_is_adjacency_not_pairs(self):
        # 6 files in one package, 3 per group: 3*3 = 9 cross pairs, but only
        # 3 names to ship per group.
        left = [f"a/L{i}.java" for i in range(3)]
        right = [f"a/R{i}.java" for i in range(3)]
        refs = [pkg_row(p, "a") for p in left + right]
        r = make([left, right], refs)
        self.assertEqual(r["stats"]["same_package_adjacency_rows"], 6, "3 outside names per group")
        block = r["groups"]["0"]["same_package_outside"][0]
        self.assertEqual(block["package"], "a")
        self.assertEqual(sorted(block["files_outside_group"]), sorted(right))
        self.assertEqual(sorted(block["files_in_group"]), sorted(left))

    def test_package_wholly_inside_one_group_emits_nothing(self):
        refs = [pkg_row("a/A.java", "a"), pkg_row("a/B.java", "a"), pkg_row("z/Z.java", "z")]
        r = make([["a/A.java", "a/B.java"], ["z/Z.java"]], refs)
        self.assertEqual(r["groups"]["0"]["same_package_outside"], [])

    def test_single_file_package_emits_nothing(self):
        r = make([["a/A.java"], ["z/Z.java"]], [pkg_row("a/A.java", "a"), pkg_row("z/Z.java", "z")])
        self.assertEqual(r["groups"]["0"]["same_package_outside"], [])


class DirectionAndDedupTest(unittest.TestCase):
    def test_outbound_and_inbound_are_assigned_to_the_right_groups(self):
        r = make([["z/Z.java"], ["a/Foo.java"]],
                 [pkg_row("a/Foo.java", "a"), pkg_row("z/Z.java", "z"), imp_row("z/Z.java", "a.Foo")])
        self.assertEqual(len(r["groups"]["0"]["outbound"]), 1)
        self.assertEqual(len(r["groups"]["0"]["inbound"]), 0)
        self.assertEqual(len(r["groups"]["1"]["inbound"]), 1)
        self.assertEqual(len(r["groups"]["1"]["outbound"]), 0)

    def test_self_reference_is_not_an_arc(self):
        r = make([["a/Foo.java"], ["z/Z.java"]],
                 [pkg_row("a/Foo.java", "a"), pkg_row("z/Z.java", "z"), imp_row("a/Foo.java", "a.Foo")])
        self.assertEqual(r["stats"].get("cut_arcs", 0), 0)

    def test_duplicate_import_rows_counted_once(self):
        refs = [pkg_row("a/Foo.java", "a"), pkg_row("z/Z.java", "z"),
                imp_row("z/Z.java", "a.Foo"), imp_row("z/Z.java", "a.Foo")]
        r = make([["z/Z.java"], ["a/Foo.java"]], refs)
        self.assertEqual(r["stats"]["cut_arcs"], 1)


class ReportShapeTest(unittest.TestCase):
    def test_declares_a_schema_version(self):
        # Every artifact crossing a stage boundary should say what it is;
        # groups.json/summaries.json currently don't. This one does.
        r = make([["a/A.java"]], [pkg_row("a/A.java", "a")])
        self.assertEqual(r["schema_version"], b.SCHEMA_VERSION)

    def test_reduction_stats_present_and_consistent(self):
        r = make([["z/Z.java"], ["a/Foo.java"]],
                 [pkg_row("a/Foo.java", "a"), pkg_row("z/Z.java", "z"), imp_row("z/Z.java", "a.Foo")])
        s = r["stats"]
        self.assertEqual(s["broadcast_rows_avoided"], 3 * 2)
        self.assertEqual(s["rows_shipped"], 2)  # one arc, seen from both sides

    def test_empty_references_does_not_crash(self):
        r = make([["a/A.java"]], [])
        self.assertEqual(r["stats"]["rows_shipped"], 0)
        self.assertIsNone(r["stats"]["reduction_factor"])


class RealArtifactTest(unittest.TestCase):
    """Runs against a completed Stage-0 output if one is present. Skipped
    otherwise, same opt-in pattern as test_partition_repo_real_world.py."""

    def _artifacts(self):
        d = os.environ.get("PIPELINE_ARTIFACTS_DIR")
        if not d:
            self.skipTest("PIPELINE_ARTIFACTS_DIR not set")
        g, s = Path(d) / "groups.json", Path(d) / "spring_signals.json"
        if not (g.is_file() and s.is_file()):
            self.skipTest(f"groups.json/spring_signals.json not both present in {d}")
        return json.load(open(g, encoding="utf-8")), json.load(open(s, encoding="utf-8"))

    def test_real_run_ships_strictly_less_than_broadcast(self):
        groups_data, signals_data = self._artifacts()
        s = b.build_report(groups_data, signals_data)["stats"]
        self.assertLess(s["rows_shipped"], s["broadcast_rows_avoided"],
                        "the whole point is shipping less than the broadcast")

    def test_real_run_resolves_some_arcs_exactly(self):
        # Guards the failure mode where a parse change makes every import
        # unresolved: the run still "succeeds" and ships almost nothing.
        groups_data, signals_data = self._artifacts()
        s = b.build_report(groups_data, signals_data)["stats"]
        self.assertGreater(s.get("cut_arcs", 0), 0, "zero arcs on a real repo means the join broke")


if __name__ == "__main__":
    unittest.main()
