#!/usr/bin/env python3
"""
Integration test for spring_signal_scan.py, run against the fixture repo in
test_fixtures/spring_signals/.

This is a REAL integration test, not a mocked one: it calls scan() directly,
which shells out to the actual ast-grep binary using the actual bundled
spring_ast_grep_rules.yml. That's deliberate — the thing most worth testing
here is whether the rule file and the Python wrapper still agree with each
other and with a real ast-grep install, not whether some mock was configured
correctly. If ast-grep isn't on PATH, this fails loudly, which is correct:
that's a real deployment problem, not a reason to skip the test.

Every fixture file exists to guard a specific, previously-broken behavior —
see the comment at the top of each one. Run with:

    python3 scripts/test_spring_signal_scan.py -v

Requires: ast-grep on PATH (see spring_signal_scan.py's error message for
install instructions if this fails with "ast-grep binary is not on PATH").
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
sys.path.insert(0, SCRIPT_DIR)

import spring_signal_scan  # noqa: E402


class SpringSignalScanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = spring_signal_scan.scan(FIXTURE_DIR)
        cls.evidence = cls.result["evidence"]

    def _entries_for(self, bucket, filename):
        return [e for e in self.evidence[bucket] if e["file"] == filename]

    # ---- filename-based detection (unchanged from the regex-era scanner) ----

    def test_file_counts(self):
        fs = self.result["files_scanned"]
        self.assertEqual(fs["java"], 9, "target/generated-sources/ShouldBeExcluded.java must not be counted")  # 8 original + SLARule.java
        self.assertEqual(fs["config"], 2)
        self.assertEqual(fs["deployment"], 1)
        self.assertEqual(fs["other_relevant"], 2)  # logback-spring.xml + db/migration/V1__init.sql

    def test_excluded_dirs_are_not_scanned(self):
        all_files = {e["file"] for entries in self.evidence.values() for e in entries}
        all_files |= set(self.result["entity_table_map"][k]["file"] for k in self.result["entity_table_map"])
        self.assertFalse(any("target" in f for f in all_files), "files under target/ leaked into evidence")

    def test_config_and_deployment_and_logging_and_migration(self):
        self.assertEqual(len(self._entries_for("configuration", "application-local.yml")), 1)
        self.assertEqual(len(self._entries_for("configuration", "bootstrap.yml")), 1)
        self.assertEqual(len(self._entries_for("deployment", "Dockerfile")), 1)
        self.assertEqual(len(self._entries_for("observability", "logback-spring.xml")), 1)
        self.assertEqual(len(self._entries_for("persistence", "db/migration/V1__init.sql")), 1)

    # ---- entity / table detection ----

    def test_entity_with_explicit_table(self):
        m = self.result["entity_table_map"]["Invoice"]
        self.assertEqual(m["table"], "billing_invoice")
        self.assertEqual(m["table_name_source"], "explicit")

    def test_entity_with_inferred_table(self):
        m = self.result["entity_table_map"]["LegacyAudit"]
        self.assertEqual(m["table"], "legacy_audit")
        self.assertEqual(m["table_name_source"], "inferred-default-naming")

    def test_acronym_bearing_entity_matches_real_hibernate_default(self):
        # Regression guard for the to_snake_case bug flagged (and deferred)
        # across every prior round: the old implementation inserted an
        # underscore before every capital letter, turning SLARule into
        # s_l_a_rule. The real Spring/Hibernate default naming strategy
        # produces "slarule" instead — see to_snake_case's docstring for the
        # verified source. This is deliberately NOT "sla_rule": that's the
        # "nicer" guess a naive acronym-aware fix would produce, and it's
        # just as wrong for this function's purpose as the old bug was.
        m = self.result["entity_table_map"]["SLARule"]
        self.assertEqual(m["table"], "slarule")
        self.assertEqual(m["table_name_source"], "inferred-default-naming")

    def test_entity_survives_stacked_annotations(self):
        # Regression guard: @Entity/@Table with @EntityListeners/@Cacheable
        # also present used to break a literal (non-relational) ast-grep
        # pattern entirely. See PaymentLedger.java.
        m = self.result["entity_table_map"]["PaymentLedger"]
        self.assertEqual(m["table"], "payment_ledger")
        self.assertEqual(m["table_name_source"], "explicit")

    def test_entityscan_is_not_a_false_positive_entity(self):
        # Regression guard for a REAL bug found by running the old scanner
        # against a production codebase's Application.java: it did
        # `"@Entity" in text`, a substring check that also matched
        # "@EntityScan(...)". Misc.java carries @EntityScan on a non-entity
        # class specifically to guard against that recurring.
        self.assertNotIn("SecurityConfig", self.result["entity_table_map"])

    def test_three_real_entities_and_no_more(self):
        # NOTE: SLARule.java is deliberately excluded from this count — it's
        # a dedicated fixture for test_acronym_bearing_entity_matches_real_
        # hibernate_default above and would make this assertion's name a lie.
        # It's still covered by test_excluded_dirs_are_not_scanned's file
        # sweep and by its own dedicated test.
        entities = set(self.result["entity_table_map"].keys()) - {"SLARule"}
        self.assertEqual(entities, {"Invoice", "LegacyAudit", "PaymentLedger"})

    # ---- repository detection ----

    def test_plain_repository(self):
        entries = self._entries_for("persistence", "InvoiceRepository.java")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["repository"], "InvoiceRepository")
        self.assertEqual(entries[0]["entity"], "Invoice")
        self.assertEqual(entries[0]["id_type"], "Long")

    def test_repository_survives_leading_annotation(self):
        # Regression guard: same annotation-adjacency issue as entities, for
        # "public interface $N extends JpaRepository<...> {$$$}". Most real
        # repository interfaces carry @Repository, which used to break this.
        entries = self._entries_for("persistence", "AnnotatedRepository.java")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["repository"], "AnnotatedRepository")

    def test_non_repository_interface_is_not_matched(self):
        # Negative case: NotARepository.java sits in the same conceptual
        # role but extends nothing Spring-Data-shaped. Zero matches expected
        # — detection is structural, not filename/directory based.
        self.assertEqual(len(self._entries_for("persistence", "NotARepository.java")), 0)

    # ---- raw queries: jpql vs native, argument-order independence ----

    def test_jpql_query_extracted(self):
        entries = self._entries_for("raw_queries", "InvoiceRepository.java")
        jpql = [e for e in entries if e["query_kind"] == "jpql"]
        self.assertEqual(len(jpql), 1)
        self.assertEqual(jpql[0]["query"], "SELECT i FROM Invoice i WHERE i.status = :status")

    def test_native_query_extracted_regardless_of_argument_order(self):
        # nativeQuery=true appears AFTER the query string here — a fixed
        # this-line-or-next-line heuristic or an argument-order-sensitive
        # pattern both got this right only by accident.
        entries = self._entries_for("raw_queries", "InvoiceRepository.java")
        native = [e for e in entries if e["query_kind"] == "native"]
        self.assertEqual(len(native), 1)
        self.assertEqual(native[0]["query"], "SELECT * FROM billing_invoice WHERE status = :status")

    # ---- native-query SQL lineage (sqllineage integration) ----

    def test_native_query_lineage_extracts_source_table(self):
        # This is the real integration path: scan() -> extract_sql_lineage()
        # -> the actual sqllineage library, against the fixture's real
        # native query text (":status" named parameter and all).
        entries = self._entries_for("raw_queries", "InvoiceRepository.java")
        native = next(e for e in entries if e["query_kind"] == "native")
        self.assertIn("lineage", native)
        self.assertTrue(native["lineage"]["available"], native["lineage"].get("reason"))
        self.assertEqual(native["lineage"]["source_tables"], ["billing_invoice"])
        self.assertEqual(native["lineage"]["target_tables"], [])

    def test_jpql_query_resolves_lineage_via_entity_table_map(self):
        # The fixture's JPQL query ("SELECT i FROM Invoice i WHERE
        # i.status = :status") is exactly the bounded single-entity case
        # resolve_jpql_to_lineage() handles: Invoice -> billing_invoice via
        # entity_table_map (Invoice.java's @Table(name="billing_invoice")),
        # alias "i." stripped, then fed through the same extract_sql_lineage()
        # native queries use. Real integration path, not a mocked lookup.
        entries = self._entries_for("raw_queries", "InvoiceRepository.java")
        jpql = next(e for e in entries if e["query_kind"] == "jpql")
        self.assertIn("lineage", jpql)
        self.assertTrue(jpql["lineage"]["available"], jpql["lineage"].get("reason"))
        self.assertEqual(jpql["lineage"]["source_tables"], ["billing_invoice"])

    # ---- api_surface / security ----

    def test_controller_and_mappings(self):
        entries = self._entries_for("api_surface", "InvoiceController.java")
        self.assertEqual(len(entries), 4)  # @RestController, @RequestMapping, @GetMapping, @PostMapping

    def test_multiline_security_annotation_detected(self):
        entries = self._entries_for("security", "InvoiceController.java")
        self.assertEqual(len(entries), 1)

    # ---- dedup: two distinct AST matches on one line collapse to one entry ----

    def test_same_line_double_usage_is_deduped(self):
        # Misc.java has `RestTemplate restTemplate = new RestTemplate();` —
        # two real, distinct type_identifier matches on one line. The old
        # regex scanner reported at most one hit per line; this scanner
        # dedupes by (file, line, ruleId) to match that, rather than
        # reporting every AST node individually.
        entries = self._entries_for("outbound_clients", "Misc.java")
        self.assertEqual(len(entries), 2)  # one import entry + one deduped usage entry

    def test_evidence_is_sorted_for_determinism(self):
        for bucket, entries in self.evidence.items():
            keys = [(e["file"], e.get("line", 0)) for e in entries]
            self.assertEqual(keys, sorted(keys), f"evidence[{bucket}] is not sorted")

    def test_entity_table_map_is_sorted_for_determinism(self):
        # entity_table_map is built inside the same ast-grep match loop as the
        # evidence buckets above, and for a long time was the one structure in
        # scan()'s output that never got sorted on the way out.
        keys = list(self.result["entity_table_map"].keys())
        self.assertEqual(keys, sorted(keys), "entity_table_map keys are not sorted")


class ScanDeterminismTest(unittest.TestCase):
    """Same input tree must produce byte-identical output.

    Everything downstream of the scanner hashes raw bytes —
    compute_file_signature(), run_manifest.json's file_signatures, and any
    future assertion that a run is reproducible. So 'the content is equal' is
    not the property that matters here; 'the serialization is equal' is. These
    tests assert the stronger one.
    """

    def test_two_scans_of_the_same_tree_serialize_identically(self):
        # Measured caveat, recorded so nobody reads more into a green result
        # here than it earns: when this was run against the unfixed scanner
        # (entity_table_map emitted in ast-grep match order), this test still
        # PASSED, while the ordering invariants above failed. Two scans inside
        # one process happened to see the same match order, so back-to-back
        # comparison did not expose the very defect it was written for.
        #
        # Keep it as a broad regression net for nondeterminism that does vary
        # per call, but the explicit sortedness assertions are the detectors
        # that actually work. A probe that only re-runs and diffs is weaker
        # than an invariant that names the property.
        first = spring_signal_scan.scan(FIXTURE_DIR)
        second = spring_signal_scan.scan(FIXTURE_DIR)
        self.assertEqual(
            json.dumps(first, indent=2, sort_keys=False),
            json.dumps(second, indent=2, sort_keys=False),
            "two scans of an unchanged tree produced different bytes",
        )

    def test_duplicate_class_name_resolves_to_lowest_file_path(self):
        # entity_table_map is keyed by simple class name, so two @Entity
        # classes in different packages collide. Before the fix, the winner
        # was whichever match ast-grep happened to emit last — unstable across
        # runs on identical input.
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        for pkg, table in (("pkg_a", "a_user"), ("pkg_b", "b_user")):
            pkg_dir = os.path.join(tmp, pkg)
            os.makedirs(pkg_dir)
            with open(os.path.join(pkg_dir, "User.java"), "w", encoding="utf-8") as fh:
                fh.write(
                    f"package com.example.{pkg};\n\n"
                    "import jakarta.persistence.*;\n\n"
                    "@Entity\n"
                    f'@Table(name = "{table}")\n'
                    "public class User {\n"
                    "    @Id\n"
                    "    private Long id;\n"
                    "}\n"
                )

        entry = spring_signal_scan.scan(tmp)["entity_table_map"]["User"]
        self.assertEqual(entry["table"], "a_user")
        self.assertTrue(entry["file"].startswith("pkg_a"), entry["file"])

        # And it stays that way — the point is stability, not the specific
        # winner.
        again = spring_signal_scan.scan(tmp)["entity_table_map"]["User"]
        self.assertEqual(entry, again)


class SqlLineageExtractionTest(unittest.TestCase):
    """Unit-level tests against extract_sql_lineage() directly, rather than
    through a full scan() — same real sqllineage dependency, no mocking,
    just exercising query shapes the fixture repo doesn't happen to cover
    (positional params, UPDATE/INSERT target-table detection, genuinely
    malformed input, and the soft-degradation path when sqllineage is
    unavailable)."""

    def test_positional_param_query_extracts_source_table(self):
        result = spring_signal_scan.extract_sql_lineage(
            "SELECT * FROM billing_invoice WHERE id = ?1 AND status = ?2"
        )
        self.assertTrue(result["available"], result.get("reason"))
        self.assertEqual(result["source_tables"], ["billing_invoice"])

    def test_update_query_extracts_target_table(self):
        result = spring_signal_scan.extract_sql_lineage(
            "UPDATE billing_invoice SET status = :status WHERE id = :id"
        )
        self.assertTrue(result["available"], result.get("reason"))
        self.assertEqual(result["target_tables"], ["billing_invoice"])

    def test_insert_query_extracts_target_table(self):
        result = spring_signal_scan.extract_sql_lineage(
            "INSERT INTO audit_log (event, ts) VALUES (:event, :ts)"
        )
        self.assertTrue(result["available"], result.get("reason"))
        self.assertEqual(result["target_tables"], ["audit_log"])

    def test_join_query_extracts_both_source_tables(self):
        result = spring_signal_scan.extract_sql_lineage(
            "SELECT i.id FROM billing_invoice i "
            "JOIN customer c ON i.customer_id = c.id WHERE i.status = ?"
        )
        self.assertTrue(result["available"], result.get("reason"))
        self.assertEqual(result["source_tables"], ["billing_invoice", "customer"])

    def test_time_literal_survives_param_normalization(self):
        # Regression guard for the negative-lookbehind in NAMED_PARAM_RE:
        # a time literal's colons must not be mistaken for bind parameters
        # (each one is preceded by a digit, never by whitespace/operator/
        # '('/',' the way a real ":status"-style parameter always is).
        result = spring_signal_scan.extract_sql_lineage(
            "SELECT * FROM billing_invoice WHERE created_at > '2024-01-01 12:00:00'"
        )
        self.assertTrue(result["available"], result.get("reason"))
        self.assertEqual(result["source_tables"], ["billing_invoice"])

    def test_malformed_sql_degrades_gracefully(self):
        result = spring_signal_scan.extract_sql_lineage("this is not sql at all !!! @#$%")
        self.assertFalse(result["available"])
        self.assertIn("reason", result)

    def test_spel_expression_degrades_gracefully_not_raises(self):
        # A Spring SpEL expression like :#{#tenant} is real, fairly common
        # (multi-tenant native queries) Spring syntax, but it is not real
        # bind-parameter syntax NAMED_PARAM_RE normalizes, and it isn't
        # valid SQL either. This must degrade, not raise all the way up
        # through scan().
        result = spring_signal_scan.extract_sql_lineage(
            "SELECT * FROM billing_invoice WHERE tenant_id = :#{#tenant}"
        )
        self.assertFalse(result["available"])
        self.assertIn("reason", result)

    def test_dialect_override_is_honored(self):
        # mysql-specific backtick-quoted identifiers fail to parse under
        # plain ansi but succeed once the real dialect is passed — proof
        # the --sql-dialect flag actually reaches sqllineage, not just that
        # the default works.
        query = "SELECT * FROM `billing_invoice` WHERE status = ?"
        ansi_result = spring_signal_scan.extract_sql_lineage(query, dialect="ansi")
        mysql_result = spring_signal_scan.extract_sql_lineage(query, dialect="mysql")
        self.assertFalse(ansi_result["available"])
        self.assertTrue(mysql_result["available"], mysql_result.get("reason"))
        self.assertEqual(mysql_result["source_tables"], ["billing_invoice"])

    def test_unavailable_when_sqllineage_not_installed(self):
        # Simulates the "package genuinely not installed" branch by
        # flipping the module's own availability flag — this exercises our
        # soft-degradation code path, not sqllineage's parsing behavior
        # (which every other test in this class already covers for real).
        original = spring_signal_scan._SQLLINEAGE_AVAILABLE
        spring_signal_scan._SQLLINEAGE_AVAILABLE = False
        try:
            result = spring_signal_scan.extract_sql_lineage(
                "SELECT * FROM billing_invoice WHERE status = :status"
            )
        finally:
            spring_signal_scan._SQLLINEAGE_AVAILABLE = original
        self.assertEqual(result, {"available": False, "reason": "sqllineage not installed"})


class JpqlLineageResolutionTest(unittest.TestCase):
    """Unit-level tests against resolve_jpql_to_lineage() directly, with a
    synthetic entity_table_map — covers the bounded resolver's happy path
    plus each explicitly-out-of-scope case named in its own docstring
    (multi-entity FROM, association traversal, JPQL-only functions, an
    unresolved entity name). SpringSignalScanTest.test_jpql_query_resolves_
    lineage_via_entity_table_map covers the same happy path through the
    real scan()/entity_table_map integration; these are the narrower unit
    cases that don't need a fixture repo."""

    ENTITY_TABLE_MAP = {
        "Invoice": {"table": "billing_invoice", "table_name_source": "explicit"},
        "Customer": {"table": "customer", "table_name_source": "inferred-default-naming"},
    }

    def test_single_entity_query_resolves(self):
        result = spring_signal_scan.resolve_jpql_to_lineage(
            "SELECT i FROM Invoice i WHERE i.status = :status", self.ENTITY_TABLE_MAP
        )
        self.assertTrue(result["available"], result.get("reason"))
        self.assertEqual(result["source_tables"], ["billing_invoice"])

    def test_resolved_lineage_records_which_entity_it_used(self):
        # Drift-check needs this to detect a cross-file dependency: a JPQL
        # citation's lineage can go stale because the *entity's* file
        # changed (e.g. @Table renamed), not the query's own file — see
        # spring_drift_check.py's _reverify_jpql_lineage_provenance().
        result = spring_signal_scan.resolve_jpql_to_lineage(
            "SELECT i FROM Invoice i WHERE i.status = :status", self.ENTITY_TABLE_MAP
        )
        self.assertEqual(result["resolved_via_entity"], "Invoice")

    def test_unresolved_lineage_has_no_resolved_via_entity(self):
        result = spring_signal_scan.resolve_jpql_to_lineage(
            "SELECT i FROM Invoice i JOIN i.customer c WHERE c.active = true", self.ENTITY_TABLE_MAP
        )
        self.assertNotIn("resolved_via_entity", result)

    def test_query_with_as_keyword_resolves(self):
        result = spring_signal_scan.resolve_jpql_to_lineage(
            "SELECT c FROM Customer AS c WHERE c.active = true", self.ENTITY_TABLE_MAP
        )
        self.assertTrue(result["available"], result.get("reason"))
        self.assertEqual(result["source_tables"], ["customer"])

    def test_multi_entity_from_clause_out_of_scope(self):
        result = spring_signal_scan.resolve_jpql_to_lineage(
            "SELECT i FROM Invoice i, Customer c WHERE i.customerId = c.id", self.ENTITY_TABLE_MAP
        )
        self.assertFalse(result["available"])
        self.assertIn("out of scope", result["reason"])

    def test_join_clause_out_of_scope(self):
        result = spring_signal_scan.resolve_jpql_to_lineage(
            "SELECT i FROM Invoice i JOIN i.customer c WHERE c.active = true", self.ENTITY_TABLE_MAP
        )
        self.assertFalse(result["available"])
        self.assertIn("out of scope", result["reason"])

    def test_association_traversal_out_of_scope(self):
        result = spring_signal_scan.resolve_jpql_to_lineage(
            "SELECT i FROM Invoice i WHERE i.customer.name = :name", self.ENTITY_TABLE_MAP
        )
        self.assertFalse(result["available"])
        self.assertIn("association-traversal", result["reason"])

    def test_jpql_only_function_out_of_scope(self):
        result = spring_signal_scan.resolve_jpql_to_lineage(
            "SELECT i FROM Invoice i WHERE SIZE(i.lineItems) > 0", self.ENTITY_TABLE_MAP
        )
        self.assertFalse(result["available"])
        self.assertIn("JPQL-only", result["reason"])

    def test_unresolved_entity_name_out_of_scope(self):
        # Not in entity_table_map at all — e.g. an @Entity(name=...) override
        # this scanner doesn't currently extract, or a genuinely unscanned
        # entity. Must degrade, not KeyError.
        result = spring_signal_scan.resolve_jpql_to_lineage(
            "SELECT p FROM Payment p WHERE p.status = :status", self.ENTITY_TABLE_MAP
        )
        self.assertFalse(result["available"])
        self.assertIn("not found in entity_table_map", result["reason"])

    def test_no_from_clause_out_of_scope(self):
        # JPQL bulk UPDATE/DELETE don't use FROM at all — the resolver
        # should degrade cleanly, not assume a SELECT-shaped query.
        result = spring_signal_scan.resolve_jpql_to_lineage(
            "UPDATE Invoice i SET i.status = :status WHERE i.id = :id", self.ENTITY_TABLE_MAP
        )
        self.assertFalse(result["available"])


