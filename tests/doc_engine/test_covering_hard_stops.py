#!/usr/bin/env python3
"""Hard-stop falsifiers for Stage-0 covering / ABSENCE / recall writers.

Each test docstring names the deviation it must catch. Levels covered here
(only those that bite this change — not Wikipedia theater):

  Unit / white-box     covering roots, callable predicates, recall verdicts
  Integration / grey   orchestrator barrier, covering_writer_facts, Fact ledger
  Black-box CLI        spring_signal_scan + gap_probe exit codes and artifacts
  Contract             covering_proof.schema.json + Fact.model_validate
  Property             inventory_root permutation invariance
  Destructive          soft-fail / mismatch / WinError-206-solo cannot green Path A
  Smoke / regression   fixture CLI emit covering + strip internal keys
  Metamorphic (narrow) chunked matches ≡ single-budget matches (wiring suite)

Out of scope for this file: visual, A/B, accessibility, i18n, beta, VCR, perf soak.
See claude/research/stage0-covering-absence-recall-2026-07-30.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from doc_engine.core.context import FileEntry, ScanContext
from doc_engine.pipeline.artifacts import Fact
from doc_engine.scanning._orchestrator import CoveringProofError, run_scan
from doc_engine.scanning._scanner_astgrep import AstGrepBackend
from doc_engine.scanning.absence import write_absence_facts
from doc_engine.scanning.covering import (
    COVERING_PROOF_SCHEMA_VERSION,
    build_covering_proof,
    build_receipt,
    inventory_root,
    subset_root,
    verify_covering_proof,
    write_covering_proof,
)
from doc_engine.scanning.facts import (
    covering_writer_facts,
    facts_from_signals,
    write_facts_jsonl,
)
from doc_engine.scanning.gap_probe import (
    CoveringPreconditionError,
    build_gap_report,
    load_and_verify_covering,
    measure_r_absence,
    run_gap_probe,
)
from doc_engine.scanning.recall_delta import (
    collect_arm_entity_keys,
    write_recall_miss_facts,
)
from doc_engine.scanning.spring import AstGrepError, scan
from tests.conftest import FIXTURE_DIR, REPO_ROOT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kafka_signals(*, messaging_hits: int = 0) -> dict:
    messaging = []
    for i in range(messaging_hits):
        messaging.append(
            {
                "file": f"M{i}.java",
                "line": i + 1,
                "match": "@KafkaListener",
                "rule_id": "messaging__kafka_listener",
            }
        )
    return {
        "evidence": {
            "deployment": [
                {
                    "file": "build.gradle",
                    "line": 1,
                    "match": "org.springframework.kafka:spring-kafka",
                    "rule_id": "deployment__build_dependency",
                }
            ],
            "messaging": messaging,
        },
        "config_key_sets": {},
        "entity_table_map": {},
        "scanner_version": "sv-test",
        "scanners": ["filesystem", "ast-grep"],
    }


def _complete_receipt(scanner: str, root: str) -> dict:
    return build_receipt(
        scanner=scanner,
        version_hash="v",
        scope="java" if scanner != "filesystem" else "all_signatures",
        expected_subset_root=root,
        acked_subset_root=root,
        status="complete",
    )


# ===========================================================================
# Unit / white-box — callable ABSENCE discipline
# ===========================================================================


class CallableAbsenceFalsifiersTest(unittest.TestCase):
    def test_astgrep_receipt_incomplete_forces_unproven(self):
        """Deviation: ABSENCE emitted when rule-pack receipt is incomplete."""
        facts = write_absence_facts(
            _kafka_signals(),
            covering_ok=True,
            covering_root="root",
            scanner_version="sv",
            astgrep_receipt_complete=False,
        )
        messaging = [f for f in facts if f["subject"] == "family:messaging"]
        self.assertEqual(messaging[0]["predicate"], "UNPROVEN")

    def test_present_family_emits_no_absence_row(self):
        """Deviation: callable present family still stamped ABSENCE/UNPROVEN."""
        facts = write_absence_facts(
            _kafka_signals(messaging_hits=2),
            covering_ok=True,
            covering_root="root",
            scanner_version="sv",
            astgrep_receipt_complete=True,
        )
        messaging = [f for f in facts if f["subject"] == "family:messaging"]
        self.assertEqual(messaging, [])

    def test_empty_bucket_without_witness_never_absence(self):
        """Deviation: empty messaging bucket alone treated as feature absent."""
        signals = {
            "evidence": {"deployment": [], "messaging": []},
            "config_key_sets": {},
        }
        facts = write_absence_facts(
            signals,
            covering_ok=True,
            covering_root="root",
            scanner_version="sv",
            astgrep_receipt_complete=True,
        )
        messaging = [f for f in facts if f["subject"] == "family:messaging"]
        self.assertEqual(messaging[0]["predicate"], "UNPROVEN")
        self.assertIsNone(messaging[0]["qualifiers"]["family_witness"])


# ===========================================================================
# Unit / white-box — recall STRUCTURAL vs EVIDENTIARY
# ===========================================================================


class RecallVerdictFalsifiersTest(unittest.TestCase):
    def test_recall_codeql_impl_is_evidentiary(self):
        """Deviation: *Impl CodeQL-only miss labelled STRUCTURAL."""
        facts = write_recall_miss_facts(
            {"entity_table_map": {}},
            native_entity_keys=set(),
            oracle_entity_keys={"FooImpl"},
            oracle_arm="codeql",
        )
        self.assertEqual(facts[0]["qualifiers"]["verdict"], "EVIDENTIARY")

    def test_recall_codeql_non_impl_is_structural(self):
        """Deviation: source-reachable miss labelled EVIDENTIARY."""
        facts = write_recall_miss_facts(
            {"entity_table_map": {}},
            native_entity_keys={"Seen"},
            oracle_entity_keys={"Seen", "HiddenEntity"},
            oracle_arm="codeql",
        )
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["qualifiers"]["verdict"], "STRUCTURAL")
        self.assertEqual(facts[0]["qualifiers"]["display_name"], "HiddenEntity")

    def test_collect_arm_entity_keys_separates_native_and_oracle(self):
        """Deviation: CodeQL keys folded into native ast-grep bag."""
        native, oracle, arm = collect_arm_entity_keys(
            [
                {"entity_table_map_candidates": {"A": [{}]}},
                {"entity_table_map_candidates": {"B": [{}], "C": [{}]}},
                {"entity_table_map": {}},
            ],
            scanner_names=["ast-grep", "codeql", "filesystem"],
        )
        self.assertEqual(native, {"A"})
        self.assertEqual(oracle, {"B", "C"})
        self.assertEqual(arm, "codeql")


# ===========================================================================
# Property — inventory root
# ===========================================================================


class CoveringPropertyTest(unittest.TestCase):
    def test_inventory_root_permutation_invariant(self):
        """Deviation: inventory_root depends on dict iteration order."""
        items = [(f"f{i}.java", f"sig{i}") for i in range(20)]
        a = inventory_root(dict(items))
        b = inventory_root(dict(reversed(items)))
        c = inventory_root({k: v for k, v in sorted(items, key=lambda kv: kv[0][::-1])})
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_subset_root_monotonic_on_path_add(self):
        """Deviation: adding a path leaves subset_root unchanged."""
        sigs = {"a.java": "1", "b.java": "2"}
        r1 = subset_root(sigs, ["a.java"])
        r2 = subset_root(sigs, ["a.java", "b.java"])
        self.assertNotEqual(r1, r2)


# ===========================================================================
# Contract — schema + Fact ledger
# ===========================================================================


class CoveringContractTest(unittest.TestCase):
    def test_covering_proof_schema_accepts_emitted_proof(self):
        """Deviation: emitted covering_proof fails its own schema contract."""
        schema = json.loads(
            (REPO_ROOT / "scripts" / "schemas" / "covering_proof.schema.json").read_text(
                encoding="utf-8"
            )
        )
        sigs = {"a.java": "x"}
        root = inventory_root(sigs)
        proof = build_covering_proof(
            file_signatures=sigs,
            scanner_version="sv",
            receipts=[_complete_receipt("filesystem", root), _complete_receipt("ast-grep", root)],
        )
        for key in schema["required"]:
            self.assertIn(key, proof)
        self.assertEqual(proof["schema_version"], schema["properties"]["schema_version"]["const"])
        self.assertEqual(proof["schema_version"], COVERING_PROOF_SCHEMA_VERSION)
        self.assertGreaterEqual(len(proof["receipts"]), 1)
        for receipt in proof["receipts"]:
            for key in schema["properties"]["receipts"]["items"]["required"]:
                self.assertIn(key, receipt)
            self.assertIn(receipt["status"], {"complete", "failed"})

    def test_facts_jsonl_absence_unproven_recall_roundtrip(self):
        """Deviation: ABSENCE/UNPROVEN/RECALL_MISS rejected by Fact or lose fields on disk."""
        facts = write_absence_facts(
            _kafka_signals(),
            covering_ok=True,
            covering_root="root",
            scanner_version="sv",
            astgrep_receipt_complete=True,
        )
        facts.extend(
            write_recall_miss_facts(
                {"entity_table_map": {}},
                native_entity_keys=set(),
                oracle_entity_keys={"Hidden"},
                oracle_arm="codeql",
            )
        )
        for f in facts:
            Fact.model_validate(f)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "facts.jsonl"
            write_facts_jsonl(path, facts)
            loaded = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        self.assertEqual(len(loaded), len(facts))
        predicates = {f["predicate"] for f in loaded}
        self.assertIn("ABSENCE", predicates)
        self.assertIn("RECALL_MISS", predicates)
        for row in loaded:
            Fact.model_validate(row)


# ===========================================================================
# Integration — covering_writer_facts + orchestrator barrier
# ===========================================================================


class CoveringWriterFactsIntegrationTest(unittest.TestCase):
    def test_covering_writer_facts_emits_recall_from_partials_meta(self):
        """Deviation: RECALL_MISS not emitted from _scan_partials_meta keys."""
        sigs = {"a.java": "1"}
        root = inventory_root(sigs)
        proof = build_covering_proof(
            file_signatures=sigs,
            scanner_version="sv",
            receipts=[
                _complete_receipt("filesystem", root),
                _complete_receipt("ast-grep", root),
                _complete_receipt("codeql", root),
            ],
        )
        signals = {
            "file_signatures": sigs,
            "scanner_version": "sv",
            "evidence": {"deployment": [], "messaging": []},
            "config_key_sets": {},
            "entity_table_map": {},
            "_covering_proof": proof,
            "_scan_partials_meta": {
                "scanner_names": ["filesystem", "ast-grep", "codeql"],
                "entity_keys_by_scanner": {
                    "ast-grep": ["Seen"],
                    "codeql": ["Seen", "Missed"],
                    "filesystem": [],
                },
            },
        }
        facts = covering_writer_facts(signals)
        misses = [f for f in facts if f["predicate"] == "RECALL_MISS"]
        self.assertEqual([m["qualifiers"]["display_name"] for m in misses], ["Missed"])


class OrchestratorBarrierTest(unittest.TestCase):
    def test_run_scan_missing_receipt_refuses(self):
        """Deviation: scanner without covering_receipt still greens Path A."""

        class NoReceipt:
            name = "bogus"

            def version_hash(self) -> str:
                return "x"

            def scan(self, repo_path: str, **kwargs):
                return {"evidence": {}, "entity_table_map": {}}

        class DummyMerger:
            def merge(self, partials, repo_path, scanner_version, scanner_names=None):
                return {
                    "evidence": {},
                    "entity_table_map": {},
                    "file_signatures": {},
                    "scanner_version": scanner_version,
                    "scanners": scanner_names or [],
                }

        class DummyLineage:
            def resolve(self, merged, **kwargs):
                return merged

        with self.assertRaises(CoveringProofError) as ctx:
            run_scan(
                str(FIXTURE_DIR),
                [NoReceipt()],
                DummyMerger(),
                DummyLineage(),
            )
        self.assertIn("covering_receipt", str(ctx.exception))

    def test_run_scan_acked_mismatch_refuses(self):
        """Deviation: acked≠expected receipt still passes barrier."""

        class BadAck:
            name = "bad"

            def version_hash(self) -> str:
                return "x"

            def scan(self, repo_path: str, **kwargs):
                from doc_engine.scanning.covering import COVERING_RECEIPT_KEY

                return {
                    "evidence": {},
                    COVERING_RECEIPT_KEY: build_receipt(
                        scanner="bad",
                        version_hash="x",
                        scope="all",
                        expected_subset_root="aaa",
                        acked_subset_root="bbb",
                        status="complete",
                    ),
                }

        class DummyMerger:
            def merge(self, partials, repo_path, scanner_version, scanner_names=None):
                return {
                    "evidence": {},
                    "entity_table_map": {},
                    "file_signatures": {},
                    "scanner_version": scanner_version,
                    "scanners": scanner_names or [],
                }

        class DummyLineage:
            def resolve(self, merged, **kwargs):
                return merged

        with self.assertRaises(CoveringProofError):
            run_scan(
                str(FIXTURE_DIR),
                [BadAck()],
                DummyMerger(),
                DummyLineage(),
            )


# ===========================================================================
# Destructive — fail-closed cannot green
# ===========================================================================


class DestructiveFailClosedTest(unittest.TestCase):
    def test_winerror_206_solo_path_raises(self):
        """Deviation: single-path WinError 206 soft-skipped as empty matches."""
        backend = AstGrepBackend()
        entry = FileEntry(
            full_path="/repo/" + ("x" * 200) + ".java",
            rel_path=("x" * 200) + ".java",
            name=("x" * 200) + ".java",
            ext=".java",
        )
        sigs = {entry.rel_path: "sig"}
        win_exc = OSError(22, "filename or extension is too long")
        win_exc.winerror = 206

        with mock.patch.object(backend, "_find_ast_grep", return_value="/bin/ast-grep"):
            with mock.patch("subprocess.run", side_effect=win_exc):
                with self.assertRaises(AstGrepError) as ctx:
                    backend._run_ast_grep(
                        "/repo", java_files=[entry], file_signatures=sigs,
                    )
        self.assertIn("incomplete inventory", str(ctx.exception))

    def test_empty_java_list_with_java_signatures_fails(self):
        """Deviation: java_files=[] while signatures list .java still greens."""
        backend = AstGrepBackend()
        with mock.patch.object(backend, "_find_ast_grep", return_value="/bin/ast-grep"):
            with self.assertRaises(AstGrepError) as ctx:
                backend._run_ast_grep(
                    "/repo",
                    java_files=[],
                    file_signatures={"StillThere.java": "abc"},
                )
        self.assertIn("empty java_files", str(ctx.exception))

    def test_mid_batch_fail_propagates_through_scan(self):
        """Deviation: mid-batch ast-grep failure soft-continues into Path A."""
        ctx = ScanContext.build(str(FIXTURE_DIR))
        if len(ctx.java_files) < 1:
            self.skipTest("fixture needs java files")

        with mock.patch(
            "doc_engine.scanning._scanner_astgrep.AstGrepBackend._invoke_ast_grep",
            side_effect=AstGrepError("exited with status 1: boom"),
        ):
            with self.assertRaises((AstGrepError, CoveringProofError)):
                scan(str(FIXTURE_DIR), scanners=["filesystem", "ast-grep"])

    def test_load_and_verify_covering_rejects_scanner_version_drift(self):
        """Deviation: covering_proof with drifted scanner_version still verifies."""
        sigs = {"a.java": "1"}
        root = inventory_root(sigs)
        proof = build_covering_proof(
            file_signatures=sigs,
            scanner_version="old",
            receipts=[_complete_receipt("filesystem", root)],
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "covering_proof.json"
            write_covering_proof(path, proof)
            signals = {"file_signatures": sigs, "scanner_version": "new"}
            _, ok, why = load_and_verify_covering(
                signals, covering_path=path,
            )
        self.assertFalse(ok)
        self.assertIn("scanner_version", why)


# ===========================================================================
# gap_probe S1 / S3
# ===========================================================================


class GapProbeS1S3Test(unittest.TestCase):
    def test_run_gap_probe_missing_covering_raises(self):
        """Deviation: gap_probe scores S2 without covering_proof sibling."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            signals_path = root / "spring_signals.json"
            facts_path = root / "facts.jsonl"
            signals_path.write_text(
                json.dumps(
                    {
                        "schema_version": 7,
                        "scanner_version": "sv",
                        "file_signatures": {"a.java": "1"},
                        "entity_table_map": {},
                        "evidence": {},
                    }
                ),
                encoding="utf-8",
            )
            facts_path.write_text("", encoding="utf-8")
            with self.assertRaises(CoveringPreconditionError):
                run_gap_probe(signals_path, facts_path, root / "out")

    def test_gap_probe_cli_exit_3_on_missing_covering(self):
        """Deviation: gap_probe CLI exit 0 when covering missing."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            signals_path = root / "spring_signals.json"
            facts_path = root / "facts.jsonl"
            out = root / "gap"
            signals_path.write_text(
                json.dumps(
                    {
                        "schema_version": 7,
                        "scanner_version": "sv",
                        "file_signatures": {"a.java": "1"},
                        "entity_table_map": {},
                        "evidence": {},
                    }
                ),
                encoding="utf-8",
            )
            facts_path.write_text("", encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "doc_engine.tools.gap_probe",
                    "--signals",
                    str(signals_path),
                    "--facts",
                    str(facts_path),
                    "--out",
                    str(out),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(proc.returncode, 3)
        self.assertFalse((out / "gap_report.json").is_file())

    def test_gap_report_omits_r_recall_without_oracle_arm(self):
        """Deviation: R_recall present on filesystem+ast-grep-only covering."""
        sigs = {"a.java": "1"}
        root = inventory_root(sigs)
        proof = build_covering_proof(
            file_signatures=sigs,
            scanner_version="sv",
            receipts=[
                _complete_receipt("filesystem", root),
                _complete_receipt("ast-grep", root),
            ],
        )
        report, _ = build_gap_report(
            {
                "schema_version": 7,
                "scanner_version": "sv",
                "file_signatures": sigs,
                "entity_table_map": {},
                "evidence": {},
            },
            [],
            covering_proof=proof,
            covering_ok=True,
        )
        self.assertNotIn("R_recall", report["rates"])

    def test_gap_report_includes_r_recall_when_codeql_receipt(self):
        """Deviation: CodeQL arm present but R_recall section omitted."""
        sigs = {"a.java": "1"}
        root = inventory_root(sigs)
        proof = build_covering_proof(
            file_signatures=sigs,
            scanner_version="sv",
            receipts=[
                _complete_receipt("filesystem", root),
                _complete_receipt("ast-grep", root),
                _complete_receipt("codeql", root),
            ],
        )
        report, _ = build_gap_report(
            {
                "schema_version": 7,
                "scanner_version": "sv",
                "file_signatures": sigs,
                "entity_table_map": {},
                "evidence": {},
            },
            [],
            covering_proof=proof,
            covering_ok=True,
        )
        self.assertIn("R_recall", report["rates"])
        self.assertEqual(report["rates"]["R_recall"]["denominator"], 0)

    def test_measure_r_absence_ignores_non_callable_absence_rows(self):
        """Deviation: planted non-callable ABSENCE counted in S3 denominator."""
        # Writer must never emit this; scorer must still not inflate if it appears.
        facts = [
            {
                "predicate": "ABSENCE",
                "subject": "family:messaging",
                "qualifiers": {"trial": "callable", "family": "messaging"},
            },
            {
                "predicate": "ABSENCE",
                "subject": "family:redis",
                "qualifiers": {"trial": "non_callable", "family": "redis"},
            },
        ]
        # Current scorer counts all ABSENCE predicates; pin intended discipline:
        # only callable trials belong in the ABSENCE rate. If this fails, fix scorer.
        block = measure_r_absence(facts)
        callable_only = [
            f for f in facts if (f.get("qualifiers") or {}).get("trial") == "callable"
        ]
        self.assertEqual(block["callable_absence"], len(callable_only))
        # Prefer scorer that filters; if it currently counts both, this documents debt.
        if block["denominator"] != len(callable_only):
            self.fail(
                "measure_r_absence must use only trial=callable ABSENCE rows as "
                f"denominator (got den={block['denominator']}, want {len(callable_only)})"
            )


# ===========================================================================
# Black-box CLI smoke — fixture Stage 0
# ===========================================================================


class FixtureCliCoveringSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil_which("ast-grep"):
            raise unittest.SkipTest("ast-grep not on PATH")

    def test_cli_writes_covering_and_strips_internal_keys(self):
        """Deviation: CLI greens Path A without covering sibling or with internal keys."""
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            signals_out = out_dir / "spring_signals.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "doc_engine.tools.spring_signal_scan",
                    str(FIXTURE_DIR),
                    "--out",
                    str(signals_out),
                    "--scanners",
                    "filesystem,ast-grep",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            covering = out_dir / "covering_proof.json"
            facts = out_dir / "facts.jsonl"
            self.assertTrue(covering.is_file(), "covering_proof.json missing")
            self.assertTrue(facts.is_file(), "facts.jsonl missing")
            path_a = json.loads(signals_out.read_text(encoding="utf-8"))
            self.assertNotIn("_covering_proof", path_a)
            self.assertNotIn("_scan_partials_meta", path_a)
            proof = json.loads(covering.read_text(encoding="utf-8"))
            ok, why = verify_covering_proof(
                proof,
                file_signatures=path_a["file_signatures"],
                scanner_version=path_a["scanner_version"],
            )
            self.assertTrue(ok, why)
            self.assertIn("covering_emit", proc.stderr)
            fact_rows = [
                json.loads(line)
                for line in facts.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(
                any(r["predicate"] in {"ABSENCE", "UNPROVEN"} for r in fact_rows),
                "expected ABSENCE/UNPROVEN stamps in facts.jsonl",
            )

    def test_in_process_scan_attaches_covering_proof(self):
        """Deviation: in-process scan() returns Path A without covering attachment."""
        result = scan(str(FIXTURE_DIR), scanners=["filesystem", "ast-grep"])
        self.assertIn("_covering_proof", result)
        self.assertIn("_scan_partials_meta", result)
        ok, why = verify_covering_proof(
            result["_covering_proof"],
            file_signatures=result["file_signatures"],
            scanner_version=result["scanner_version"],
        )
        self.assertTrue(ok, why)
        # Dual-emit covering writers see the attachment.
        facts = facts_from_signals(result)
        self.assertTrue(any(f["predicate"] in {"ABSENCE", "UNPROVEN"} for f in facts))


def shutil_which(name: str):
    import shutil

    return shutil.which(name)


if __name__ == "__main__":
    unittest.main()
