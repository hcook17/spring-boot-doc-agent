#!/usr/bin/env python3
"""Generic Stage 0 orchestrator with covering-proof barrier."""

import hashlib
from typing import Any, Dict, List

from doc_engine.core.context import ScanContext
from doc_engine.core.protocols import LineageResolver, Merger, Scanner
from doc_engine.scanning.covering import (
    build_covering_proof,
    pop_receipt,
    verify_covering_proof,
)


class CoveringProofError(RuntimeError):
    """Raised when Stage-0 covering receipts fail the inventory barrier."""


def _combined_scanner_version(scanners: List[Scanner]) -> str:
    """Hash the active scanner names and their individual version hashes."""
    h = hashlib.sha256()
    for scanner in scanners:
        h.update(f"{scanner.name}:{scanner.version_hash()}".encode())
    return h.hexdigest()[:16]


def _ensure_scan_context(repo_path: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    if kwargs.get("scan_context") is not None:
        return kwargs
    respect_gitignore = bool(kwargs.get("respect_gitignore", False))
    return {
        **kwargs,
        "scan_context": ScanContext.build(
            repo_path, respect_gitignore=respect_gitignore,
        ),
    }


def _require_complete_receipt(scanner: Scanner, partial: Dict[str, Any]) -> Dict[str, Any]:
    receipt = pop_receipt(partial)
    if receipt is None:
        raise CoveringProofError(
            f"scanner {scanner.name!r} did not emit a covering_receipt"
        )
    if receipt.get("status") != "complete":
        raise CoveringProofError(
            f"scanner {scanner.name!r} covering receipt failed: "
            f"{receipt.get('error')}"
        )
    return receipt


def _collect_partials(
    repo_path: str,
    scanners: List[Scanner],
    kwargs: Dict[str, Any],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    partials: List[Dict[str, Any]] = []
    receipts: List[Dict[str, Any]] = []
    for scanner in scanners:
        partial = scanner.scan(repo_path, **kwargs)
        receipts.append(_require_complete_receipt(scanner, partial))
        partials.append(partial)
    return partials, receipts


def _entity_keys_by_scanner(
    scanner_names: List[str],
    partials: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    return {
        name: sorted(
            set(partial.get("entity_table_map_candidates", {}) or {})
            | set(partial.get("entity_table_map", {}) or {})
        )
        for name, partial in zip(scanner_names, partials, strict=True)
    }


def _attach_covering_proof(
    resolved: Dict[str, Any],
    *,
    scan_context: ScanContext,
    scanner_version: str,
    receipts: List[Dict[str, Any]],
    kwargs: Dict[str, Any],
) -> None:
    proof = build_covering_proof(
        file_signatures=scan_context.file_signatures,
        scanner_version=scanner_version,
        receipts=receipts,
        respect_gitignore=bool(kwargs.get("respect_gitignore", False)),
    )
    ok, why = verify_covering_proof(
        proof,
        file_signatures=scan_context.file_signatures,
        scanner_version=scanner_version,
    )
    if not ok:
        raise CoveringProofError(why)
    resolved["_covering_proof"] = proof


def run_scan(
    repo_path: str,
    scanners: List[Scanner],
    merger: Merger,
    lineage_resolver: LineageResolver,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Run all scanners, merge, resolve lineage, attach covering proof."""
    kwargs = _ensure_scan_context(repo_path, kwargs)
    scan_context: ScanContext = kwargs["scan_context"]
    scanner_version = _combined_scanner_version(scanners)
    partials, receipts = _collect_partials(repo_path, scanners, kwargs)
    scanner_names = [scanner.name for scanner in scanners]
    merged = merger.merge(
        partials, repo_path, scanner_version, scanner_names=scanner_names,
    )
    resolved = lineage_resolver.resolve(merged, **kwargs)
    _attach_covering_proof(
        resolved,
        scan_context=scan_context,
        scanner_version=scanner_version,
        receipts=receipts,
        kwargs=kwargs,
    )
    resolved["_scan_partials_meta"] = {
        "scanner_names": scanner_names,
        "entity_keys_by_scanner": _entity_keys_by_scanner(scanner_names, partials),
    }
    return resolved
