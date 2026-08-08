"""R_absence / R_recall measures and covering-proof load/verify."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from doc_engine.scanning.covering import (
    covering_proof_path_for_signals_out,
    verify_covering_proof,
)

from .common import _load_json, _rate_block


def _fact_qualifiers(fact: Mapping[str, Any]) -> Mapping[str, Any]:
    qualifiers = fact.get("qualifiers")
    return qualifiers if isinstance(qualifiers, Mapping) else {}


def _callable_absence_failure(
    fact: Mapping[str, Any],
    *,
    qualifiers: Mapping[str, Any],
    trial: Any,
) -> Dict[str, Any]:
    return {
        "layer": "absence",
        "stratum": str(qualifiers.get("family") or fact.get("subject")),
        "reason_class": "ABSENCE",
        "subject": fact.get("subject"),
        "file": fact.get("file"),
        "trial": trial,
    }


def _tally_absence_and_unproven(
    facts: Sequence[Mapping[str, Any]],
) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Count callable ABSENCE failures and out-of-stratum UNPROVEN stamps."""
    absence_count = 0
    unproven_count = 0
    failures: List[Dict[str, Any]] = []
    for fact in facts:
        predicate = fact.get("predicate")
        if predicate == "ABSENCE":
            qualifiers = _fact_qualifiers(fact)
            trial = qualifiers.get("trial")
            if trial != "callable":
                continue
            absence_count += 1
            failures.append(
                _callable_absence_failure(fact, qualifiers=qualifiers, trial=trial)
            )
        elif predicate == "UNPROVEN":
            unproven_count += 1
    return absence_count, unproven_count, failures


def _absence_rate_block(
    absence_count: int,
    callable_trials: Optional[int],
) -> Dict[str, Any]:
    """Build the R_absence rate block using trials when supplied."""
    if callable_trials is not None:
        denominator = int(callable_trials)
        if denominator > 0:
            return _rate_block(absence_count, denominator)
        return _rate_block(0, 0)
    if absence_count:
        return _rate_block(absence_count, absence_count)
    return _rate_block(0, 0)


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
    absence_count, unproven_count, failures = _tally_absence_and_unproven(facts)
    block = _absence_rate_block(absence_count, callable_trials)
    block["callable_absence"] = absence_count
    block["callable_trials"] = callable_trials
    block["unproven"] = unproven_count
    block["polarity"] = "failure_mass"
    block["note"] = (
        "R_absence is failure mass |ABSENCE|/callable_trials (ideal 0). "
        "UNPROVEN is reported but excluded from the denominator."
    )
    block["failures"] = failures
    return block


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
    misses = [fact for fact in facts if fact.get("predicate") == "RECALL_MISS"]
    structural = 0
    evidentiary = 0
    failures: List[Dict[str, Any]] = []
    for fact in misses:
        qualifiers = _fact_qualifiers(fact)
        verdict = str(qualifiers.get("verdict") or "STRUCTURAL")
        if verdict == "EVIDENTIARY":
            evidentiary += 1
        else:
            structural += 1
        failures.append(
            {
                "layer": "recall",
                "stratum": verdict,
                "reason_class": "RECALL_MISS",
                "subject": fact.get("subject"),
                "file": fact.get("file"),
                "oracle_arm": qualifiers.get("oracle_arm"),
            }
        )
    denominator = len(misses)
    block = (
        _rate_block(structural, denominator) if denominator else _rate_block(0, 0)
    )
    block["structural"] = structural
    block["evidentiary"] = evidentiary
    block["oracle_arm_present"] = True
    block["failures"] = failures
    return block


def _complete_receipt_for_scanner(
    covering_proof: Optional[Mapping[str, Any]],
    *,
    scanner: str,
) -> bool:
    """True when a receipt for ``scanner`` is complete with matching subset roots."""
    for receipt in (covering_proof or {}).get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        if receipt.get("scanner") != scanner:
            continue
        if receipt.get("status") != "complete":
            continue
        expected_root = receipt.get("expected_subset_root")
        acked_root = receipt.get("acked_subset_root")
        if expected_root and acked_root and expected_root == acked_root:
            return True
    return False


def _trusted_codeql_oracle_arm(covering_proof: Optional[Mapping[str, Any]]) -> bool:
    """True only for a complete CodeQL receipt with matching subset roots."""
    return _complete_receipt_for_scanner(covering_proof, scanner="codeql")


def _astgrep_receipt_complete(covering_proof: Optional[Mapping[str, Any]]) -> bool:
    return _complete_receipt_for_scanner(covering_proof, scanner="ast-grep")


def _planted_recall_failures(
    facts: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Synthetic failures when RECALL_MISS exists without a trusted oracle arm."""
    rows: List[Dict[str, Any]] = []
    for fact in facts:
        if fact.get("predicate") != "RECALL_MISS":
            continue
        qualifiers = _fact_qualifiers(fact)
        rows.append(
            {
                "layer": "recall",
                "stratum": "untrusted_planted",
                "reason_class": "RECALL_MISS_WITHOUT_ORACLE",
                "subject": fact.get("subject"),
                "file": fact.get("file"),
                "oracle_arm": qualifiers.get("oracle_arm"),
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
    signatures = signals.get("file_signatures") or {}
    if not isinstance(signatures, Mapping):
        return dict(proof), False, "signals.file_signatures missing"
    scanner_version = signals.get("scanner_version")
    if not scanner_version:
        return dict(proof), False, "signals.scanner_version missing"
    verified, reason = verify_covering_proof(
        proof,
        file_signatures=signatures,
        scanner_version=str(scanner_version),
    )
    return dict(proof), verified, reason
