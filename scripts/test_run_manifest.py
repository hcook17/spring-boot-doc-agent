#!/usr/bin/env python3
"""
Unit tests for run_manifest.py.

Pure-function tests (stage timing math, tag-count remapping, interview
parsing, commit-hash/dirty-flag graceful failure, the capacity_preflight
stage-key mapping) run against synthetic in-memory data or a monkeypatched
subprocess.run, using explicit --now-ms/now_ms injection instead of real
sleeps so nothing here is timing-flaky. A smaller set of CLI round-trip
tests drives the actual script via subprocess against a temp directory,
exercising init/start-stage/end-stage/finalize together, including the
retry case (a stage that failed and was restarted) and the partial-run
case (a stage never ended before finalize).

Reuses scripts/test_fixtures/spring_signals/ (the same fixture
test_spring_signal_scan.py, test_pipeline_stages.py, and
test_capacity_preflight.py already share) for the fresh-file-signature-scan
test, rather than building a second fixture tree.

Run with:
    python3 scripts/test_run_manifest.py -v
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DIR = os.path.join(SCRIPT_DIR, "test_fixtures", "spring_signals")
RUN_MANIFEST_PATH = os.path.join(SCRIPT_DIR, "run_manifest.py")
SCHEMA_PATH = os.path.join(SCRIPT_DIR, "run_manifest.schema.json")
sys.path.insert(0, SCRIPT_DIR)

import run_manifest  # noqa: E402
import spring_signal_scan  # noqa: E402

with open(SCHEMA_PATH, encoding="utf-8") as _f:
    _SCHEMA = json.load(_f)


def _fake_completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr=stderr)


def validate_manifest_shape(data):
    """Structural check against run_manifest.schema.json's documented shape —
    the equivalent of test_pipeline_stages.py's own structural validators,
    deliberately not a jsonschema-library-enforced check (no new dependency).
    Required-key sets are read from the schema file itself (via _SCHEMA)
    rather than restated here, so the two can't silently diverge. Returns a
    list of problem strings; empty means the shape is valid."""
    problems = []
    required_top = set(_SCHEMA["required"])
    missing = required_top - data.keys()
    if missing:
        problems.append(f"missing top-level keys: {sorted(missing)}")
        return problems

    if data["schema_version"] != 1:
        problems.append(f"schema_version {data['schema_version']!r} != 1")
    if data["status"] not in ("running", "complete", "failed", "partial"):
        problems.append(f"unrecognized top-level status {data['status']!r}")

    tr = data["target_repo"]
    required_target_repo = set(_SCHEMA["properties"]["target_repo"]["required"])
    for key in required_target_repo:
        if key not in tr:
            problems.append(f"target_repo missing key {key!r}")

    required_stage = set(_SCHEMA["properties"]["stages"]["items"]["required"])
    for i, stage in enumerate(data["stages"]):
        stage_missing = required_stage - stage.keys()
        if stage_missing:
            problems.append(f"stage[{i}] missing keys: {sorted(stage_missing)}")
            continue
        if stage["status"] not in run_manifest.STAGE_STATUSES:
            problems.append(f"stage[{i}] unrecognized status {stage['status']!r}")

    return problems


class AtomicWriteTest(unittest.TestCase):
    def test_write_and_read_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "run_manifest.json")
            run_manifest._write_json_atomic(path, {"a": 1})
            self.assertEqual(run_manifest._read_json(path), {"a": 1})
            # No leftover temp files after a successful write.
            leftovers = [f for f in os.listdir(d) if f != "run_manifest.json"]
            self.assertEqual(leftovers, [])

    def test_interrupted_write_leaves_prior_file_intact(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "run_manifest.json")
            run_manifest._write_json_atomic(path, {"version": 1})

            with mock.patch.object(run_manifest.os, "replace", side_effect=OSError("simulated interruption")):
                with self.assertRaises(OSError):
                    run_manifest._write_json_atomic(path, {"version": 2})

            # The prior valid file must survive an interrupted second write.
            self.assertEqual(run_manifest._read_json(path), {"version": 1})
            leftovers = [f for f in os.listdir(d) if f != "run_manifest.json"]
            self.assertEqual(leftovers, [], "the failed temp file should have been cleaned up")


class GitHelpersTest(unittest.TestCase):
    def test_commit_hash_success(self):
        with mock.patch.object(run_manifest.subprocess, "run",
                                return_value=_fake_completed(stdout="abc123\n")):
            self.assertEqual(run_manifest.git_commit_hash("/fake/repo"), "abc123")

    def test_commit_hash_git_not_on_path(self):
        with mock.patch.object(run_manifest.subprocess, "run", side_effect=FileNotFoundError("no git")):
            self.assertIsNone(run_manifest.git_commit_hash("/fake/repo"))

    def test_commit_hash_nonzero_returncode_not_a_repo(self):
        with mock.patch.object(run_manifest.subprocess, "run",
                                return_value=_fake_completed(returncode=128, stderr="not a git repository")):
            self.assertIsNone(run_manifest.git_commit_hash("/fake/repo"))

    def test_dirty_true_when_porcelain_nonempty(self):
        with mock.patch.object(run_manifest.subprocess, "run",
                                return_value=_fake_completed(stdout=" M some/file.java\n")):
            self.assertTrue(run_manifest.git_is_dirty("/fake/repo"))

    def test_dirty_false_when_porcelain_empty(self):
        with mock.patch.object(run_manifest.subprocess, "run", return_value=_fake_completed(stdout="")):
            self.assertFalse(run_manifest.git_is_dirty("/fake/repo"))

    def test_dirty_none_on_failure(self):
        with mock.patch.object(run_manifest.subprocess, "run", side_effect=FileNotFoundError("no git")):
            self.assertIsNone(run_manifest.git_is_dirty("/fake/repo"))


class InitManifestTest(unittest.TestCase):
    def test_shape_and_defaults(self):
        with mock.patch.object(run_manifest, "git_commit_hash", return_value="deadbeef"), \
             mock.patch.object(run_manifest, "git_is_dirty", return_value=False):
            manifest = run_manifest.build_init_manifest("/fake/repo", now_ms=1_700_000_000_000)
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["status"], "running")
        self.assertEqual(manifest["stages"], [])
        self.assertEqual(manifest["target_repo"]["commit_hash"], "deadbeef")
        self.assertFalse(manifest["target_repo"]["dirty"])
        self.assertTrue(manifest["run_id"].startswith("2023-11-14T22:13:20Z-"))
        self.assertEqual(validate_manifest_shape(manifest), [])


class StageLifecycleTest(unittest.TestCase):
    def _blank_manifest(self):
        return {"stages": []}

    def test_start_then_end_records_duration(self):
        m = self._blank_manifest()
        run_manifest.start_stage(m, "signal_scan", now_ms=1000)
        run_manifest.end_stage(m, "signal_scan", "complete", now_ms=1500)
        stage = m["stages"][0]
        self.assertEqual(stage["status"], "complete")
        self.assertEqual(stage["start_time_ms"], 1000)
        self.assertEqual(stage["end_time_ms"], 1500)
        self.assertEqual(stage["duration_ms"], 500)
        self.assertIsNone(stage["error"])

    def test_end_stage_records_error(self):
        m = self._blank_manifest()
        run_manifest.start_stage(m, "doc_writer", now_ms=0)
        run_manifest.end_stage(m, "doc_writer", "failed", error="subagent timeout", now_ms=10)
        self.assertEqual(m["stages"][0]["error"], "subagent timeout")

    def test_end_stage_unknown_name_raises(self):
        m = self._blank_manifest()
        with self.assertRaises(ValueError):
            run_manifest.end_stage(m, "nonexistent", "complete", now_ms=10)

    def test_end_stage_invalid_status_raises(self):
        m = self._blank_manifest()
        run_manifest.start_stage(m, "architect", now_ms=0)
        with self.assertRaises(ValueError):
            run_manifest.end_stage(m, "architect", "running", now_ms=10)

    def test_retry_case_resolves_in_append_order(self):
        # A stage that failed, then was retried: two start/end pairs for
        # the same name. end-stage must resolve each call against its own
        # immediately-preceding still-running entry, not an earlier,
        # already-ended one.
        m = self._blank_manifest()
        run_manifest.start_stage(m, "file_summarize", fanout=3, now_ms=0)
        run_manifest.end_stage(m, "file_summarize", "failed", error="ast-grep crashed", now_ms=100)
        run_manifest.start_stage(m, "file_summarize", fanout=3, now_ms=200)
        run_manifest.end_stage(m, "file_summarize", "complete", now_ms=400)

        self.assertEqual(len(m["stages"]), 2)
        first, second = m["stages"]
        self.assertEqual(first["status"], "failed")
        self.assertEqual(first["duration_ms"], 100)
        self.assertEqual(second["status"], "complete")
        self.assertEqual(second["start_time_ms"], 200)
        self.assertEqual(second["duration_ms"], 200)


class FinalizeStatusTest(unittest.TestCase):
    def _manifest_with_stages(self, *statuses):
        stages = []
        for i, status in enumerate(statuses):
            stages.append({
                "name": f"stage{i}", "status": status,
                "start_time_ms": 0, "end_time_ms": 100 if status != "running" else None,
                "duration_ms": 100 if status != "running" else None, "error": None, "actual_fanout": None,
            })
        return {"stages": stages, "timestamp_start": "2026-01-01T00:00:00Z"}

    def test_infer_complete_when_all_stages_complete(self):
        m = self._manifest_with_stages("complete", "complete")
        m, warnings = run_manifest.finalize_manifest(m, now_ms=1000)
        self.assertEqual(m["status"], "complete")
        self.assertEqual(warnings, [])

    def test_infer_failed_takes_priority(self):
        m = self._manifest_with_stages("complete", "failed", "canceled")
        m, _ = run_manifest.finalize_manifest(m, now_ms=1000)
        self.assertEqual(m["status"], "failed")

    def test_stage_left_running_is_auto_canceled_and_status_partial(self):
        m = self._manifest_with_stages("complete", "running")
        m, warnings = run_manifest.finalize_manifest(m, now_ms=1000)
        self.assertEqual(m["stages"][1]["status"], "canceled")
        self.assertIsNotNone(m["stages"][1]["error"])
        self.assertEqual(m["stages"][1]["end_time_ms"], 1000)
        self.assertEqual(m["status"], "partial")
        self.assertEqual(len(warnings), 1)

    def test_explicit_status_override_wins(self):
        m = self._manifest_with_stages("complete", "complete")
        m, _ = run_manifest.finalize_manifest(m, status="failed", now_ms=1000)
        self.assertEqual(m["status"], "failed")


class FileSignaturesTest(unittest.TestCase):
    def test_reuse_from_signals_file(self):
        fake_sigs = {"src/Foo.java": "sha256:abc"}
        with tempfile.TemporaryDirectory() as d:
            signals_path = os.path.join(d, "spring_signals.json")
            with open(signals_path, "w", encoding="utf-8") as f:
                json.dump({"file_signatures": fake_sigs}, f)
            result = run_manifest.load_file_signatures(signals_file=signals_path)
        self.assertEqual(result, fake_sigs)

    def test_fresh_scan_matches_spring_signal_scan_directly(self):
        result = run_manifest.load_file_signatures(repo_path=FIXTURE_DIR)
        self.assertIn("Invoice.java", result)
        expected = spring_signal_scan.compute_file_signature(os.path.join(FIXTURE_DIR, "Invoice.java"))
        self.assertEqual(result["Invoice.java"], expected)

    def test_no_signals_file_and_no_repo_path_returns_empty(self):
        self.assertEqual(run_manifest.load_file_signatures(), {})


class EvidenceTagCountsTest(unittest.TestCase):
    def test_counts_remapped_and_only_known_files_read(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "readme.md"), "w", encoding="utf-8") as f:
                f.write(
                    "Uses PostgreSQL [Evidenced — build.gradle]. "
                    "Deploy cadence is weekly [Confirmed — interview, 2026-07-23]. "
                    "Retry policy [Unknown — not evidenced in code, not covered in interview]."
                )
            # Not one of the fourteen — must be ignored.
            with open(os.path.join(d, "notes.md"), "w", encoding="utf-8") as f:
                f.write("[Evidenced — irrelevant.java:1]")

            result = run_manifest.compute_evidence_tag_counts(d)

        self.assertEqual(set(result.keys()), {"readme.md"})
        self.assertEqual(result["readme.md"], {"Evidenced": 1, "Confirmed": 1, "Unknown": 1, "PerExistingDocs": 0})


class InterviewParseTest(unittest.TestCase):
    def test_well_formed_list(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "interview_answers.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump([
                    {"id": "a", "question": "q1", "status": "answered", "answer": "x", "date": "2026-07-24"},
                    {"id": "b", "question": "q2", "status": "skipped", "answer": None, "date": "2026-07-24"},
                ], f)
            result = run_manifest.parse_interview_file(path)
        self.assertEqual(result, {
            "asked": 2, "answered": 1, "skipped": 1,
            "questions": [{"id": "a", "status": "answered"}, {"id": "b", "status": "skipped"}],
        })

    def test_missing_file_returns_zeros(self):
        result = run_manifest.parse_interview_file("/nonexistent/interview_answers.json")
        self.assertEqual(result, {"asked": 0, "answered": 0, "skipped": 0, "questions": []})

    def test_malformed_not_a_list_returns_zeros(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "interview_answers.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"not": "a list"}, f)
            result = run_manifest.parse_interview_file(path)
        self.assertEqual(result["asked"], 0)

    def test_entry_missing_required_keys_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "interview_answers.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump([{"id": "a", "status": "answered"}, {"question": "no id or status"}], f)
            result = run_manifest.parse_interview_file(path)
        self.assertEqual(result["asked"], 1)
        self.assertEqual(result["answered"], 1)


class CapacityPreflightTieInTest(unittest.TestCase):
    def test_all_six_real_keys_map_and_architect_sums(self):
        # Shaped exactly like capacity_preflight.py's own compute_preflight()
        # return value (confirmed via direct read of capacity_preflight.py).
        report = {
            "stage_fanout": {
                "stage1_file_summarizer": 3,
                "stage2_architect_segment": 3,
                "stage2_architect_merge": 1,
                "stage3_gap_analyzer": 1,
                "stage3_software_architect_and_testing": 1,
                "stage4_doc_writer": 14,
            },
            "total_fanout": 23,
        }
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "capacity_preflight_report.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report, f)
            result = run_manifest.compute_capacity_preflight_tie_in(path)

        self.assertEqual(result["total_predicted_fanout"], 23)
        self.assertEqual(result["unmapped_preflight_keys"], [])
        self.assertEqual(result["predicted_fanout_by_manifest_stage"], {
            "file_summarize": 3,
            "architect": 4,  # segment (3) + merge (1)
            "gap_analysis_interview": 1,
            "architecture_testing_review": 1,
            "doc_writer": 14,
        })

    def test_unknown_key_recorded_and_warns_not_silently_dropped(self):
        report = {"stage_fanout": {"stage5_future_stage": 7}, "total_fanout": 7}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "capacity_preflight_report.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report, f)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = run_manifest.compute_capacity_preflight_tie_in(path)

        self.assertEqual(result["unmapped_preflight_keys"], ["stage5_future_stage"])
        self.assertEqual(result["predicted_fanout_by_manifest_stage"], {})
        self.assertIn("stage5_future_stage", stderr.getvalue())
        self.assertIn("no known mapping", stderr.getvalue())


class CLIRoundTripTest(unittest.TestCase):
    """Drives the actual script as a subprocess, since this is the surface
    SKILL.md's orchestrating thread actually calls — a pure-function test
    alone wouldn't catch an argparse wiring mistake."""

    def _run(self, *args):
        result = subprocess.run(
            [sys.executable, RUN_MANIFEST_PATH, *args],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr}\nstdout: {result.stdout}")
        return result

    def test_full_lifecycle_via_cli(self):
        with tempfile.TemporaryDirectory() as d:
            manifest_path = os.path.join(d, "run_manifest.json")
            signals_path = os.path.join(d, "spring_signals.json")
            with open(signals_path, "w", encoding="utf-8") as f:
                json.dump({"file_signatures": {"Foo.java": "sha256:abc"}}, f)

            self._run("init", FIXTURE_DIR, "--out", manifest_path, "--now-ms", "1000")
            self._run("start-stage", manifest_path, "signal_scan", "--now-ms", "1000")
            self._run("end-stage", manifest_path, "signal_scan", "--status", "complete", "--now-ms", "1500")
            self._run("start-stage", manifest_path, "partition", "--now-ms", "1500")
            self._run("end-stage", manifest_path, "partition", "--status", "complete", "--now-ms", "1800")
            self._run("finalize", manifest_path, "--signals-file", signals_path, "--now-ms", "2000")

            manifest = run_manifest._read_json(manifest_path)

        self.assertEqual(validate_manifest_shape(manifest), [])
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(len(manifest["stages"]), 2)
        self.assertEqual(manifest["stages"][0]["duration_ms"], 500)
        self.assertEqual(manifest["stages"][1]["duration_ms"], 300)
        self.assertEqual(manifest["file_signatures"], {"Foo.java": "sha256:abc"})

    def test_retry_case_via_cli(self):
        with tempfile.TemporaryDirectory() as d:
            manifest_path = os.path.join(d, "run_manifest.json")
            self._run("init", FIXTURE_DIR, "--out", manifest_path, "--now-ms", "0")
            self._run("start-stage", manifest_path, "doc_writer", "--now-ms", "0")
            self._run("end-stage", manifest_path, "doc_writer", "--status", "failed", "--now-ms", "100")
            self._run("start-stage", manifest_path, "doc_writer", "--now-ms", "200")
            self._run("end-stage", manifest_path, "doc_writer", "--status", "complete", "--now-ms", "500")
            manifest = run_manifest._read_json(manifest_path)

        stages = [s for s in manifest["stages"] if s["name"] == "doc_writer"]
        self.assertEqual(len(stages), 2)
        self.assertEqual(stages[0]["status"], "failed")
        self.assertEqual(stages[1]["status"], "complete")

    def test_partial_run_via_cli(self):
        with tempfile.TemporaryDirectory() as d:
            manifest_path = os.path.join(d, "run_manifest.json")
            self._run("init", FIXTURE_DIR, "--out", manifest_path, "--now-ms", "0")
            self._run("start-stage", manifest_path, "architect", "--now-ms", "0")
            # Deliberately no end-stage call — simulates a crashed session.
            self._run("finalize", manifest_path, "--now-ms", "500")
            manifest = run_manifest._read_json(manifest_path)

        self.assertEqual(manifest["status"], "partial")
        self.assertEqual(manifest["stages"][0]["status"], "canceled")


if __name__ == "__main__":
    unittest.main()
