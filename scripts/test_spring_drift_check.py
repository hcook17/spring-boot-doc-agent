#!/usr/bin/env python3
"""
Integration test for spring_drift_check.py, run against a scratch copy of
the same fixture repo test_spring_signal_scan.py uses
(test_fixtures/spring_signals/).

Like test_spring_signal_scan.py, this is a REAL integration test, not a
mocked one: every test calls spring_signal_scan.scan() for a baseline (real
ast-grep subprocess, real bundled rule file) and spring_drift_check.check_drift()
against a mutated copy of the same files (another real ast-grep subprocess,
for whichever files tier 1 flags as changed). Each test gets its own fresh
tempfile copy of the fixture tree so mutating files for one drift scenario
can't bleed into another test or into test_spring_signal_scan.py's own
fixture-count assumptions.

Run with:

    python3 scripts/test_spring_drift_check.py -v

Requires: ast-grep on PATH (same requirement as test_spring_signal_scan.py).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DIR = os.path.join(SCRIPT_DIR, "test_fixtures", "spring_signals")
DRIFT_CHECK_PATH = os.path.join(SCRIPT_DIR, "spring_drift_check.py")
sys.path.insert(0, SCRIPT_DIR)

import spring_signal_scan  # noqa: E402
import spring_drift_check  # noqa: E402


def _make_scratch_copy():
    scratch = tempfile.mkdtemp(prefix="drift_check_test_")
    dest = os.path.join(scratch, "repo")
    shutil.copytree(FIXTURE_DIR, dest)
    return dest


def _edit(path, old, new):
    with open(path) as f:
        text = f.read()
    assert old in text, f"expected to find {old!r} in {path}"
    text = text.replace(old, new)
    with open(path, "w") as f:
        f.write(text)


def _by_source(report, source_suffix):
    """First result entry whose `source` ends with the given suffix — lets
    tests address e.g. "entity_table_map.LegacyAudit" or a specific bucket
    entry without depending on list order."""
    for r in report["results"]:
        if r["source"].endswith(source_suffix):
            return r
    return None


class SpringDriftCheckTest(unittest.TestCase):
    def setUp(self):
        self.repo = _make_scratch_copy()
        self.baseline = spring_signal_scan.scan(self.repo)
        # Sanity: every test depends on the baseline carrying the
        # drift-detection fields introduced in schema_version 2
        # (file_signatures, rule_id) — not on the exact version number,
        # which moves independently of this file for unrelated reasons
        # (e.g. the SQL lineage field added in schema_version 3). Asserting
        # ">=" rather than "==" here means the next unrelated version bump
        # won't break this whole suite the way this one did. If this ever
        # fails, it means spring_signal_scan.py regressed, not
        # spring_drift_check.py.
        self.assertGreaterEqual(self.baseline["schema_version"], 2)
        self.assertIn("file_signatures", self.baseline)

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.repo), ignore_errors=True)

    def _drift(self):
        return spring_drift_check.check_drift(self.repo, self.baseline)

    # ---- tier 1 only: nothing changed ----

    def test_no_changes_everything_unchanged(self):
        report = self._drift()
        self.assertEqual(report["file_summary"]["changed"], [])
        self.assertEqual(report["file_summary"]["deleted"], [])
        self.assertEqual(report["file_summary"]["added"], [])
        statuses = {r["status"] for r in report["results"]}
        self.assertEqual(statuses, {spring_drift_check.STATUS_UNCHANGED})

    # ---- the core false-positive this whole tool exists to avoid ----

    def test_unrelated_comment_edit_does_not_drift_the_entity_citation(self):
        # This is the exact scenario from the design brief: a comment fix
        # nowhere near the cited annotation must not read as drift.
        _edit(
            os.path.join(self.repo, "SLARule.java"),
            "private Long id;",
            "private Long id; // unrelated comment, nothing structural changed",
        )
        report = self._drift()
        self.assertIn("SLARule.java", report["file_summary"]["changed"])

        entity_citation = _by_source(report, "entity_table_map.SLARule")
        bucket_citation = next(
            r for r in report["results"]
            if r["file"] == "SLARule.java" and r["source"] == "evidence.persistence"
        )
        self.assertEqual(entity_citation["status"], spring_drift_check.STATUS_CONFIRMED)
        self.assertEqual(entity_citation["tier"], 2)
        self.assertEqual(bucket_citation["status"], spring_drift_check.STATUS_CONFIRMED)

    # ---- real drift: table mapping actually changes ----

    def test_table_mapping_change_is_drift_but_existence_entry_is_not(self):
        _edit(
            os.path.join(self.repo, "LegacyAudit.java"),
            "@Entity\npublic class LegacyAudit {",
            '@Entity\n@Table(name = "legacy_audit_v2")\npublic class LegacyAudit {',
        )
        report = self._drift()

        entity_citation = _by_source(report, "entity_table_map.LegacyAudit")
        self.assertEqual(entity_citation["status"], spring_drift_check.STATUS_DRIFTED)
        self.assertIn("legacy_audit", entity_citation["detail"])
        self.assertIn("legacy_audit_v2", entity_citation["detail"])

        # The parallel persistence-bucket entry only claims "this class is
        # still @Entity-annotated" — which remains true — so it must NOT
        # drift just because the table mapping did.
        bucket_citation = next(
            r for r in report["results"]
            if r["file"] == "LegacyAudit.java" and r["source"] == "evidence.persistence"
        )
        self.assertEqual(bucket_citation["status"], spring_drift_check.STATUS_CONFIRMED)

    def test_entity_class_removed_entirely_is_drift(self):
        _edit(
            os.path.join(self.repo, "LegacyAudit.java"),
            "@Entity\npublic class LegacyAudit {",
            "public class LegacyAudit {",  # @Entity annotation removed
        )
        report = self._drift()
        entity_citation = _by_source(report, "entity_table_map.LegacyAudit")
        self.assertEqual(entity_citation["status"], spring_drift_check.STATUS_DRIFTED)
        bucket_citation = next(
            r for r in report["results"]
            if r["file"] == "LegacyAudit.java" and r["source"] == "evidence.persistence"
        )
        self.assertEqual(bucket_citation["status"], spring_drift_check.STATUS_DRIFTED)

    # ---- repository generic type args ----

    def test_repository_type_args_change_is_drift(self):
        _edit(
            os.path.join(self.repo, "InvoiceRepository.java"),
            "JpaRepository<Invoice, Long>",
            "JpaRepository<Invoice, String>",
        )
        report = self._drift()
        citation = next(
            r for r in report["results"]
            if r["file"] == "InvoiceRepository.java" and r["rule_id"] == "persistence__repository"
        )
        self.assertEqual(citation["status"], spring_drift_check.STATUS_DRIFTED)

    # ---- one annotation changes; siblings in the same file must not drift ----

    def test_single_mapping_change_does_not_flag_sibling_citations(self):
        _edit(
            os.path.join(self.repo, "InvoiceController.java"),
            "@PostMapping\n    public String createInvoice()",
            '@PostMapping("/new")\n    public String createInvoice()',
        )
        report = self._drift()

        # The @PostMapping citation (originally bare) is the one that changed shape.
        drifted = [r for r in report["results"]
                   if r["file"] == "InvoiceController.java" and r["status"] == spring_drift_check.STATUS_DRIFTED]
        self.assertEqual(len(drifted), 1)
        self.assertEqual(drifted[0]["match"], "@PostMapping")

        # Everything else in the same file must still confirm: @RestController,
        # @RequestMapping, @GetMapping, @PreAuthorize (api_surface/security),
        # plus the package declaration and two imports (references) — 7 total.
        confirmed = [r for r in report["results"]
                     if r["file"] == "InvoiceController.java" and r["status"] == spring_drift_check.STATUS_CONFIRMED]
        self.assertEqual(len(confirmed), 7)

    # ---- raw query text change ----

    def test_query_text_change_is_drift(self):
        # InvoiceRepository.java carries two @Query citations (one jpql, one
        # native) — edit only the jpql one's string and confirm just that
        # citation drifts while its sibling (unedited) still confirms. The
        # `match` field always reflects the *original* stored text (drift_result
        # never overwrites it with the fresh match), so both citations are
        # still distinguishable after the edit by their original wording.
        _edit(
            os.path.join(self.repo, "InvoiceRepository.java"),
            "SELECT i FROM Invoice i WHERE i.status = :status",
            "SELECT i FROM Invoice i WHERE i.status = :status AND i.archived = false",
        )
        report = self._drift()
        query_citations = [
            r for r in report["results"]
            if r["file"] == "InvoiceRepository.java" and r["rule_id"] == "raw_queries__query"
        ]
        self.assertEqual(len(query_citations), 2)

        jpql_citation = next(r for r in query_citations if "i.status" in (r.get("match") or ""))
        native_citation = next(r for r in query_citations if "i.status" not in (r.get("match") or ""))
        self.assertEqual(jpql_citation["status"], spring_drift_check.STATUS_DRIFTED)
        self.assertEqual(native_citation["status"], spring_drift_check.STATUS_CONFIRMED)

    # ---- deletions and additions ----

    def test_deleted_file_flags_every_citation_as_file_deleted(self):
        os.remove(os.path.join(self.repo, "Misc.java"))
        report = self._drift()
        self.assertIn("Misc.java", report["file_summary"]["deleted"])
        misc_results = [r for r in report["results"] if r["file"] == "Misc.java"]
        self.assertTrue(misc_results, "Misc.java had evidence in the baseline; expected citations in the report")
        self.assertTrue(all(r["status"] == spring_drift_check.STATUS_FILE_DELETED for r in misc_results))

    def test_new_file_is_informational_only(self):
        with open(os.path.join(self.repo, "NewThing.java"), "w") as f:
            f.write("package com.example.billing;\n\npublic class NewThing {\n}\n")
        report = self._drift()
        self.assertIn("NewThing.java", report["file_summary"]["added"])
        self.assertFalse(any(r["file"] == "NewThing.java" for r in report["results"]))

    # ---- filename-based (no rule_id) evidence ----

    def test_filename_based_evidence_falls_back_to_tier1_only(self):
        with open(os.path.join(self.repo, "db", "migration", "V1__init.sql"), "a") as f:
            f.write("\n-- an appended, unrelated comment\n")
        report = self._drift()
        citation = next(r for r in report["results"] if r["file"] == "db/migration/V1__init.sql")
        self.assertIsNone(citation["rule_id"])
        self.assertEqual(citation["status"], spring_drift_check.STATUS_NO_RULE_FALLBACK)
        self.assertEqual(citation["tier"], 1)

    # ---- config key set drift (schema_version 5) ----

    def test_config_value_changed_under_unchanged_key_is_flagged_for_review(self):
        _edit(os.path.join(self.repo, "application-local.yml"), "port: 8080", "port: 9090")
        report = self._drift()
        citation = next(r for r in report["results"] if r["file"] == "application-local.yml")
        self.assertEqual(citation["status"], spring_drift_check.STATUS_CONFIG_VALUES_ONLY_CHANGED)
        self.assertEqual(citation["tier"], 1)

    def test_config_key_added_is_structural_not_flagged_for_review(self):
        with open(os.path.join(self.repo, "application-local.yml"), "a") as f:
            f.write("  extra-new-key: added\n")
        report = self._drift()
        citation = next(r for r in report["results"] if r["file"] == "application-local.yml")
        self.assertEqual(citation["status"], spring_drift_check.STATUS_CONFIG_STRUCTURE_CHANGED)
        self.assertIn("extra-new-key", citation["detail"])

    # ---- schema guard ----

    def test_stale_schema_version_is_rejected_not_crashed(self):
        stale = dict(self.baseline)
        del stale["schema_version"]
        del stale["file_signatures"]
        stale_path = os.path.join(os.path.dirname(self.repo), "stale_signals.json")
        with open(stale_path, "w") as f:
            json.dump(stale, f)
        with self.assertRaises(SystemExit):
            spring_drift_check.load_signals(stale_path)

    def test_citation_with_no_prior_signature_is_unknown_not_guessed(self):
        baseline_missing_sig = json.loads(json.dumps(self.baseline))  # deep copy
        baseline_missing_sig["file_signatures"].pop("Dockerfile", None)
        report = spring_drift_check.check_drift(self.repo, baseline_missing_sig)
        citation = next(r for r in report["results"] if r["file"] == "Dockerfile")
        self.assertEqual(citation["status"], spring_drift_check.STATUS_UNKNOWN_NO_SIGNATURE)

    # ---- --manifest: run_manifest.json as the tier-1 baseline ----

    def test_no_manifest_baseline_source_is_spring_signals(self):
        report = self._drift()
        self.assertEqual(report["file_signatures_baseline"], {"source": "spring_signals.json"})

    def test_manifest_baseline_used_for_tier1_instead_of_signals(self):
        # A manifest whose file_signatures already reflects the edit below
        # (i.e. it was "taken after" the edit) must see the file as
        # unchanged even though spring_signals.json's own baseline predates
        # the edit and would otherwise flag it.
        _edit(
            os.path.join(self.repo, "LegacyAudit.java"),
            "@Entity\npublic class LegacyAudit {",
            '@Entity\n@Table(name = "legacy_audit_v2")\npublic class LegacyAudit {',
        )
        post_edit_scan = spring_signal_scan.scan(self.repo)
        manifest = {
            "run_id": "2026-07-25T00:00:00Z-deadbeef",
            "target_repo": {"path": self.repo, "commit_hash": "deadbeef", "dirty": False},
            "file_signatures": post_edit_scan["file_signatures"],
        }

        report = spring_drift_check.check_drift(self.repo, self.baseline, manifest=manifest)

        self.assertNotIn("LegacyAudit.java", report["file_summary"]["changed"])
        self.assertEqual(
            report["file_signatures_baseline"],
            {"source": "run_manifest.json", "run_id": "2026-07-25T00:00:00Z-deadbeef",
             "commit_hash": "deadbeef", "dirty": False},
        )

    def test_manifest_still_requires_signals_for_tier2_evidence(self):
        # Even with a manifest supplying the tier-1 baseline, tier-2 citation
        # content (entity/table mapping etc.) must still come from signals —
        # a manifest alone has no evidence/entity_table_map to check against.
        manifest = {
            "run_id": "x", "target_repo": {"commit_hash": None, "dirty": None},
            "file_signatures": self.baseline["file_signatures"],
        }
        report = spring_drift_check.check_drift(self.repo, self.baseline, manifest=manifest)
        entity_citation = _by_source(report, "entity_table_map.LegacyAudit")
        self.assertIsNotNone(entity_citation, "tier-2 citations must still come from signals, manifest or no manifest")

    def test_load_manifest_rejects_file_with_no_file_signatures(self):
        with tempfile.TemporaryDirectory() as d:
            bad_path = os.path.join(d, "bad_manifest.json")
            with open(bad_path, "w") as f:
                json.dump({"run_id": "x"}, f)
            with self.assertRaises(SystemExit):
                spring_drift_check.load_manifest(bad_path)

    def test_cli_accepts_manifest_flag_and_reports_its_source(self):
        with tempfile.TemporaryDirectory() as d:
            signals_path = os.path.join(d, "spring_signals.json")
            with open(signals_path, "w") as f:
                json.dump(self.baseline, f)
            manifest_path = os.path.join(d, "run_manifest.json")
            with open(manifest_path, "w") as f:
                json.dump({
                    "run_id": "cli-test", "target_repo": {"commit_hash": "cafef00d", "dirty": True},
                    "file_signatures": self.baseline["file_signatures"],
                }, f)
            out_path = os.path.join(d, "drift_report.json")

            result = subprocess.run(
                [sys.executable, DRIFT_CHECK_PATH, self.repo, signals_path,
                 "--manifest", manifest_path, "--out", out_path],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("run_manifest.json", result.stdout)

            with open(out_path) as f:
                report = json.load(f)
            self.assertEqual(report["file_signatures_baseline"]["source"], "run_manifest.json")
            self.assertEqual(report["file_signatures_baseline"]["run_id"], "cli-test")


if __name__ == "__main__":
    unittest.main()