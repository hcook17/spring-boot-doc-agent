"""Opt-in AET / gap_probe validation against the canonical real Spring checkout.

Point ``DOC_ENGINE_REAL_REPO`` (or ``local-runs/real-repo.path``) at a local
Spring Boot tree. Never commit that path.

Artifact lane (fast; uses existing signals + facts)::

    DOC_ENGINE_REAL_ARTIFACTS_DIR=local-runs/real-repo-latest \\
        pytest tests/doc_engine/test_gap_probe_ocs_real_world.py -v

Live-scan lane (slow; re-runs Stage 0)::

    DOC_ENGINE_REAL_LIVE_SCAN=1 \\
        pytest tests/doc_engine/test_gap_probe_ocs_real_world.py -v -k live_scan

With the real repo / artifacts unset, every test is skipped (normal for CI).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from doc_engine.paths import repo_root
from doc_engine.real_fixture import (
    live_scan_enabled,
    real_artifacts_dir,
    real_repo_path,
    require_real_repo,
)
from doc_engine.scanning.gap_probe import (
    GAP_PROBE_SCHEMA_VERSION,
    build_gap_report,
    run_gap_probe,
)

REPO_ROOT = repo_root()

# Artifact-lane AET must not green covering_ok=True without a proof on disk.
REQUIRE_COVERING_PROOF = True


def _resolve_artifacts_dir() -> Path | None:
    return real_artifacts_dir(prefer_default=False)


@pytest.fixture(scope="module")
def ocs_artifacts() -> tuple[Path, Path]:
    root = _resolve_artifacts_dir()
    if root is None:
        root = real_artifacts_dir(prefer_default=True)
    if root is None or not root.is_dir():
        pytest.skip(
            "DOC_ENGINE_REAL_ARTIFACTS_DIR unset / missing — opt-in artifact lane skipped "
            "(regen via scripts/ci/regen_real_repo_artifacts.py)"
        )
    signals = root / "spring_signals.json"
    facts = root / "facts.jsonl"
    covering = root / "covering_proof.json"
    if not signals.is_file():
        pytest.skip(f"missing spring_signals.json under {root}")
    if not facts.is_file():
        pytest.skip(f"missing facts.jsonl under {root}")
    if REQUIRE_COVERING_PROOF and not covering.is_file():
        pytest.skip(
            f"missing covering_proof.json under {root} — regenerate Stage 0 "
            "(REQUIRE_COVERING_PROOF=True; covering_ok=True without proof is forbidden)"
        )
    return signals, facts


@pytest.fixture(scope="module")
def ocs_report(ocs_artifacts: tuple[Path, Path]) -> dict:
    signals_path, facts_path = ocs_artifacts
    signals = json.loads(signals_path.read_text(encoding="utf-8"))
    facts = [
        json.loads(line)
        for line in facts_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    covering_path = signals_path.parent / "covering_proof.json"
    covering_proof = json.loads(covering_path.read_text(encoding="utf-8"))
    report, _failures = build_gap_report(
        signals,
        facts,
        signals_path=str(signals_path),
        facts_path=str(facts_path),
        covering_ok=True,
        covering_why="",
        covering_proof=covering_proof,
    )
    return report


class TestOcsArtifactsAet:
    """AET bite against precomputed real-repo Stage-0 outputs."""

    def test_schema_v3(self, ocs_report: dict) -> None:
        assert ocs_report["schema_version"] == GAP_PROBE_SCHEMA_VERSION == 3
        assert "measurement" in ocs_report
        assert ocs_report["measurement"]["truncation"]["slot"] == "truncation_loss"
        assert ocs_report["uncertainty"]["slot"] == "comparison_index"

    def test_identity_rates_healthy(self, ocs_report: dict) -> None:
        rates = ocs_report["rates"]
        assert rates["R_sym"]["rate"] == 1.0
        assert rates["R_coll"]["rate"] == 0.0
        assert rates["R_join"]["rate"] == 1.0
        assert rates["R_sym"]["callable_denominator"] == rates["R_sym"]["denominator"]
        assert ocs_report["counts"]["maps_to"] == ocs_report["counts"]["entity_table_map"]
        assert ocs_report["counts"]["maps_to"] > 0

    def test_path_a_rekey_not_reopened(self, ocs_report: dict) -> None:
        reopen = ocs_report["design_reopen"]
        assert reopen["path_a_to_symbols"] is False
        assert reopen["join_incomplete"] is False

    def test_lineage_residual_dialect_dominant(self, ocs_report: dict) -> None:
        lin = ocs_report["rates"]["R_lin"]
        assert lin["scoring_env"] == "callable"
        assert lin["denominator"] > 0
        assert lin["mean_rate"] is not None
        assert 0.0 <= lin["mean_rate"] <= 1.0
        dominant = ocs_report["design_reopen"]["lineage_dominant_stratum"]
        assert dominant is not None
        assert dominant["reason_class"] == "dialect_or_syntax"
        assert dominant["count"] > 0

    def test_scoring_env_delta_moves_lineage_only(self, ocs_report: dict) -> None:
        delta = ocs_report["measurement"]["delta_r_scoring_env"]
        assert delta["R_sym"] == 0.0
        assert delta["R_coll"] == 0.0
        assert delta["R_join"] == 0.0
        assert delta["R_lin_denominator_pooled"] >= delta["R_lin_denominator_callable"]
        if delta["R_lin_denominator_pooled"] > delta["R_lin_denominator_callable"]:
            assert delta["R_lin_mean"] is not None

    def test_cli_writes_report(self, ocs_artifacts: tuple[Path, Path], tmp_path: Path) -> None:
        signals_path, facts_path = ocs_artifacts
        covering = signals_path.parent / "covering_proof.json"
        if not covering.is_file():
            pytest.skip("covering_proof.json missing beside artifacts (re-scan required)")
        out = tmp_path / "gap_report"
        report = run_gap_probe(
            signals_path, facts_path, out, failure_budget=50, covering_path=covering,
        )
        assert (out / "gap_report.json").is_file()
        assert (out / "gap_failures.jsonl").is_file()
        assert report["measurement"]["truncation"]["failures_kept"] <= 50
        assert report["measurement"]["truncation"]["failures_total"] >= report["measurement"]["truncation"][
            "failures_kept"
        ]


@pytest.mark.skipif(not live_scan_enabled(), reason="DOC_ENGINE_REAL_LIVE_SCAN not enabled")
class TestOcsLiveScanAet:
    """Re-scan the canonical real Spring checkout then run gap_probe (slow)."""

    def test_live_scan_then_gap_probe(self, tmp_path: Path) -> None:
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
        facts_path = tmp_path / "facts.jsonl"
        covering = tmp_path / "covering_proof.json"
        assert out_signals.is_file()
        assert facts_path.is_file()
        assert covering.is_file()

        gap_out = tmp_path / "gap"
        report = run_gap_probe(
            out_signals, facts_path, gap_out, covering_path=covering,
        )
        assert report["schema_version"] == GAP_PROBE_SCHEMA_VERSION
        assert report["s1_covering"]["verified"] is True
        assert report["rates"]["R_sym"]["rate"] == 1.0
        assert report["rates"]["R_coll"]["rate"] == 0.0
        assert report["counts"]["maps_to"] > 0
