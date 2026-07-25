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

import spring_drift_check  # noqa: E402
import spring_signal_scan  # noqa: E402


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

    # ---- JPQL lineage's second provenance input: the entity's own file ----
    #
    # A JPQL citation's lineage is a DERIVED value with two inputs, not one:
    # the query text (its own file) and the entity->table mapping (a
    # *different* file, entity_table_map[entity]["file"]). Freshness for a
    # derived citation means "every file in its provenance is unchanged" —
    # the same rule every other (single-input) citation already follows,
    # just honestly widened for the one citation type that actually has two
    # inputs, rather than a special "dependent entity" status bolted on.

    def test_entity_table_rename_drifts_dependent_jpql_citation_even_though_query_file_is_untouched(self):
        # InvoiceRepository.java's JPQL query resolves its lineage through
        # Invoice.java's entity mapping. If Invoice.java's @Table renames,
        # InvoiceRepository.java itself never changes — tier 1 alone would
        # call its JPQL citation unchanged even though the lineage it
        # carries is now stale.
        _edit(
            os.path.join(self.repo, "Invoice.java"),
            '@Table(name = "billing_invoice")',
            '@Table(name = "invoices")',
        )
        report = self._drift()

        entity_citation = _by_source(report, "entity_table_map.Invoice")
        self.assertEqual(entity_citation["status"], spring_drift_check.STATUS_DRIFTED)

        jpql_result = self._raw_query_result(report, "InvoiceRepository.java", "jpql")
        self.assertEqual(jpql_result["status"], spring_drift_check.STATUS_DRIFTED)
        self.assertEqual(jpql_result["tier"], 2)
        self.assertIn("Invoice", jpql_result["detail"])
        self.assertIn("billing_invoice", jpql_result["detail"])
        self.assertIn("invoices", jpql_result["detail"])

        # The native query's lineage was extracted directly from real SQL
        # text, no entity_table_map dependency at all — it must NOT be
        # swept up just because a sibling citation in the same file was.
        native_result = self._raw_query_result(report, "InvoiceRepository.java", "native")
        self.assertEqual(native_result["status"], spring_drift_check.STATUS_UNCHANGED)

    def test_entity_file_changed_but_table_mapping_unchanged_confirms_jpql_lineage(self):
        # The core false-positive this whole tool exists to avoid, applied
        # to the new provenance check: Invoice.java's hash changes (an
        # unrelated comment), but @Table itself doesn't move, so the JPQL
        # lineage resolved through it is still accurate. Must read as
        # CONFIRMED (tier 2 — actually re-verified), not left at the tier-1
        # STATUS_UNCHANGED default (which would mean "never actually
        # checked"), and definitely not DRIFTED.
        _edit(
            os.path.join(self.repo, "Invoice.java"),
            "private Long id;",
            "private Long id; // unrelated comment, nothing structural changed",
        )
        report = self._drift()

        jpql_result = self._raw_query_result(report, "InvoiceRepository.java", "jpql")
        self.assertEqual(jpql_result["status"], spring_drift_check.STATUS_CONFIRMED)
        self.assertEqual(jpql_result["tier"], 2)

    def test_dependent_status_does_not_override_a_citation_with_its_own_real_tier2_result(self):
        # If the query's own file ALSO changed, tier 2 already produced a
        # real, more specific verdict for it (a genuine text mismatch) — the
        # provenance re-check must not clobber that with a different DRIFTED
        # detail about the entity instead.
        _edit(
            os.path.join(self.repo, "Invoice.java"),
            '@Table(name = "billing_invoice")',
            '@Table(name = "invoices")',
        )
        _edit(
            os.path.join(self.repo, "InvoiceRepository.java"),
            "SELECT i FROM Invoice i WHERE i.status = :status",
            "SELECT i FROM Invoice i WHERE i.status = :status AND i.archived = false",
        )
        report = self._drift()

        jpql_result = self._raw_query_result(report, "InvoiceRepository.java", "jpql")
        self.assertEqual(jpql_result["status"], spring_drift_check.STATUS_DRIFTED)
        self.assertIn("no fresh @Query match", jpql_result["detail"])

    def test_entity_table_rename_drifts_jpql_even_when_query_file_also_changed_but_text_intact(self):
        # audit Claim 1, end-to-end: both Invoice.java (table rename) AND
        # InvoiceRepository.java change in the same interval, but the JPQL
        # query STRING is untouched — so its own-file tier-2 recheck yields
        # CONFIRMED (text still present). The provenance pass must still
        # upgrade it to DRIFTED because the entity's table moved; the
        # pre-fix guard (skip anything not STATUS_UNCHANGED) reported this as
        # confirmed_still_present over now-stale lineage.
        _edit(
            os.path.join(self.repo, "Invoice.java"),
            '@Table(name = "billing_invoice")',
            '@Table(name = "invoices")',
        )
        _edit(
            os.path.join(self.repo, "InvoiceRepository.java"),
            "Invoice findByStatus(String status);",
            "Invoice findByStatus(String status); // unrelated non-query edit",
        )
        report = self._drift()

        # Guard: the query file really did change (so its own-file verdict is
        # tier-2 CONFIRMED, not tier-1 UNCHANGED) — otherwise this test would
        # silently reduce to the already-covered query-file-untouched case.
        self.assertIn("InvoiceRepository.java", report["file_summary"]["changed"])

        jpql_result = self._raw_query_result(report, "InvoiceRepository.java", "jpql")
        self.assertEqual(jpql_result["status"], spring_drift_check.STATUS_DRIFTED)
        self.assertEqual(jpql_result["tier"], 2)
        self.assertIn("billing_invoice", jpql_result["detail"])
        self.assertIn("invoices", jpql_result["detail"])

    def test_deleting_entity_file_drifts_dependent_jpql_citation(self):
        # audit finding #2, end-to-end: Invoice.java is deleted while
        # InvoiceRepository.java is untouched. The JPQL citation's second
        # provenance input is gone, so it must read DRIFTED (with a
        # delete-specific detail), not the tier-1 STATUS_UNCHANGED its own
        # untouched file would otherwise leave it at.
        os.remove(os.path.join(self.repo, "Invoice.java"))
        report = self._drift()
        self.assertIn("Invoice.java", report["file_summary"]["deleted"])

        jpql_result = self._raw_query_result(report, "InvoiceRepository.java", "jpql")
        self.assertEqual(jpql_result["status"], spring_drift_check.STATUS_DRIFTED)
        self.assertEqual(jpql_result["tier"], 2)
        self.assertIn("deleted", jpql_result["detail"])

        # The native query in the same file has no entity_table_map dependency,
        # so deleting Invoice.java must not sweep it up.
        native_result = self._raw_query_result(report, "InvoiceRepository.java", "native")
        self.assertEqual(native_result["status"], spring_drift_check.STATUS_UNCHANGED)

    def _raw_query_result(self, report, file_rel, query_kind):
        """Look up a raw_queries__query drift result by (file, query_kind),
        via the baseline's own line number — drift_result() doesn't carry
        query_kind/query text, only file/line/match, and InvoiceRepository.java
        has both a jpql and a native citation whose `match` text is
        indistinguishable (both start "@Query(")."""
        baseline_entry = next(
            e for e in self.baseline["evidence"]["raw_queries"]
            if e["file"] == file_rel and e["query_kind"] == query_kind
        )
        return next(
            r for r in report["results"]
            if r["file"] == file_rel and r["line"] == baseline_entry["line"]
        )

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
             "repo_path": self.repo, "commit_hash": "deadbeef", "dirty": False},
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

    def test_load_manifest_rejects_still_running_manifest(self):
        # build_init_manifest()'s status stays "running" until finalize is
        # ever called at all -- a manifest at that point always has an empty
        # file_signatures placeholder and must not be usable as a baseline.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "run_manifest.json")
            with open(path, "w") as f:
                json.dump({
                    "run_id": "x", "status": "running",
                    "target_repo": {"commit_hash": "abc", "dirty": False},
                    "file_signatures": {},
                }, f)
            with self.assertRaises(SystemExit):
                spring_drift_check.load_manifest(path)

    def test_load_manifest_rejects_finalized_manifest_with_empty_file_signatures(self):
        # finalize_manifest() only overwrites file_signatures if it was
        # actually given some (e.g. no --signals-file and no repo to
        # re-hash) -- a "complete" manifest can still have an empty map.
        # No target_repo.path here, so there's nothing to re-check against --
        # must be treated as the broken-finalize case, not the empty-repo one.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "run_manifest.json")
            with open(path, "w") as f:
                json.dump({
                    "run_id": "x", "status": "complete",
                    "target_repo": {"commit_hash": "abc", "dirty": False},
                    "file_signatures": {},
                }, f)
            with self.assertRaises(SystemExit):
                spring_drift_check.load_manifest(path)

    def test_load_manifest_accepts_empty_file_signatures_for_a_genuinely_empty_repo(self):
        # An empty file_signatures map isn't always the broken-finalize case --
        # a repo with zero trackable files at scan time finalizes with an
        # empty map too, and "everything is newly added" is the correct
        # report for that, not a misreport. target_repo.path is re-walked
        # live to tell the two cases apart.
        with tempfile.TemporaryDirectory() as empty_repo:
            with tempfile.TemporaryDirectory() as d:
                path = os.path.join(d, "run_manifest.json")
                with open(path, "w") as f:
                    json.dump({
                        "run_id": "x", "status": "complete",
                        "target_repo": {"path": empty_repo, "commit_hash": "abc", "dirty": False},
                        "file_signatures": {},
                    }, f)
                data = spring_drift_check.load_manifest(path)
                self.assertEqual(data["file_signatures"], {})

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


