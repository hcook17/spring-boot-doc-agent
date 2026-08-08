"""Adversarial falsifiers for gap_probe / real-fixture assumptions.

Each test names the deviation it must catch. These exist because happy-path
real-repo asserts (R_sym==1, covering_ok=True bypass, vacuous baseline bands)
were green while the following holes were live.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

import pytest

from doc_engine.paths import repo_root
from doc_engine.real_fixture import real_artifacts_dir, real_repo_path
from doc_engine.scanning.covering import (
    build_covering_proof,
    build_receipt,
    inventory_root,
    verify_covering_proof,
)
from doc_engine.scanning.gap_probe import (
    CoveringPreconditionError,
    build_gap_report,
    measure_r_coll,
)
from doc_engine.scanning.symbol import format_type
from doc_engine.tools import spring_drift_check

REPO_ROOT = repo_root()
BASELINE = REPO_ROOT / "scripts" / "coverage" / "real_repo_gap_baseline.json"


def _minimal_signals(**overrides):
    base = {
        "schema_version": 7,
        "scanner_version": "adv",
        "entity_table_map": {
            "Order": {
                "file": "Order.java",
                "table": "orders",
                "package": "com.example",
                "fqcn": "com.example.Order",
            }
        },
        "evidence": {"raw_queries": [], "deployment": []},
        "file_signatures": {"Order.java": "abc"},
    }
    base.update(overrides)
    return base


def _maps_to_fact(package: str, name: str, table: str) -> dict:
    return {
        "predicate": "MAPS_TO",
        "subject": format_type(package, name),
        "object": table,
        "qualifiers": {
            "display_name": name,
            "fqcn": f"{package}.{name}",
            "symbol_kind": "type",
        },
        "file": f"{name}.java",
        "line": None,
        "rule_id": None,
        "scanner": None,
    }


class TestCoveringVerifiedLie:
    """Deviation: covering_ok=True with no proof still claimed s1.verified."""

    def test_covering_ok_without_proof_is_not_verified(self) -> None:
        report, _ = build_gap_report(
            _minimal_signals(),
            [_maps_to_fact("com.example", "Order", "orders")],
            covering_ok=True,
            covering_why="",
            covering_proof=None,
        )
        assert report["s1_covering"]["proof_present"] is False
        assert report["s1_covering"]["verified"] is False
        assert report["s1_covering"]["inventory_root"] is None

    def test_covering_ok_with_proof_is_verified(self) -> None:
        sigs = {"Order.java": "abc"}
        root = inventory_root(sigs)
        proof = build_covering_proof(
            file_signatures=sigs,
            scanner_version="adv",
            receipts=[
                build_receipt(
                    scanner="filesystem",
                    version_hash="v",
                    scope="all_signatures",
                    expected_subset_root=root,
                    acked_subset_root=root,
                    status="complete",
                )
            ],
        )
        report, _ = build_gap_report(
            _minimal_signals(file_signatures=sigs),
            [_maps_to_fact("com.example", "Order", "orders")],
            covering_ok=True,
            covering_proof=proof,
        )
        assert report["s1_covering"]["verified"] is True
        assert report["s1_covering"]["proof_present"] is True
        assert report["s1_covering"]["inventory_root"] == root

    def test_covering_ok_false_still_refuses(self) -> None:
        signals = _minimal_signals()
        with pytest.raises(CoveringPreconditionError):
            build_gap_report(
                signals,
                [],
                covering_ok=False,
                covering_why="adversarial",
            )


class TestJoinIncompleteEmptyDenom:
    """Deviation: wiping entity_table_map left join_incomplete=False (rate None)."""

    def test_empty_path_a_with_orphan_maps_to_reopens_join(self) -> None:
        signals = _minimal_signals(entity_table_map={})
        facts = [_maps_to_fact("com.example", "Order", "orders")]
        report, _ = build_gap_report(
            signals, facts, covering_ok=True, covering_why=""
        )
        assert report["rates"]["R_join"]["rate"] is None
        assert report["counts"]["maps_to"] == 1
        assert report["counts"]["entity_table_map"] == 0
        assert report["design_reopen"]["join_incomplete"] is True

    def test_path_a_with_zero_maps_to_reopens_join(self) -> None:
        report, _ = build_gap_report(
            _minimal_signals(), [], covering_ok=True, covering_why=""
        )
        assert report["counts"]["maps_to"] == 0
        assert report["counts"]["entity_table_map"] == 1
        assert report["design_reopen"]["join_incomplete"] is True

    def test_healthy_dual_emit_does_not_reopen_join(self) -> None:
        report, _ = build_gap_report(
            _minimal_signals(),
            [_maps_to_fact("com.example", "Order", "orders")],
            covering_ok=True,
            covering_why="",
        )
        assert report["rates"]["R_join"]["rate"] == 1.0
        assert report["design_reopen"]["join_incomplete"] is False


class TestBaselineBandsNotVacuous:
    """Deviation: R_lin∈[0,1] and U_max=1 accepted any measurement."""

    def test_lin_and_u_bands_are_strict(self) -> None:
        data = json.loads(BASELINE.read_text(encoding="utf-8"))
        bands = data["bands"]
        assert bands["R_lin_mean_min"] > 0.0
        assert bands["R_lin_mean_max"] < 1.0
        assert bands["U_max"] < 1.0
        # Measured external-dev-corpus point must sit inside the band.
        exp = data["expected"]
        assert bands["R_lin_mean_min"] <= exp["R_lin_mean"] <= bands["R_lin_mean_max"]
        assert exp["U"] <= bands["U_max"]


class TestContestedRaisesColl:
    """Deviation: identity_rates_healthy could ignore small R_coll if only >0 checks."""

    def test_single_contested_key_moves_r_coll_off_zero(self) -> None:
        signals = _minimal_signals(
            entity_table_map={
                "User": {
                    "file": "a/User.java",
                    "table": "a_user",
                    "status": "contested",
                    "fqcn": "com.example.a.User",
                    "package": "com.example.a",
                    "candidates": [
                        {
                            "file": "a/User.java",
                            "table": "a_user",
                            "package": "com.example.a",
                            "fqcn": "com.example.a.User",
                        },
                        {
                            "file": "b/User.java",
                            "table": "b_user",
                            "package": "com.example.b",
                            "fqcn": "com.example.b.User",
                        },
                    ],
                }
            }
        )
        block = measure_r_coll(signals)
        assert block["rate"] == 1.0
        report, _ = build_gap_report(signals, [], covering_ok=True, covering_why="")
        assert report["design_reopen"]["path_a_to_symbols"] is True


class TestForgedCoveringProof:
    """Deviation: mismatched acked_subset_root must not verify."""

    def test_forged_acked_root_fails_verify(self) -> None:
        sigs = {"a.java": "1", "b.java": "2"}
        root = inventory_root(sigs)
        proof = build_covering_proof(
            file_signatures=sigs,
            scanner_version="sv",
            receipts=[
                build_receipt(
                    scanner="filesystem",
                    version_hash="v",
                    scope="all_signatures",
                    expected_subset_root=root,
                    acked_subset_root="deadbeef",
                    status="complete",
                )
            ],
        )
        ok, why = verify_covering_proof(
            proof, file_signatures=sigs, scanner_version="sv"
        )
        assert ok is False
        assert "acked_subset_root" in why


def _real_artifacts_available() -> bool:
    root = real_artifacts_dir(prefer_default=False)
    if root is None:
        root = real_artifacts_dir(prefer_default=True)
    return bool(root and (root / "spring_signals.json").is_file())


def _real_artifacts_available() -> bool:
    root = real_artifacts_dir(prefer_default=False)
    if root is None:
        root = real_artifacts_dir(prefer_default=True)
    return bool(root and (root / "spring_signals.json").is_file())


@pytest.fixture(scope="module")
def real_artifacts_bundle() -> tuple[dict, list, Path]:
    root = real_artifacts_dir(prefer_default=False)
    if root is None:
        root = real_artifacts_dir(prefer_default=True)
    assert root is not None
    signals = json.loads((root / "spring_signals.json").read_text(encoding="utf-8"))
    facts = [
        json.loads(line)
        for line in (root / "facts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return signals, facts, root


@pytest.mark.skipif(
    not _real_artifacts_available(),
    reason="DOC_ENGINE_REAL_ARTIFACTS_DIR unset — opt-in adversarial real-repo lane",
)
class TestRealRepoAdversarial:
    """Opt-in attacks against a local mid-size Spring dump + checkout."""

    def test_artifact_lane_without_covering_must_not_claim_verified(
        self, real_artifacts_bundle: tuple[dict, list, Path]
    ) -> None:
        signals, facts, root = real_artifacts_bundle
        if (root / "covering_proof.json").is_file():
            pytest.skip("covering present — vacuous-verified attack N/A")
        report, _ = build_gap_report(
            signals, facts, covering_ok=True, covering_why=""
        )
        # Product honesty: even if a caller forces covering_ok, no proof ⇒ not verified.
        assert report["s1_covering"]["verified"] is False

    def test_empty_entity_map_reopens_on_real_facts(
        self, real_artifacts_bundle: tuple[dict, list, Path]
    ) -> None:
        signals, facts, _root = real_artifacts_bundle
        broken = dict(signals)
        broken["entity_table_map"] = {}
        report, _ = build_gap_report(
            broken, facts, covering_ok=True, covering_why=""
        )
        assert report["counts"]["maps_to"] > 0
        assert report["design_reopen"]["join_incomplete"] is True

    def test_mutated_signature_marks_file_changed(
        self, real_artifacts_bundle: tuple[dict, list, Path]
    ) -> None:
        signals, _facts, _root = real_artifacts_bundle
        repo = real_repo_path()
        if repo is None or not repo.is_dir():
            pytest.skip("DOC_ENGINE_REAL_REPO unset")
        mutated = json.loads(json.dumps(signals))
        sigs = dict(mutated.get("file_signatures") or {})
        java = [k for k in sigs if k.endswith(".java")]
        if not java:
            pytest.skip("no java signatures")
        target = java[0]
        sigs[target] = "adversarial-deadbeef"
        mutated["file_signatures"] = sigs
        report = spring_drift_check.check_drift(str(repo), mutated)
        assert target in report["file_summary"]["changed"]

    def test_wrong_repo_tree_is_not_identity_drift(
        self, real_artifacts_bundle: tuple[dict, list, Path]
    ) -> None:
        signals, _facts, _root = real_artifacts_bundle
        # Point drift at *this* plugin repo — almost every cited path should vanish.
        wrong = REPO_ROOT
        report = spring_drift_check.check_drift(str(wrong), signals)
        deleted = report["file_summary"]["deleted"]
        assert len(deleted) > 100, (
            f"wrong-tree attack expected mass deletions, got {len(deleted)}"
        )
        # Must not look like a healthy identity drift (status_counts ⊆ {unchanged}).
        assert set(report["status_counts"]) - {"unchanged"}


class TestRealWorldFixtureMustRequireCovering:
    """Deviation: real-world AET fixture forced covering_ok=True with no proof."""

    def test_ocs_report_fixture_refuses_missing_covering(self, tmp_path: Path) -> None:
        """Simulate artifact dir without covering — fixture helper must skip/fail closed."""
        from tests.doc_engine import test_gap_probe_ocs_real_world as mod

        art = tmp_path / "arts"
        art.mkdir()
        (art / "spring_signals.json").write_text(
            json.dumps(_minimal_signals()), encoding="utf-8"
        )
        (art / "facts.jsonl").write_text("{}\n", encoding="utf-8")
        with mock.patch.dict(
            os.environ,
            {"DOC_ENGINE_REAL_ARTIFACTS_DIR": str(art)},
            clear=False,
        ):
            # Re-import resolution path: call the fixture logic indirectly.
            root = mod._resolve_artifacts_dir()
            assert root == art
            covering = art / "covering_proof.json"
            assert not covering.is_file()
            # The module's ocs_report path must not silently covering_ok=True forever:
            # after the fix, callers should use run_gap_probe / require covering.
            # Enforce the contract the real-world module documents.
            assert hasattr(mod, "REQUIRE_COVERING_PROOF")
            assert mod.REQUIRE_COVERING_PROOF is True
