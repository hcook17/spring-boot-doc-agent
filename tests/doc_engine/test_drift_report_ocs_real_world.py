"""Opt-in L5 drift_report schema witness against a local real Spring checkout.

This file ships with the plugin (no proprietary content). The target checkout and
its Stage-0 outputs do NOT — keep them local-only.

Artifact lane (uses an existing spring_signals.json + live repo tree)::

    DRIFT_OCS_ARTIFACTS_DIR=local-runs/<artifact-dir> \\
    DRIFT_OCS_REPO=/path/to/local-spring-service \\
        pytest tests/doc_engine/test_drift_report_ocs_real_world.py -v

If DRIFT_OCS_REPO is unset, the test falls back to spring_signals.json's
repo_path when that directory still exists.

Live-scan lane (slow; fresh Stage 0 then drift against itself → all unchanged)::

    DRIFT_OCS_REPO=/path/to/local-spring-service \\
    DRIFT_OCS_LIVE_SCAN=1 \\
        pytest tests/doc_engine/test_drift_report_ocs_real_world.py -v -k live_scan

With env vars unset, every test is skipped (normal for CI / other machines).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from doc_engine.paths import repo_root
from doc_engine.pipeline.artifacts import DriftReportArtifact
from doc_engine.pipeline.validation import validate_artifact_data, validate_artifact_file
from doc_engine.tools import spring_drift_check

REPO_ROOT = repo_root()

ARTIFACTS_DIR = os.environ.get("DRIFT_OCS_ARTIFACTS_DIR")
OCS_REPO = os.environ.get("DRIFT_OCS_REPO")
LIVE_SCAN = os.environ.get("DRIFT_OCS_LIVE_SCAN", "").strip().lower() in {
    "1",
    "true",
    "yes",
}


def _resolve_artifacts_dir() -> Path | None:
    if not ARTIFACTS_DIR:
        return None
    p = Path(ARTIFACTS_DIR)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p


def _resolve_repo(signals: dict | None = None) -> Path | None:
    if OCS_REPO:
        return Path(OCS_REPO)
    if signals and signals.get("repo_path"):
        candidate = Path(signals["repo_path"])
        if candidate.is_dir():
            return candidate
    return None


@pytest.fixture(scope="module")
def ocs_signals_and_repo() -> tuple[dict, Path, Path]:
    root = _resolve_artifacts_dir()
    if root is None:
        pytest.skip(
            "DRIFT_OCS_ARTIFACTS_DIR not set — opt-in ocs drift schema lane skipped "
            "(see test_drift_report_ocs_real_world.py docstring)"
        )
    if not root.is_dir():
        pytest.skip(f"DRIFT_OCS_ARTIFACTS_DIR is not a directory: {root}")
    signals_path = root / "spring_signals.json"
    if not signals_path.is_file():
        pytest.skip(f"missing spring_signals.json under {root}")
    signals = json.loads(signals_path.read_text(encoding="utf-8"))
    if signals.get("schema_version", 1) < 2:
        pytest.skip(
            f"spring_signals.json schema_version={signals.get('schema_version')} "
            "< 2 (no file_signatures) — regenerate Stage 0"
        )
    repo = _resolve_repo(signals)
    if repo is None or not repo.is_dir():
        pytest.skip(
            "DRIFT_OCS_REPO not set and signals.repo_path is missing/absent — "
            "point DRIFT_OCS_REPO at a local Spring service checkout"
        )
    return signals, repo, signals_path


@pytest.fixture(scope="module")
def ocs_drift_report(ocs_signals_and_repo: tuple[dict, Path, Path]) -> dict:
    signals, repo, _signals_path = ocs_signals_and_repo
    return spring_drift_check.check_drift(str(repo), signals)


class TestOcsDriftReportSchema:
    """L5 bite: real ocs check_drift output must validate as DriftReportArtifact."""

    def test_writer_emits_schema_version(self, ocs_drift_report: dict) -> None:
        assert (
            ocs_drift_report["schema_version"]
            == spring_drift_check.DRIFT_REPORT_SCHEMA_VERSION
            == 1
        )

    def test_model_validate_round_trip(self, ocs_drift_report: dict) -> None:
        model = DriftReportArtifact.model_validate(ocs_drift_report)
        dumped = model.model_dump()
        assert dumped["schema_version"] == 1
        assert dumped["citations_checked"] == ocs_drift_report["citations_checked"]
        assert set(dumped["file_summary"]) >= {
            "unchanged",
            "changed",
            "deleted",
            "added",
        }
        # Real mid-size service must produce at least one citation outcome.
        assert dumped["citations_checked"] > 0
        assert len(dumped["results"]) == dumped["citations_checked"]

    def test_validate_artifact_data_and_file(
        self, ocs_drift_report: dict, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        validate_artifact_data("drift_report", ocs_drift_report)
        out = tmp_path_factory.mktemp("ocs-drift") / "drift_report.json"
        out.write_text(json.dumps(ocs_drift_report), encoding="utf-8")
        loaded = validate_artifact_file("drift_report", out)
        assert loaded.schema_version == 1

    def test_status_vocabulary_closed(self, ocs_drift_report: dict) -> None:
        allowed = {
            spring_drift_check.STATUS_UNCHANGED,
            spring_drift_check.STATUS_CONFIRMED,
            spring_drift_check.STATUS_DRIFTED,
            spring_drift_check.STATUS_FILE_DELETED,
            spring_drift_check.STATUS_NO_RULE_FALLBACK,
            spring_drift_check.STATUS_UNKNOWN_NO_SIGNATURE,
            spring_drift_check.STATUS_CONFIG_STRUCTURE_CHANGED,
            spring_drift_check.STATUS_CONFIG_VALUES_ONLY_CHANGED,
        }
        seen = {row["status"] for row in ocs_drift_report["results"]}
        assert seen <= allowed
        assert set(ocs_drift_report["status_counts"]) <= allowed


@pytest.mark.skipif(not LIVE_SCAN, reason="DRIFT_OCS_LIVE_SCAN not enabled")
class TestOcsLiveScanDriftSchema:
    """Fresh Stage 0 on ocs, then drift against that scan (identity → schema bite)."""

    def test_live_scan_then_self_drift(self, tmp_path: Path) -> None:
        if not OCS_REPO:
            pytest.skip("DRIFT_OCS_REPO not set")
        repo = Path(OCS_REPO)
        if not repo.is_dir():
            pytest.skip(f"DRIFT_OCS_REPO is not a directory: {repo}")

        out_signals = tmp_path / "spring_signals.json"
        cmd = [
            sys.executable,
            "-m",
            "doc_engine.tools.spring_signal_scan",
            str(repo),
            "--out",
            str(out_signals),
            "--scanners",
            "filesystem,ast-grep",
        ]
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"scan failed:\n{proc.stderr}\n{proc.stdout}"
        assert out_signals.is_file()

        signals = json.loads(out_signals.read_text(encoding="utf-8"))
        report = spring_drift_check.check_drift(str(repo), signals)
        DriftReportArtifact.model_validate(report)
        assert report["schema_version"] == 1
        assert report["citations_checked"] > 0
        # Identity drift: no file content change since the scan we just wrote.
        assert report["file_summary"]["changed"] == []
        assert report["file_summary"]["deleted"] == []
        assert set(report["status_counts"]) <= {
            spring_drift_check.STATUS_UNCHANGED,
        }
