"""Adversarial falsifiers across the deterministic Stage-0 → gates ETL.

Each test names the deviation. Happy-path portable / kitchen-sink suites can
stay green while these holes are live — this module exists to keep them red.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from doc_engine.paths import repo_root
from doc_engine.pipeline.artifacts import ARTIFACT_FILENAMES
from doc_engine.pipeline.stages import build_stage_specs
from doc_engine.pipeline.validation import (
    ArtifactValidationError,
    require_stage0_siblings,
    validate_artifacts_in_dir,
)
from doc_engine.real_fixture import require_real_repo
from doc_engine.tools import build_cross_group_edges, validate_artifacts
from doc_engine.tools import partition_repo
from tests.conftest import FIXTURE_DIR

REPO_ROOT = repo_root()


def _product_scan_tree() -> Path:
    """Real Spring tree for product-truth ETL scans (not the hermetic fixture)."""
    try:
        return require_real_repo()
    except FileNotFoundError as exc:
        pytest.skip(str(exc))


def _minimal_signals(**overrides) -> dict:
    base = {
        "schema_version": 7,
        "scanner_version": "etl-adv",
        "repo_path": str(FIXTURE_DIR),
        "files_scanned": {"java": 1, "yml": 0},
        "entity_table_map": {},
        "evidence": {"references": []},
        "file_signatures": {"A.java": "abc"},
    }
    base.update(overrides)
    return base


class TestValidateAllFailClosed:
    """Deviation: validate --all greened empty dirs / signals-only dumps."""

    def test_empty_dir_exits_nonzero(self, tmp_path: Path) -> None:
        code = validate_artifacts.main(["--all", str(tmp_path)])
        assert code == 1

    def test_signals_without_facts_sibling_fails(self, tmp_path: Path) -> None:
        (tmp_path / "spring_signals.json").write_text(
            json.dumps(_minimal_signals()), encoding="utf-8"
        )
        with pytest.raises(ArtifactValidationError) as ctx:
            require_stage0_siblings(tmp_path)
        assert "facts.jsonl" in str(ctx.value)

    def test_signals_without_covering_sibling_fails(self, tmp_path: Path) -> None:
        (tmp_path / "spring_signals.json").write_text(
            json.dumps(_minimal_signals()), encoding="utf-8"
        )
        (tmp_path / "facts.jsonl").write_text("{}\n", encoding="utf-8")
        with pytest.raises(ArtifactValidationError) as ctx:
            require_stage0_siblings(tmp_path)
        assert "covering_proof.json" in str(ctx.value)

    def test_complete_siblings_pass_require(self, tmp_path: Path) -> None:
        (tmp_path / "spring_signals.json").write_text(
            json.dumps(_minimal_signals()), encoding="utf-8"
        )
        (tmp_path / "facts.jsonl").write_text("{}\n", encoding="utf-8")
        (tmp_path / "covering_proof.json").write_text("{}", encoding="utf-8")
        require_stage0_siblings(tmp_path)  # does not raise

    def test_cli_all_rejects_signals_only(self, tmp_path: Path) -> None:
        (tmp_path / "spring_signals.json").write_text(
            json.dumps(_minimal_signals()), encoding="utf-8"
        )
        code = validate_artifacts.main(["--all", str(tmp_path)])
        assert code == 1


class TestStageSpecOutputsComplete:
    """Deviation: capacity/edges/covering absent from stage outputs → silent miss."""

    def test_signal_scan_requires_covering_and_facts(self) -> None:
        spec = next(s for s in build_stage_specs() if s.name == "signal_scan")
        assert "facts.jsonl" in spec.outputs
        assert "covering_proof.json" in spec.outputs
        assert ARTIFACT_FILENAMES["spring_signals"] in spec.outputs

    def test_capacity_requires_report_output(self) -> None:
        spec = next(s for s in build_stage_specs() if s.name == "capacity_preflight")
        assert "capacity_preflight_report.json" in spec.outputs

    def test_edges_output_is_registered_filename(self) -> None:
        spec = next(s for s in build_stage_specs() if s.name == "cross_group_edges")
        assert spec.outputs == (ARTIFACT_FILENAMES["cross_group_edges"],)

    def test_gap_probe_is_required_deterministic_stage(self) -> None:
        """Deviation: gap_probe lived as opt-in CLI; Path A certified without U."""
        names = [s.name for s in build_stage_specs()]
        assert "gap_probe" in names
        idx_scan = names.index("signal_scan")
        idx_gap = names.index("gap_probe")
        assert idx_gap == idx_scan + 1
        spec = next(s for s in build_stage_specs() if s.name == "gap_probe")
        assert "gap_report/gap_report.json" in spec.outputs


class TestPartitionAdversarial:
    """Deviation: partition could emit empty / inconsistent groups unnoticed."""

    def test_empty_repo_tree_produces_zero_groups_not_crash(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty"
        repo.mkdir()
        files = partition_repo.dfs_file_list(
            str(repo),
            partition_repo.DEFAULT_EXCLUDED_DIRS,
            partition_repo.DEFAULT_EXCLUDED_EXTS,
            partition_repo.DEFAULT_EXCLUDED_FILES,
        )
        assert files == []
        groups = partition_repo.build_groups([], max_tokens=2000, overlap_ratio=0.1)
        assert groups == []

    def test_single_oversized_file_still_emitted(self, tmp_path: Path) -> None:
        # One file larger than max_tokens must still form a group (atomic files).
        groups = partition_repo.build_groups(
            [("Huge.java", 50_000)], max_tokens=100, overlap_ratio=0.1
        )
        assert len(groups) == 1
        assert groups[0][0][0] == "Huge.java"


class TestCrossGroupEdgesAdversarial:
    """Deviation: empty refs / empty groups still write a report — must not look healthy."""

    def test_empty_groups_report_is_vacuous_not_healthy(self) -> None:
        report = build_cross_group_edges.build_report(
            {"schema_version": 1, "groups": []},
            {
                "schema_version": 7,
                "repo_path": str(FIXTURE_DIR),
                "evidence": {"references": []},
                "entity_table_map": {},
            },
        )
        assert report["num_groups"] == 0
        assert report["references_rows"] == 0
        # Vacuous: zero shipped rows — callers must not treat this as a successful join.
        assert report["stats"]["rows_shipped"] == 0
        assert report["stats"].get("reduction_factor") is None

    def test_groups_with_no_references_ship_zero_cut_arcs(self) -> None:
        report = build_cross_group_edges.build_report(
            {
                "schema_version": 1,
                "groups": [
                    {"id": 0, "files": ["a/A.java"], "est_tokens": 10},
                    {"id": 1, "files": ["b/B.java"], "est_tokens": 10},
                ],
            },
            {
                "schema_version": 7,
                "repo_path": str(FIXTURE_DIR),
                "evidence": {"references": []},
                "entity_table_map": {},
            },
        )
        assert report["num_groups"] == 2
        assert report["stats"].get("cut_arcs", 0) == 0


class TestCorruptFactsFailValidation:
    """Deviation: malformed facts.jsonl must not pass the facts boundary."""

    def test_invalid_jsonl_line_raises(self, tmp_path: Path) -> None:
        from doc_engine.pipeline.validation import validate_artifact_file

        path = tmp_path / "facts.jsonl"
        path.write_text("{not-json\n", encoding="utf-8")
        with pytest.raises(ArtifactValidationError):
            validate_artifact_file("facts", path)


class TestSignalsFileReuseRequiresSiblings:
    """Deviation: --signals-file copied Path A alone and skipped Stage-0 dual-emit."""

    def test_local_runner_materializes_siblings_when_reusing_signals(
        self, tmp_path: Path
    ) -> None:
        signals = tmp_path / "spring_signals.json"
        signals.write_text(json.dumps(_minimal_signals()), encoding="utf-8")
        out = tmp_path / "out"
        out.mkdir()
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "doc_engine.pipeline.local_runner",
                str(FIXTURE_DIR),
                "--out-dir",
                str(out),
                "--deterministic-only",
                "--signals-file",
                str(signals),
                "--skip-drift",
            ],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert (out / "facts.jsonl").is_file()
        assert (out / "covering_proof.json").is_file()
        combined = proc.stderr + proc.stdout
        run_log = out / "run.log"
        if run_log.is_file():
            combined += run_log.read_text(encoding="utf-8")
        assert "facts not found" not in combined

    def test_local_runner_rejects_signals_without_file_signatures(
        self, tmp_path: Path
    ) -> None:
        signals = tmp_path / "spring_signals.json"
        signals.write_text(
            json.dumps(_minimal_signals(file_signatures={})), encoding="utf-8"
        )
        out = tmp_path / "out"
        out.mkdir()
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "doc_engine.pipeline.local_runner",
                str(FIXTURE_DIR),
                "--out-dir",
                str(out),
                "--deterministic-only",
                "--signals-file",
                str(signals),
                "--skip-drift",
            ],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode != 0
        combined = proc.stderr + proc.stdout
        assert "Stage-0 siblings" in combined or "file_signatures" in combined


class TestRealRepoDeterministicEtlAdversarial:
    """Product-truth ETL against DOC_ENGINE_REAL_REPO / local-runs/real-repo.path.

    Hermetic FIXTURE_DIR is not a stand-in for mid-size Spring distributions —
    these scans must hit the operator's real tree.
    """

    def test_real_scan_then_validate_all(self, tmp_path: Path) -> None:
        repo = _product_scan_tree()
        out_signals = tmp_path / "spring_signals.json"
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "doc_engine.tools.spring_signal_scan",
                str(repo),
                "--out",
                str(out_signals),
                "--scanners",
                "filesystem,ast-grep",
            ],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            pytest.fail(f"real-repo scan failed:\n{proc.stderr}\n{proc.stdout}")
        assert (tmp_path / "facts.jsonl").is_file()
        assert (tmp_path / "covering_proof.json").is_file()
        require_stage0_siblings(tmp_path)
        gap = subprocess.run(
            [
                sys.executable,
                "-m",
                "doc_engine.tools.gap_probe",
                "--signals",
                str(out_signals),
                "--facts",
                str(tmp_path / "facts.jsonl"),
                "--covering",
                str(tmp_path / "covering_proof.json"),
                "--out",
                str(tmp_path / "gap_report"),
            ],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert gap.returncode == 0, gap.stderr
        assert (tmp_path / "gap_report" / "gap_report.json").is_file()
        from doc_engine.pipeline.validation import require_gap_probe_artifact

        require_gap_probe_artifact(tmp_path)
        code = validate_artifacts.main(["--all", str(tmp_path)])
        assert code == 0

    def test_validate_all_rejects_signals_without_gap_report(self, tmp_path: Path) -> None:
        """Deviation: Path A + siblings greened without gap_probe measurement."""
        repo = _product_scan_tree()
        out_signals = tmp_path / "spring_signals.json"
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "doc_engine.tools.spring_signal_scan",
                str(repo),
                "--out",
                str(out_signals),
                "--scanners",
                "filesystem,ast-grep",
            ],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            pytest.fail(f"real-repo scan failed:\n{proc.stderr}\n{proc.stdout}")
        require_stage0_siblings(tmp_path)
        code = validate_artifacts.main(["--all", str(tmp_path)])
        assert code == 1

    def test_planted_empty_gap_report_fails_validate_all(self, tmp_path: Path) -> None:
        """Deviation: existence-only gap_report greened planted {}."""
        repo = _product_scan_tree()
        out_signals = tmp_path / "spring_signals.json"
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "doc_engine.tools.spring_signal_scan",
                str(repo),
                "--out",
                str(out_signals),
                "--scanners",
                "filesystem,ast-grep",
            ],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            pytest.fail(f"real-repo scan failed:\n{proc.stderr}\n{proc.stdout}")
        gap_dir = tmp_path / "gap_report"
        gap_dir.mkdir()
        (gap_dir / "gap_report.json").write_text("{}", encoding="utf-8")
        code = validate_artifacts.main(["--all", str(tmp_path)])
        assert code == 1

    def test_planted_unverified_gap_report_fails_validate_all(self, tmp_path: Path) -> None:
        """Deviation: schema-valid but s1_covering.verified=false greened --all."""
        repo = _product_scan_tree()
        out_signals = tmp_path / "spring_signals.json"
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "doc_engine.tools.spring_signal_scan",
                str(repo),
                "--out",
                str(out_signals),
                "--scanners",
                "filesystem,ast-grep",
            ],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            pytest.fail(f"real-repo scan failed:\n{proc.stderr}\n{proc.stdout}")
        gap_dir = tmp_path / "gap_report"
        gap_dir.mkdir()
        (gap_dir / "gap_report.json").write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "s1_covering": {"verified": False, "proof_present": True},
                    "oracle": {
                        "arm_present": False,
                        "claim": "omitted_without_oracle",
                        "R_recall": None,
                    },
                    "rates": {
                        "R_recall": {
                            "claim": "omitted_without_oracle",
                            "numerator": None,
                            "denominator": None,
                            "rate": None,
                        }
                    },
                    "uncertainty": {"U": 0.0},
                }
            ),
            encoding="utf-8",
        )
        code = validate_artifacts.main(["--all", str(tmp_path)])
        assert code == 1

    def test_until_signal_scan_not_certified_even_with_planted_gap(self, tmp_path: Path) -> None:
        """Deviation: --until signal_scan + planted gap_report greened det cert."""
        repo = _product_scan_tree()
        out = tmp_path / "run"
        out.mkdir()
        gap_dir = out / "gap_report"
        gap_dir.mkdir()
        (gap_dir / "gap_report.json").write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "s1_covering": {"verified": True, "proof_present": True},
                    "oracle": {
                        "arm_present": False,
                        "claim": "omitted_without_oracle",
                        "R_recall": None,
                    },
                    "rates": {
                        "R_recall": {
                            "claim": "omitted_without_oracle",
                            "rate": None,
                        }
                    },
                    "uncertainty": {"U": 0.0},
                }
            ),
            encoding="utf-8",
        )
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "doc_engine.pipeline.local_runner",
                str(repo),
                "--out-dir",
                str(out),
                "--deterministic-only",
                "--until",
                "signal_scan",
                "--skip-drift",
            ],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        cert_path = out / "certification.json"
        assert cert_path.is_file(), proc.stderr + proc.stdout
        cert = json.loads(cert_path.read_text(encoding="utf-8"))
        assert cert["certified"] is False
        assert any("gap_probe" in f for f in cert["failures"])
        assert proc.returncode != 0

    def test_tampered_covering_fails_gap_probe(self, tmp_path: Path) -> None:
        from doc_engine.scanning.gap_probe import CoveringPreconditionError, run_gap_probe

        repo = _product_scan_tree()
        out_signals = tmp_path / "spring_signals.json"
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "doc_engine.tools.spring_signal_scan",
                str(repo),
                "--out",
                str(out_signals),
                "--scanners",
                "filesystem,ast-grep",
            ],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            pytest.fail(f"real-repo scan failed:\n{proc.stderr}\n{proc.stdout}")
        covering = tmp_path / "covering_proof.json"
        payload = json.loads(covering.read_text(encoding="utf-8"))
        payload["inventory_root"] = "deadbeef"
        covering.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(CoveringPreconditionError):
            run_gap_probe(
                out_signals,
                tmp_path / "facts.jsonl",
                tmp_path / "gap",
                covering_path=covering,
            )