class ReferencesBucketTest(unittest.TestCase):
    """references__import / references__package (spring_ast_grep_rules.yml)
    build a repo-wide import/package index so file-summarizer can find
    cross-group relationships its own per-group file view can't see (see
    the "references" rule block's header comment). Two files in different
    fictional "groups" (directories, standing in for partition_repo.py
    groups, which this scanner has no concept of) — groupA/Consumer.java
    importing groupB.Service — must produce a references__import entry
    for the import, independent of any group boundary."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        group_a = os.path.join(self.tmpdir, "groupA")
        group_b = os.path.join(self.tmpdir, "groupB")
        os.makedirs(group_a)
        os.makedirs(group_b)
        with open(os.path.join(group_a, "Consumer.java"), "w") as f:
            f.write(
                "package groupA;\n\n"
                "import groupB.Service;\n\n"
                "public class Consumer {\n"
                "    private final Service service = new Service();\n"
                "}\n"
            )
        with open(os.path.join(group_b, "Service.java"), "w") as f:
            f.write("package groupB;\n\npublic class Service {\n}\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cross_group_import_appears_in_references_bucket(self):
        result = spring_signal_scan.scan(self.tmpdir)
        import_entries = [
            e for e in result["evidence"]["references"]
            if e["rule_id"] == "references__import" and e["file"] == "groupA/Consumer.java"
        ]
        self.assertEqual(len(import_entries), 1)
        self.assertIn("groupB.Service", import_entries[0]["match"])


class BuildFileClassificationTest(unittest.TestCase):
    """Gradle/Maven build scripts and build-adjacent property files.

    These are classified by FILENAME, not parsed: ast-grep has no Groovy
    grammar at all (`-l groovy` -> "groovy is not supported!"), so a
    .gradle file can never get the structural treatment every .java rule
    gets. Before this existed they fell through every branch in scan()'s
    pass 1 -- read by file-summarizer, since partition_repo.py does not
    exclude them, but carrying no bucket and, more seriously, never
    reaching the secret-redaction path.

    Note these do NOT go through rule_coverage.py's non-vacuity gate, which
    only covers ast-grep rules. This suite is the only thing asserting the
    Python filename path works, so an assertion missing here is a hole
    nothing else covers."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name, text=""):
        path = os.path.join(self.tmpdir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def _matches(self, result, bucket):
        return {(e["file"], e.get("match")) for e in result["evidence"][bucket]}

    def test_build_scripts_land_in_deployment(self):
        for name in ("build.gradle", "settings.gradle.kts", "pom.xml",
                     "build.xml", "extra.groovy"):
            self._write(name, "// build\n")
        found = self._matches(spring_signal_scan.scan(self.tmpdir), "deployment")
        for name in ("build.gradle", "settings.gradle.kts", "pom.xml",
                     "build.xml", "extra.groovy"):
            self.assertIn((name, "build script"), found, name)

    def test_a_plain_kts_script_is_not_a_build_file(self):
        """`.kts` alone is any Kotlin script. Matching it would put arbitrary
        Kotlin into operations.md, so the compound suffix is what counts."""
        self._write("scratch.kts", "println(1)\n")
        found = self._matches(spring_signal_scan.scan(self.tmpdir), "deployment")
        self.assertNotIn(("scratch.kts", "build script"), found)

    def test_gradle_properties_is_treated_as_config(self):
        self._write("gradle.properties", "org.gradle.jvmargs=-Xmx2g\n")
        found = self._matches(spring_signal_scan.scan(self.tmpdir), "configuration")
        self.assertIn(("gradle.properties", "config file"), found)

    def test_a_credential_in_gradle_properties_is_redacted(self):
        """The defect that motivated this: build.gradle's own comment records
        that gradle.properties carries `_password` entries, and that file
        matched none of the config patterns, so it never reached the
        redaction path at all."""
        self._write("gradle.properties", "repoUser=ci\nrepoPassword=hunter2literal\n")
        zones = spring_signal_scan.scan(self.tmpdir)["redaction_zones"]
        self.assertIn("gradle.properties", zones)
        self.assertEqual([z["line"] for z in zones["gradle.properties"]], [2])

    def test_a_quoted_placeholder_in_a_build_script_is_not_redacted(self):
        """Routing more files into the redaction path made an existing
        false positive matter: a quoted `${...}` was reported as a literal
        credential because the placeholder regex is anchored and the value
        keeps its quotes. Real build scripts write them exactly this way."""
        self._write("domain.gradle", 'password = "${REPO_PASSWORD}"\n')
        zones = spring_signal_scan.scan(self.tmpdir)["redaction_zones"]
        self.assertNotIn("domain.gradle", zones)

    def test_build_output_directories_stay_excluded(self):
        self._write("build/generated/Thing.java", "package x;\npublic class Thing {}\n")
        result = spring_signal_scan.scan(self.tmpdir)
        files = {e["file"] for entries in result["evidence"].values() for e in entries}
        self.assertFalse([f for f in files if f.startswith("build/")], files)


class RespectGitignoreOptInTest(unittest.TestCase):
    """--respect-gitignore is additive-only: a directory not covered by the
    hardcoded EXCLUDED_DIRS floor (unlike vendor/, venv/, etc.) should only
    disappear from the scan when the repo's own .gitignore excludes it AND
    the caller opts in via respect_gitignore=True.

    This scratch repo is a real `git init`-ed one, not just a bare
    directory with a .gitignore file: ast-grep's own native gitignore
    handling (what run_ast_grep's --no-ignore vcs omission relies on for
    the ast-grep-side half of this feature) only activates inside an
    actual VCS root, the same as ripgrep's underlying `ignore` crate --
    a .gitignore next to files with no .git present is invisible to it.
    Real target repos for this plugin are checkouts, so this is
    realistic, not a workaround."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        subprocess.run(["git", "init", "-q"], cwd=self.tmpdir, check=True)
        scratch_dir = os.path.join(self.tmpdir, "scratch_module")
        os.makedirs(scratch_dir)
        with open(os.path.join(scratch_dir, "Scratch.java"), "w") as f:
            f.write("package scratch_module;\n\n@Entity\npublic class Scratch {\n}\n")
        with open(os.path.join(self.tmpdir, ".gitignore"), "w") as f:
            f.write("scratch_module/\n")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scratch_module_scanned_without_opt_in(self):
        result = spring_signal_scan.scan(self.tmpdir)
        self.assertEqual(result["files_scanned"]["java"], 1)
        self.assertIn("Scratch", result["entity_table_map"])

    def test_scratch_module_excluded_with_opt_in(self):
        result = spring_signal_scan.scan(self.tmpdir, respect_gitignore=True)
        self.assertEqual(result["files_scanned"]["java"], 0)
        self.assertNotIn("Scratch", result["entity_table_map"])




class AstGrepFailureIsAnExceptionTest(unittest.TestCase):
    """run_ast_grep() used to call sys.exit(1) on a failing ast-grep.

    That is the identical defect AstGrepNotFoundError was introduced to fix
    in find_ast_grep(), left in place at two sites because the original fix
    converted only the "binary missing" path. SystemExit derives from
    BaseException, and unittest's _handleClassSetUp catches only Exception --
    so a sys.exit() raised under setUpClass (which is where three suites call
    scan()) kills the whole test process with no "Ran N tests" line, instead
    of being reported as one class's setUpClass error.

    These tests pin the property that actually matters: an ordinary
    `except Exception` must catch it. Asserting the exception type alone
    would not -- SystemExit would satisfy an assertRaises(BaseException) just
    as well, which is precisely how this went unnoticed the first time.
    """

    class _FakeProc:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def _run_with(self, proc, monkey):
        original = spring_signal_scan.subprocess.run
        spring_signal_scan.subprocess.run = lambda *a, **k: proc
        try:
            return monkey()
        finally:
            spring_signal_scan.subprocess.run = original

    def test_nonzero_exit_raises_ast_grep_error(self):
        proc = self._FakeProc(returncode=2, stderr="bad rule file")
        with self.assertRaises(spring_signal_scan.AstGrepError):
            self._run_with(proc, lambda: spring_signal_scan.run_ast_grep("ast-grep", "."))

    def test_unparseable_output_raises_ast_grep_error(self):
        proc = self._FakeProc(returncode=0, stdout="not json at all")
        with self.assertRaises(spring_signal_scan.AstGrepError):
            self._run_with(proc, lambda: spring_signal_scan.run_ast_grep("ast-grep", "."))

    def test_nonzero_exit_is_catchable_as_a_plain_exception(self):
        """The regression witness. Against the pre-fix code this fails by
        the SystemExit propagating straight through the `except Exception`."""
        proc = self._FakeProc(returncode=2, stderr="bad rule file")
        caught = None
        try:
            self._run_with(proc, lambda: spring_signal_scan.run_ast_grep("ast-grep", "."))
        except Exception as exc:  # noqa: BLE001 -- catching broadly is the point
            caught = exc
        self.assertIsNotNone(
            caught, "run_ast_grep raised something `except Exception` cannot catch")
        self.assertNotIsInstance(caught, SystemExit)

    def test_unparseable_output_is_catchable_as_a_plain_exception(self):
        proc = self._FakeProc(returncode=0, stdout="{{{")
        caught = None
        try:
            self._run_with(proc, lambda: spring_signal_scan.run_ast_grep("ast-grep", "."))
        except Exception as exc:  # noqa: BLE001 -- catching broadly is the point
            caught = exc
        self.assertIsNotNone(caught)
        self.assertNotIsInstance(caught, SystemExit)

    def test_the_failure_message_still_names_ast_grep_and_the_status(self):
        """CLI behavior is meant to be unchanged: main() prints the exception
        and exits 1, so the text a user sees must still carry the detail that
        used to be printed directly."""
        proc = self._FakeProc(returncode=3, stderr="rule parse failed")
        with self.assertRaises(spring_signal_scan.AstGrepError) as ctx:
            self._run_with(proc, lambda: spring_signal_scan.run_ast_grep("ast-grep", "."))
        message = str(ctx.exception)
        self.assertIn("ast-grep", message)
        self.assertIn("3", message)
        self.assertIn("rule parse failed", message)

    def test_not_found_error_is_still_an_ast_grep_error(self):
        """Subclassing keeps every existing `except AstGrepNotFoundError`
        call site meaning exactly what it meant before."""
        self.assertTrue(issubclass(spring_signal_scan.AstGrepNotFoundError,
                                   spring_signal_scan.AstGrepError))


if __name__ == "__main__":
    unittest.main()