class JpqlLineageProvenanceTest(unittest.TestCase):
    """Unit-level tests against _raw_query_entries_with_resolved_entity()
    and _reverify_jpql_lineage_provenance() directly, with synthetic
    signals/results dicts — no ast-grep, no tempdir. Each function has one
    job (find the citations with a second provenance input; re-verify that
    input for citations whose provenance file changed) and is tested in
    isolation from the real-repo integration scenarios in
    SpringDriftCheckTest above, which cover the same behavior end-to-end."""

    def _signals(self, resolved_via_entity="Invoice", available=True):
        lineage = {"available": available, "source_tables": ["billing_invoice"], "target_tables": []}
        if available and resolved_via_entity is not None:
            lineage["resolved_via_entity"] = resolved_via_entity
        return {
            "entity_table_map": {
                "Invoice": {"file": "Invoice.java", "table": "billing_invoice", "table_name_source": "explicit"},
            },
            "evidence": {
                "raw_queries": [
                    {
                        "file": "InvoiceRepository.java", "line": 9, "query_kind": "jpql",
                        "query": "SELECT i FROM Invoice i WHERE i.status = :status",
                        "lineage": lineage,
                    },
                    {
                        "file": "InvoiceRepository.java", "line": 17, "query_kind": "native",
                        "query": "SELECT * FROM billing_invoice WHERE status = :status",
                        "lineage": {"available": True, "source_tables": ["billing_invoice"], "target_tables": []},
                    },
                ],
            },
        }

    # ---- _raw_query_entries_with_resolved_entity ----

    def test_finds_the_jpql_entry_with_resolved_via_entity(self):
        found = list(spring_drift_check._raw_query_entries_with_resolved_entity(self._signals()))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["query_kind"], "jpql")

    def test_skips_native_entries_with_no_resolved_via_entity(self):
        signals = self._signals()
        del signals["evidence"]["raw_queries"][0]  # keep only the native entry
        found = list(spring_drift_check._raw_query_entries_with_resolved_entity(signals))
        self.assertEqual(found, [])

    def test_skips_unavailable_jpql_lineage(self):
        # An out-of-scope JPQL query (join, traversal, ...) has
        # lineage = {"available": False, "reason": ...} — no
        # resolved_via_entity key at all, nothing to re-verify.
        signals = self._signals(available=False)
        found = list(spring_drift_check._raw_query_entries_with_resolved_entity(signals))
        self.assertEqual(found, [])

    def test_empty_signals_yields_nothing(self):
        found = list(spring_drift_check._raw_query_entries_with_resolved_entity({}))
        self.assertEqual(found, [])

    # ---- _reverify_jpql_lineage_provenance ----

    def _base_result(self, status=spring_drift_check.STATUS_UNCHANGED, tier=1):
        return {
            "source": "evidence.raw_queries", "file": "InvoiceRepository.java", "line": 9,
            "rule_id": "raw_queries__query", "match": "@Query(", "status": status, "tier": tier,
        }

    def test_entity_missing_from_entity_table_map_skips_defensively(self):
        # Shouldn't happen in practice — resolve_jpql_to_lineage() only
        # sets resolved_via_entity when the entity WAS found in
        # entity_table_map at scan time — but signals is arbitrary input
        # (a hand-edited JSON, a future format this code doesn't know
        # about), so this must degrade rather than KeyError.
        signals = self._signals()
        del signals["entity_table_map"]["Invoice"]
        results = [self._base_result()]
        spring_drift_check._reverify_jpql_lineage_provenance(
            results, signals, fresh_entity_tables={}, changed_set={"Invoice.java"}, deleted_set=set(),
        )
        self.assertEqual(results[0]["status"], spring_drift_check.STATUS_UNCHANGED)

    def test_entity_file_not_changed_leaves_result_untouched(self):
        results = [self._base_result()]
        spring_drift_check._reverify_jpql_lineage_provenance(
            results, self._signals(), fresh_entity_tables={},
            changed_set=set(), deleted_set=set(),  # Invoice.java in neither set
        )
        self.assertEqual(results[0]["status"], spring_drift_check.STATUS_UNCHANGED)
        self.assertEqual(results[0]["tier"], 1)

    def test_entity_file_changed_table_unchanged_confirms(self):
        results = [self._base_result()]
        spring_drift_check._reverify_jpql_lineage_provenance(
            results, self._signals(), fresh_entity_tables={"Invoice": {"table": "billing_invoice"}},
            changed_set={"Invoice.java"}, deleted_set=set(),
        )
        self.assertEqual(results[0]["status"], spring_drift_check.STATUS_CONFIRMED)
        self.assertEqual(results[0]["tier"], 2)

    def test_entity_file_changed_table_renamed_drifts_with_old_and_new_names(self):
        results = [self._base_result()]
        spring_drift_check._reverify_jpql_lineage_provenance(
            results, self._signals(), fresh_entity_tables={"Invoice": {"table": "invoices"}},
            changed_set={"Invoice.java"}, deleted_set=set(),
        )
        self.assertEqual(results[0]["status"], spring_drift_check.STATUS_DRIFTED)
        self.assertEqual(results[0]["tier"], 2)
        self.assertIn("billing_invoice", results[0]["detail"])
        self.assertIn("invoices", results[0]["detail"])

    def test_entity_no_longer_matched_drifts_conservatively(self):
        # persistence__entity re-run against the changed file found no
        # match for this class at all (fresh_entity_tables has no entry for
        # it) — can't confirm the lineage is still accurate, so this must
        # NOT be silently left at STATUS_UNCHANGED.
        results = [self._base_result()]
        spring_drift_check._reverify_jpql_lineage_provenance(
            results, self._signals(), fresh_entity_tables={}, changed_set={"Invoice.java"}, deleted_set=set(),
        )
        self.assertEqual(results[0]["status"], spring_drift_check.STATUS_DRIFTED)
        self.assertIn("no longer matches", results[0]["detail"])

    def test_does_not_override_a_result_with_its_own_more_specific_verdict(self):
        # The query's own file also changed and already produced a real
        # tier-2 verdict (DRIFTED, from a text mismatch) — the provenance
        # pass must leave it exactly alone, not overwrite with a different
        # DRIFTED detail about the entity.
        results = [self._base_result(status=spring_drift_check.STATUS_DRIFTED, tier=2)]
        results[0]["detail"] = "no fresh @Query match with the same query text and kind found in this file"
        spring_drift_check._reverify_jpql_lineage_provenance(
            results, self._signals(), fresh_entity_tables={"Invoice": {"table": "invoices"}},
            changed_set={"Invoice.java"}, deleted_set=set(),
        )
        self.assertEqual(results[0]["status"], spring_drift_check.STATUS_DRIFTED)
        self.assertIn("no fresh @Query match", results[0]["detail"])

    def test_confirmed_own_file_verdict_still_gets_entity_provenance_rechecked(self):
        # THE regression case (audit Claim 1): the query's OWN file changed
        # in a way that left its text intact, so _recheck_queries() already
        # marked it STATUS_CONFIRMED — but "text still present" says nothing
        # about whether the lineage is still accurate. If the entity's table
        # renamed in the same interval, this CONFIRMED verdict must be
        # UPGRADED to DRIFTED, not skipped. The pre-fix guard (skip unless
        # STATUS_UNCHANGED) let this exact case through as confirmed-but-stale.
        results = [self._base_result(status=spring_drift_check.STATUS_CONFIRMED, tier=2)]
        spring_drift_check._reverify_jpql_lineage_provenance(
            results, self._signals(), fresh_entity_tables={"Invoice": {"table": "invoices"}},
            changed_set={"Invoice.java"}, deleted_set=set(),
        )
        self.assertEqual(results[0]["status"], spring_drift_check.STATUS_DRIFTED)
        self.assertEqual(results[0]["tier"], 2)
        self.assertIn("billing_invoice", results[0]["detail"])
        self.assertIn("invoices", results[0]["detail"])

    def test_confirmed_own_file_verdict_with_unchanged_table_stays_confirmed(self):
        # The companion no-false-positive check for the case above: a
        # CONFIRMED query whose entity file changed but whose table mapping
        # did NOT must stay CONFIRMED — the upgrade fires on an actual table
        # change, not merely on the entity file being touched.
        results = [self._base_result(status=spring_drift_check.STATUS_CONFIRMED, tier=2)]
        spring_drift_check._reverify_jpql_lineage_provenance(
            results, self._signals(), fresh_entity_tables={"Invoice": {"table": "billing_invoice"}},
            changed_set={"Invoice.java"}, deleted_set=set(),
        )
        self.assertEqual(results[0]["status"], spring_drift_check.STATUS_CONFIRMED)

    def test_deleted_entity_file_drifts_dependent_jpql_with_delete_specific_detail(self):
        # audit finding #2: the entity's file was DELETED (not just changed),
        # so it never got tier-2 rechecked and never appears in
        # fresh_entity_tables. The gate must still fire (via deleted_set), and
        # the fresh-is-None branch must report DRIFTED with a delete-specific
        # detail, not the "no longer matches in its file" wording that reads
        # wrong for a file that no longer exists.
        results = [self._base_result()]
        spring_drift_check._reverify_jpql_lineage_provenance(
            results, self._signals(), fresh_entity_tables={},
            changed_set=set(), deleted_set={"Invoice.java"},
        )
        self.assertEqual(results[0]["status"], spring_drift_check.STATUS_DRIFTED)
        self.assertEqual(results[0]["tier"], 2)
        self.assertIn("deleted", results[0]["detail"])
        self.assertIn("Invoice.java", results[0]["detail"])

    def test_no_matching_result_entry_does_not_crash(self):
        # Defensive: a citation with resolved_via_entity but no
        # corresponding (file, line) in results shouldn't happen in
        # practice (every citation gets exactly one result), but this pass
        # runs after the main loop on a separate data structure, so it must
        # degrade safely rather than KeyError if the two ever disagree.
        results = []
        spring_drift_check._reverify_jpql_lineage_provenance(
            results, self._signals(), fresh_entity_tables={"Invoice": {"table": "invoices"}},
            changed_set={"Invoice.java"}, deleted_set=set(),
        )
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
