"""Covering proof, ABSENCE/UNPROVEN writers, and recall delta."""

import unittest
from pathlib import Path

from doc_engine.scanning.absence import write_absence_facts
from doc_engine.scanning.covering import (
    build_covering_proof,
    build_receipt,
    inventory_root,
    subset_root,
    verify_covering_proof,
    write_covering_proof,
)
from doc_engine.scanning.gap_probe import (
    CoveringPreconditionError,
    build_gap_report,
    measure_r_absence,
    measure_r_recall,
)
from doc_engine.scanning.recall_delta import write_recall_miss_facts


class CoveringProofTest(unittest.TestCase):
    def test_inventory_root_stable(self):
        sigs = {"a.java": "aaa", "b.yml": "bbb"}
        self.assertEqual(inventory_root(sigs), inventory_root(dict(reversed(list(sigs.items())))))

    def test_subset_root_diverges_on_missing_path(self):
        sigs = {"a.java": "aaa"}
        self.assertNotEqual(
            subset_root(sigs, ["a.java"]),
            subset_root(sigs, ["a.java", "missing.java"]),
        )

    def test_verify_requires_acked_eq_expected(self):
        sigs = {"x.java": "1"}
        root = inventory_root(sigs)
        good = build_receipt(
            scanner="filesystem",
            version_hash="v",
            scope="all",
            expected_subset_root=root,
            acked_subset_root=root,
            status="complete",
        )
        proof = build_covering_proof(
            file_signatures=sigs,
            scanner_version="sv",
            receipts=[good],
        )
        ok, why = verify_covering_proof(proof, file_signatures=sigs, scanner_version="sv")
        self.assertTrue(ok, why)

        bad = dict(good)
        bad["acked_subset_root"] = "nope"
        proof_bad = build_covering_proof(
            file_signatures=sigs,
            scanner_version="sv",
            receipts=[bad],
        )
        ok2, why2 = verify_covering_proof(
            proof_bad, file_signatures=sigs, scanner_version="sv",
        )
        self.assertFalse(ok2)
        self.assertIn("acked_subset_root", why2)


class AbsenceWriterTest(unittest.TestCase):
    def test_callable_zero_hits_is_absence(self):
        signals = {
            "evidence": {
                "deployment": [
                    {
                        "file": "build.gradle",
                        "line": 1,
                        "match": "org.springframework.kafka:spring-kafka",
                        "rule_id": "deployment__build_dependency",
                    }
                ],
                "messaging": [],
            },
            "config_key_sets": {},
        }
        facts = write_absence_facts(
            signals,
            covering_ok=True,
            covering_root="abc",
            scanner_version="sv",
            astgrep_receipt_complete=True,
        )
        messaging = [f for f in facts if f["subject"] == "family:messaging"]
        self.assertEqual(len(messaging), 1)
        self.assertEqual(messaging[0]["predicate"], "ABSENCE")
        self.assertEqual(messaging[0]["qualifiers"]["trial"], "callable")

    def test_non_callable_without_witness_is_unproven(self):
        signals = {"evidence": {"deployment": [], "messaging": []}, "config_key_sets": {}}
        facts = write_absence_facts(
            signals,
            covering_ok=True,
            covering_root="abc",
            scanner_version="sv",
            astgrep_receipt_complete=True,
        )
        messaging = [f for f in facts if f["subject"] == "family:messaging"]
        self.assertEqual(messaging[0]["predicate"], "UNPROVEN")
        self.assertEqual(messaging[0]["qualifiers"]["trial"], "non_callable")

    def test_covering_failed_never_absence(self):
        signals = {
            "evidence": {
                "deployment": [
                    {"file": "p.xml", "line": 1, "match": "spring-kafka", "rule_id": "d"}
                ],
                "messaging": [],
            },
            "config_key_sets": {},
        }
        facts = write_absence_facts(
            signals,
            covering_ok=False,
            covering_root=None,
            scanner_version="sv",
            astgrep_receipt_complete=True,
        )
        messaging = [f for f in facts if f["subject"] == "family:messaging"]
        self.assertEqual(messaging[0]["predicate"], "UNPROVEN")


