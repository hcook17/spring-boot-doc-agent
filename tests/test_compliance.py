#!/usr/bin/env python3
"""Tests for compliance profiles and certification.json."""

import json
import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from pydantic import ValidationError

from doc_engine.config.loader import load_repo_config
from doc_engine.config.settings import Settings
from doc_engine.pipeline.compliance import (
    CERTIFIED_GATE_IDS,
    SCAN_ONLY_GATE_ID,
    ComplianceProfile,
    GateRecord,
    StageRecord,
    build_certification_report,
    gates_required_for_profile,
    resolve_compliance_profile,
    stages_for_profile,
    write_certification_json,
)
from doc_engine.pipeline.stages import build_stage_specs
from tests.conftest import FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH


class ResolveProfileTest(unittest.TestCase):
    def test_default_is_certified(self):
        args = Namespace(compliance_profile=None, deterministic_only=False)
        self.assertEqual(resolve_compliance_profile(None, args), ComplianceProfile.CERTIFIED)

    def test_deterministic_only_flag(self):
        args = Namespace(compliance_profile=None, deterministic_only=True)
        self.assertEqual(
            resolve_compliance_profile(None, args),
            ComplianceProfile.DETERMINISTIC_ONLY,
        )

    def test_explicit_cli_beats_yaml(self):
        config = Settings(compliance_profile=ComplianceProfile.SCAN_ONLY)
        args = Namespace(
            compliance_profile="certified",
            deterministic_only=False,
        )
        self.assertEqual(resolve_compliance_profile(config, args), ComplianceProfile.CERTIFIED)

    def test_explicit_cli_beats_deterministic_only(self):
        config = Settings(compliance_profile=ComplianceProfile.SCAN_ONLY)
        args = Namespace(
            compliance_profile="certified",
            deterministic_only=True,
        )
        self.assertEqual(resolve_compliance_profile(config, args), ComplianceProfile.CERTIFIED)

    def test_yaml_used_when_no_cli_override(self):
        config = Settings(compliance_profile=ComplianceProfile.DETERMINISTIC_ONLY)
        args = Namespace(compliance_profile=None, deterministic_only=False)
        self.assertEqual(
            resolve_compliance_profile(config, args),
            ComplianceProfile.DETERMINISTIC_ONLY,
        )


