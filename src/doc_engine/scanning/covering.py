"""Content-addressed Stage-0 covering proof (S1 processing completeness).

Inventory SoR is ``file_signatures`` (rel → sha256). A successful scan requires
per-backend receipts whose ``acked_subset_root`` equals ``expected_subset_root``.
See claude/research/stage0-covering-absence-recall-2026-07-30.md.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

COVERING_PROOF_SCHEMA_VERSION = 1
COVERING_RECEIPT_KEY = "covering_receipt"


def inventory_root(file_signatures: Mapping[str, str]) -> str:
    """Hash of sorted ``path\\0sig\\n`` lines — single root over the walk SoR."""
    h = hashlib.sha256()
    for path in sorted(file_signatures):
        sig = file_signatures[path]
        h.update(path.encode("utf-8"))
        h.update(b"\0")
        h.update(str(sig).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def subset_root(file_signatures: Mapping[str, str], paths: Iterable[str]) -> str:
    """Hash of ``file_signatures`` restricted to ``paths`` (missing → empty sig)."""
    subset = {p: file_signatures[p] for p in sorted(set(paths)) if p in file_signatures}
    # Paths submitted that lack a signature still participate as empty sig so
    # acked vs expected diverge if the walk and argv disagree.
    for p in sorted(set(paths)):
        if p not in subset:
            subset[p] = ""
    return inventory_root(subset)


def java_scope_paths(file_signatures: Mapping[str, str]) -> List[str]:
    return sorted(p for p in file_signatures if p.endswith(".java"))


def build_receipt(
    *,
    scanner: str,
    version_hash: str,
    scope: str,
    expected_subset_root: str,
    acked_subset_root: str,
    status: str,
    covered_count: int = 0,
    batches: Optional[int] = None,
    winerror_206_bisects: int = 0,
    error: Optional[str] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    receipt: Dict[str, Any] = {
        "scanner": scanner,
        "version_hash": version_hash,
        "scope": scope,
        "expected_subset_root": expected_subset_root,
        "acked_subset_root": acked_subset_root,
        "status": status,
        "covered_count": covered_count,
        "winerror_206_bisects": winerror_206_bisects,
        "error": error,
    }
    if batches is not None:
        receipt["batches"] = batches
    if extra:
        receipt.update(dict(extra))
    return receipt


def build_covering_proof(
    *,
    file_signatures: Mapping[str, str],
    scanner_version: str,
    receipts: Sequence[Mapping[str, Any]],
    file_signature_algorithm: str = "sha256",
    respect_gitignore: bool = False,
) -> Dict[str, Any]:
    root = inventory_root(file_signatures)
    return {
        "schema_version": COVERING_PROOF_SCHEMA_VERSION,
        "inventory_root": root,
        "file_signature_algorithm": file_signature_algorithm,
        "scanner_version": scanner_version,
        "walk": {
            "respect_gitignore": respect_gitignore,
        },
        "barrier": {
            "kind": "batch_inventory_closed",
            "inventory_root": root,
        },
        "receipts": [dict(r) for r in receipts],
    }


def expected_subset_root_for_scope(
    file_signatures: Mapping[str, str],
    scope: str,
) -> str:
    """Recompute the subset root a receipt's ``scope`` claims to cover."""
    if scope == "all_signatures":
        return inventory_root(file_signatures)
    if scope == "java":
        return subset_root(file_signatures, java_scope_paths(file_signatures))
    raise ValueError(f"unknown covering receipt scope: {scope!r}")


def verify_covering_proof(
    proof: Mapping[str, Any],
    *,
    file_signatures: Mapping[str, str],
    scanner_version: str,
) -> Tuple[bool, str]:
    """Recompute inventory + per-receipt subset roots; fail closed on mismatch."""
    if int(proof.get("schema_version") or 0) != COVERING_PROOF_SCHEMA_VERSION:
        return False, f"unsupported covering_proof schema_version={proof.get('schema_version')}"
    expected_root = inventory_root(file_signatures)
    if proof.get("inventory_root") != expected_root:
        return False, "inventory_root does not match file_signatures"
    if proof.get("scanner_version") != scanner_version:
        return False, "scanner_version mismatch between proof and signals"
    barrier = proof.get("barrier") or {}
    if barrier.get("inventory_root") != expected_root:
        return False, "barrier.inventory_root mismatch"
    receipts = proof.get("receipts") or []
    if not receipts:
        return False, "covering_proof has no receipts"
    for receipt in receipts:
        status = receipt.get("status")
        if status == "failed":
            return False, (
                f"receipt failed for scanner={receipt.get('scanner')}: "
                f"{receipt.get('error')}"
            )
        if status != "complete":
            return False, f"receipt status not complete: {receipt.get('scanner')}={status}"
        scope = receipt.get("scope")
        if not isinstance(scope, str) or not scope:
            return False, (
                f"receipt missing scope for scanner={receipt.get('scanner')}"
            )
        try:
            recomputed = expected_subset_root_for_scope(file_signatures, scope)
        except ValueError as exc:
            return False, str(exc)
        expected = receipt.get("expected_subset_root")
        acked = receipt.get("acked_subset_root")
        if expected != recomputed:
            return False, (
                f"expected_subset_root does not match recomputed scope={scope!r} "
                f"for scanner={receipt.get('scanner')}"
            )
        if acked != recomputed:
            return False, (
                f"acked_subset_root does not match recomputed scope={scope!r} "
                f"for scanner={receipt.get('scanner')}"
            )
    return True, ""


def covering_proof_path_for_signals_out(out_path: Path) -> Path:
    return Path(out_path).resolve().parent / "covering_proof.json"


def write_covering_proof(path: Path, proof: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def pop_receipt(partial: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Remove and return ``covering_receipt`` from a scanner partial, if present."""
    return partial.pop(COVERING_RECEIPT_KEY, None)