class RecallDeltaTest(unittest.TestCase):
    def test_oracle_minus_native_emits_recall_miss(self):
        signals = {"entity_table_map": {}}
        facts = write_recall_miss_facts(
            signals,
            native_entity_keys={"Seen"},
            oracle_entity_keys={"Seen", "Hidden"},
            oracle_arm="codeql",
        )
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["predicate"], "RECALL_MISS")
        self.assertEqual(facts[0]["qualifiers"]["display_name"], "Hidden")
        self.assertIn(facts[0]["qualifiers"]["verdict"], {"STRUCTURAL", "EVIDENTIARY"})

    def test_no_oracle_keys_emits_nothing(self):
        facts = write_recall_miss_facts(
            {},
            native_entity_keys={"A"},
            oracle_entity_keys=set(),
            oracle_arm="codeql",
        )
        self.assertEqual(facts, [])


class GapProbeCoveringGateTest(unittest.TestCase):
    def test_refuses_without_covering(self):
        with self.assertRaises(CoveringPreconditionError):
            build_gap_report(
                {"entity_table_map": {}, "evidence": {}, "scanner_version": "x"},
                [],
                covering_ok=False,
                covering_why="missing",
            )

    def test_absence_rate_ignores_unproven(self):
        facts = [
            {
                "predicate": "ABSENCE",
                "subject": "family:messaging",
                "qualifiers": {"trial": "callable", "family": "messaging"},
            },
            {
                "predicate": "UNPROVEN",
                "subject": "family:redis",
                "qualifiers": {"trial": "non_callable", "family": "redis"},
            },
        ]
        block = measure_r_absence(facts)
        self.assertEqual(block["callable_absence"], 1)
        self.assertEqual(block["unproven"], 1)
        self.assertEqual(block["denominator"], 1)

    def test_recall_omitted_without_oracle(self):
        self.assertIsNone(measure_r_recall([], oracle_arm_present=False))

    def test_gap_report_with_covering(self):
        sigs = {"a.java": "1"}
        root = inventory_root(sigs)
        receipt = build_receipt(
            scanner="filesystem",
            version_hash="v",
            scope="all",
            expected_subset_root=root,
            acked_subset_root=root,
            status="complete",
        )
        proof = build_covering_proof(
            file_signatures=sigs, scanner_version="sv", receipts=[receipt],
        )
        signals = {
            "schema_version": 7,
            "scanner_version": "sv",
            "file_signatures": sigs,
            "entity_table_map": {},
            "evidence": {},
        }
        report, _ = build_gap_report(
            signals,
            [],
            covering_proof=proof,
            covering_ok=True,
        )
        self.assertTrue(report["s1_covering"]["verified"])
        self.assertIn("R_absence", report["rates"])
        self.assertEqual(report["rates"]["R_absence"]["polarity"], "failure_mass")
        self.assertIn("R_recall", report["rates"])
        self.assertTrue(report["rates"]["R_recall"]["omitted"])
        self.assertEqual(report["rates"]["R_recall"]["claim"], "omitted_without_oracle")
        self.assertFalse(report["rates"]["oracle"]["trusted_codeql_arm"])


class CoveringWriteRoundTripTest(unittest.TestCase):
    def test_write_covering_proof(self):
        import tempfile

        sigs = {"z.java": "zz"}
        root = inventory_root(sigs)
        proof = build_covering_proof(
            file_signatures=sigs,
            scanner_version="sv",
            receipts=[
                build_receipt(
                    scanner="ast-grep",
                    version_hash="v",
                    scope="java",
                    expected_subset_root=subset_root(sigs, ["z.java"]),
                    acked_subset_root=subset_root(sigs, ["z.java"]),
                    status="complete",
                )
            ],
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "covering_proof.json"
            write_covering_proof(path, proof)
            self.assertTrue(path.is_file())
            ok, why = verify_covering_proof(
                proof, file_signatures=sigs, scanner_version="sv",
            )
            self.assertTrue(ok, why)
            self.assertEqual(proof["inventory_root"], root)


if __name__ == "__main__":
    unittest.main()