class LoadConfigTest(unittest.TestCase):
    def test_yaml_round_trip_compliance_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = os.path.join(tmp, ".doc-engine.yml")
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write("compliance_profile: scan_only\n")
            cfg = load_repo_config(tmp)
            self.assertIsNotNone(cfg)
            self.assertEqual(cfg.compliance_profile, ComplianceProfile.SCAN_ONLY)

    def test_invalid_profile_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = os.path.join(tmp, ".doc-engine.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump({"compliance_profile": "not_a_profile"}, f)
            with self.assertRaises(ValidationError):
                load_repo_config(tmp)


class StagesForProfileTest(unittest.TestCase):
    def test_scan_only_stage_names(self):
        specs = stages_for_profile(ComplianceProfile.SCAN_ONLY, build_stage_specs())
        names = {s.name for s in specs}
        self.assertEqual(names, {"init_manifest", "signal_scan"})

    def test_deterministic_only_excludes_generative(self):
        specs = stages_for_profile(ComplianceProfile.DETERMINISTIC_ONLY, build_stage_specs())
        self.assertTrue(all(s.kind.name == "DETERMINISTIC" for s in specs))
        self.assertGreater(len(specs), 2)

    def test_certified_includes_generative(self):
        specs = stages_for_profile(ComplianceProfile.CERTIFIED, build_stage_specs())
        kinds = {s.kind.name for s in specs}
        self.assertIn("DETERMINISTIC", kinds)
        self.assertIn("GENERATIVE", kinds)

    def test_skip_signal_scan(self):
        specs = stages_for_profile(
            ComplianceProfile.SCAN_ONLY,
            build_stage_specs(),
            skip_signal_scan=True,
        )
        self.assertEqual([s.name for s in specs], ["init_manifest"])


class GatesRequiredForProfileTest(unittest.TestCase):
    def test_scan_only_gate_id(self):
        self.assertEqual(
            gates_required_for_profile(ComplianceProfile.SCAN_ONLY),
            frozenset({SCAN_ONLY_GATE_ID}),
        )

    def test_certified_gate_ids(self):
        self.assertEqual(
            gates_required_for_profile(ComplianceProfile.CERTIFIED),
            CERTIFIED_GATE_IDS,
        )


class CertificationReportTest(unittest.TestCase):
    def test_all_ok_certified_true(self):
        report = build_certification_report(
            ComplianceProfile.CERTIFIED,
            "/repo",
            "/out",
            [StageRecord(name="signal_scan", status="ok")],
            [GateRecord(id="validate_artifacts_all", label="gate", status="ok")],
            generative_executor="mock",
        )
        self.assertTrue(report.certified)
        self.assertEqual(report.failures, [])
        self.assertEqual(report.profile_gate_ids, sorted(CERTIFIED_GATE_IDS))

    def test_failed_gate_certified_false(self):
        report = build_certification_report(
            ComplianceProfile.CERTIFIED,
            "/repo",
            "/out",
            [StageRecord(name="signal_scan", status="ok")],
            [GateRecord(id="citation_coverage", label="gate", status="fail")],
        )
        self.assertFalse(report.certified)
        self.assertIn("gate:citation_coverage:fail", report.failures)

    def test_failed_stage_certified_false(self):
        report = build_certification_report(
            ComplianceProfile.SCAN_ONLY,
            "/repo",
            "/out",
            [StageRecord(name="signal_scan", status="fail", detail="exit 1")],
            [],
        )
        self.assertFalse(report.certified)
        self.assertIn("stage:signal_scan:fail", report.failures)

    def test_write_certification_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = build_certification_report(
                ComplianceProfile.SCAN_ONLY,
                "/repo",
                tmp,
                [],
                [],
            )
            path = write_certification_json(tmp, report)
            self.assertTrue(path.is_file())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["schema_version"], 1)
            self.assertEqual(data["compliance_profile"], "scan_only")

    def test_failed_stage_with_empty_gates_not_certified(self):
        """Vacuously empty gate list must not imply certified when a stage failed."""
        report = build_certification_report(
            ComplianceProfile.CERTIFIED,
            "/repo",
            "/out",
            [StageRecord(name="doc_writer", status="fail", detail="mock raised")],
            [],
            generative_executor="mock",
        )
        self.assertFalse(report.certified)
        self.assertIn("stage:doc_writer:fail", report.failures)


class FinishMessagingTest(unittest.TestCase):
    def test_success_lines_only_when_certified(self):
        from doc_engine.pipeline.local_runner import Log, Runner, _write_certification_and_finish

        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, "run.log")
            log = Log(log_path)
            runner = Runner(log, keep_going=False)
            runner.record("pipeline:doc_writer", "FAIL", 0.0, "mock failed")
            code = _write_certification_and_finish(
                log,
                runner,
                ComplianceProfile.CERTIFIED,
                "/repo",
                tmp,
                "mock",
                show_table=False,
                success_lines=["RESULT: every gate passed."],
            )
            transcript = Path(log_path).read_text(encoding="utf-8")
            self.assertEqual(code, 1)
            self.assertNotIn("every gate passed", transcript)
            self.assertIn("certification failed", transcript)


class ScanOnlyIntegrationTest(unittest.TestCase):
    def test_scan_only_with_signals_file_writes_certification(self):
        from doc_engine.pipeline.local_runner import run_pipeline

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "run")
            args = Namespace(
                repo_path=str(FIXTURE_DIR),
                out_dir=out_dir,
                max_tokens=120000,
                docs_in_target_repo=False,
                prior_signals=None,
                skip_drift=True,
                respect_gitignore=False,
                strict_citations=False,
                keep_going=False,
                compliance_profile="scan_only",
                deterministic_only=False,
                signals_file=str(FIXTURE_SNAPSHOT_PATH),
            )
            code = run_pipeline(args)
            cert_path = os.path.join(out_dir, "certification.json")
            self.assertTrue(os.path.isfile(cert_path))
            with open(cert_path, encoding="utf-8") as f:
                cert = json.load(f)
            self.assertEqual(cert["compliance_profile"], "scan_only")
            self.assertTrue(cert["certified"])
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
