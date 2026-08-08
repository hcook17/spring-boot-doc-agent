"""R_absence / R_recall measures and covering-proof load/verify."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from doc_engine.scanning.covering import (
    covering_proof_path_for_signals_out,
    verify_covering_proof,
)

from .common import _load_json, _rate_block


def measure_r_absence(
    facts: Sequence[Mapping[str, Any]],
    *,
    callable_trials: Optional[int] = None,
) -> Dict[str, Any]:
    """ABSENCE failure mass over callable trials; UNPROVEN is out-of-stratum.

    ``rate`` = |ABSENCE| / callable_trials when ``callable_trials`` is supplied
    (failure mass; ideal 0). Without ``callable_trials``, dens fall back to
    |ABSENCE| only for back-compat unit calls — prefer always passing trials.
    """
    absence = 0
    unproven = 0
    failures: List[Dict[str, Any]] = []
    for f in facts:
        pred = f.get("predicate")
        quals = f.get("qualifiers") if isinstance(f.get("qualifiers"), Mapping) else {}
        trial = quals.get("trial")
        if pred == "ABSENCE":
            if trial != "callable":
                continue
            absence += 1
            failures.append(
                {
                    "layer": "absence",
                    "stratum": str(quals.get("family") or f.get("subject")),
                    "reason_class": "ABSENCE",
                    "subject": f.get("subject"),
                    "file": f.get("file"),
                    "trial": trial,
                }
            )
        elif pred == "UNPROVEN":
            unproven += 1
    if callable_trials is not None:
        den = int(callable_trials)
        out = _rate_block(absence, den) if den > 0 else _rate_block(0, 0)
    else:
        den = absence
        out = _rate_block(absence, den) if den else _rate_block(0, 0)
    out["callable_absence"] = absence
    out["callable_trials"] = callable_trials
    out["unproven"] = unproven
    out["polarity"] = "failure_mass"
    out["note"] = (
        "R_absence is failure mass |ABSENCE|/callable_trials (ideal 0). "
        "UNPROVEN is reported but excluded from the denominator."
    )
    out["failures"] = failures
    return out


def measure_r_recall(
    facts: Sequence[Mapping[str, Any]],
    *,
    oracle_arm_present: bool = False,
) -> Optional[Dict[str, Any]]:
    """RECALL_MISS rates when trusted oracle arm present; else None.

    Planted RECALL_MISS without an oracle arm must not invent measured recall —
    callers stamp ``untrusted_planted``.
    """
    if not oracle_arm_present:
        return None
    misses = [f for f in facts if f.get("predicate") == "RECALL_MISS"]
    structural = 0
    evidentiary = 0
    failures: List[Dict[str, Any]] = []
    for f in misses:
        quals = f.get("qualifiers") if isinstance(f.get("qualifiers"), Mapping) else {}
        verdict = str(quals.get("verdict") or "STRUCTURAL")
        if verdict == "EVIDENTIARY":
            evidentiary += 1
        else:
            structural += 1
        failures.append(
            {
                "layer": "recall",
                "stratum": verdict,
                "reason_class": "RECALL_MISS",
                "subject": f.get("subject"),
                "file": f.get("file"),
                "oracle_arm": quals.get("oracle_arm"),
            }
        )
    den = len(misses)
    out = _rate_block(structural, den) if den else _rate_block(0, 0)
    out["structural"] = structural
    out["evidentiary"] = evidentiary
    out["oracle_arm_present"] = True
    out["failures"] = failures
    return out


def _trusted_codeql_oracle_arm(covering_proof: Optional[Mapping[str, Any]]) -> bool:
    """True only for a complete CodeQL receipt with matching subset roots."""
    for receipt in (covering_proof or {}).get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        if receipt.get("scanner") != "codeql":
            continue
        if receipt.get("status") != "complete":
            continue
        expected = receipt.get("expected_subset_root")
        acked = receipt.get("acked_subset_root")
        if expected and acked and expected == acked:
            return True
    return False


def _astgrep_receipt_complete(covering_proof: Optional[Mapping[str, Any]]) -> bool:
    for receipt in (covering_proof or {}).get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        if receipt.get("scanner") != "ast-grep":
            continue
        if receipt.get("status") != "complete":
            continue
        expected = receipt.get("expected_subset_root")
        acked = receipt.get("acked_subset_root")
        if expected and acked and expected == acked:
            return True
    return False


def _planted_recall_failures(
    facts: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Synthetic failures when RECALL_MISS exists without a trusted oracle arm."""
    rows: List[Dict[str, Any]] = []
    for fact in facts:
        if fact.get("predicate") != "RECALL_MISS":
            continue
        quals = fact.get("qualifiers") if isinstance(fact.get("qualifiers"), Mapping) else {}
        rows.append(
            {
                "layer": "recall",
                "stratum": "untrusted_planted",
                "reason_class": "RECALL_MISS_WITHOUT_ORACLE",
                "subject": fact.get("subject"),
                "file": fact.get("file"),
                "oracle_arm": quals.get("oracle_arm"),
            }
        )
    return rows


def load_and_verify_covering(
    signals: Mapping[str, Any],
    *,
    signals_path: Optional[Path] = None,
    covering_path: Optional[Path] = None,
) -> Tuple[Dict[str, Any], bool, str]:
    """Load covering_proof sibling and verify against signals inventory."""
    path = covering_path
    if path is None and signals_path is not None:
        path = covering_proof_path_for_signals_out(signals_path)
    if path is None or not path.is_file():
        return {}, False, f"covering_proof.json missing (expected {path})"
    proof = _load_json(path)
    if not isinstance(proof, Mapping):
        return {}, False, "covering_proof root must be a JSON object"
    sigs = signals.get("file_signatures") or {}
    if not isinstance(sigs, Mapping):
        return dict(proof), False, "signals.file_signatures missing"
    scanner_version = signals.get("scanner_version")
    if not scanner_version:
        return dict(proof), False, "signals.scanner_version missing"
    ok, why = verify_covering_proof(
        proof,
        file_signatures=sigs,
        scanner_version=str(scanner_version),
    )
    return dict(proof), ok, why
