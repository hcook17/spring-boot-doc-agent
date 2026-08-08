"""Opt-in L5 drift_report schema witness against the canonical real Spring checkout.

Point ``DOC_ENGINE_REAL_REPO`` (or ``local-runs/real-repo.path``) at a local
Spring Boot tree. Never commit that path.

Artifact lane (existing spring_signals.json + live repo tree)::

    DOC_ENGINE_REAL_ARTIFACTS_DIR=local-runs/real-repo-latest \\
        pytest tests/doc_engine/test_drift_report_ocs_real_world.py -v

If the repo env/path file is unset, falls back to spring_signals.json's
``repo_path`` when that directory still exists.

Live-scan lane (slow; fresh Stage 0 then identity drift)::

    DOC_ENGINE_REAL_LIVE_SCAN=1 \\
        pytest tests/doc_engine/test_drift_report_ocs_real_world.py -v -k live_scan
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from doc_engine.paths import repo_root
from doc_engine.pipeline.artifacts import DriftReportArtifact
from doc_engine.pipeline.validation import validate_artifact_data, validate_artifact_file
from doc_engine.real_fixture import (
    live_scan_enabled,
    real_artifacts_dir,
    real_repo_path,
    require_real_repo,
)
from doc_engine.tools import spring_drift_check

REPO_ROOT = repo_root()


def _resolve_artifacts_dir() -> Path | None:
    root = real_artifacts_dir(prefer_default=False)
    if root is None:
        root = real_artifacts_dir(prefer_default=True)
    return root


def _resolve_repo(signals: dict | None = None) -> Path | None:
    configured = real_repo_path()
    if configured is not None and configured.is_dir():
        return configured
    if signals and signals.get("repo_path"):
        candidate = Path(signals["repo_path"])
        if candidate.is_dir():
            return candidate
    return None


@pytest.fixture(scope="module")
def ocs_signals_and_repo() -> tuple[dict, Path, Path]:
    root = _resolve_artifacts_dir()
    if root is None or not root.is_dir():
        pytest.skip(
            "DOC_ENGINE_REAL_ARTIFACTS_DIR unset / missing — opt-in drift artifact lane skipped "
            "(regen via scripts/ci/regen_real_repo_artifacts.py)"
        )
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
            "DOC_ENGINE_REAL_REPO unset and signals.repo_path is missing/absent — "
            "point the canonical real-repo lane at a local Spring checkout"
        )
    return signals, repo, signals_path


@pytest.fixture(scope="module")
def ocs_drift_report(ocs_signals_and_repo: tuple[dict, Path, Path]) -> dict:
    signals, repo, _signals_path = ocs_signals_and_repo
    return spring_drift_check.check_drift(str(repo), signals)


class TestOcsDriftReportSchema:
    """L5 bite: real check_drift output must validate as DriftReportArtifact."""

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
        assert dumped["citations_checked"] > 0
        assert len(dumped["results"]) == dumped["citations_checked"]

    def test_validate_artifact_data_and_file(
        self, ocs_drift_report: dict, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        validate_artifact_data("drift_report", ocs_drift_report)
        out = tmp_path_factory.mktemp("real-drift") / "drift_report.json"
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


@pytest.mark.skipif(not live_scan_enabled(), reason="DOC_ENGINE_REAL_LIVE_SCAN not enabled")
class TestOcsLiveScanDriftSchema:
    """Fresh Stage 0 on the real tree, then drift against that scan (identity)."""

    def test_live_scan_then_self_drift(self, tmp_path: Path) -> None:
        try:
            repo = require_real_repo()
        except FileNotFoundError as exc:
            pytest.skip(str(exc))

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
        assert report["file_summary"]["changed"] == []
        assert report["file_summary"]["deleted"] == []
        assert set(report["status_counts"]) <= {
            spring_drift_check.STATUS_UNCHANGED,
        }
