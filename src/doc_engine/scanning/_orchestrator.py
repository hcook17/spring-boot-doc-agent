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


def run_scan(
    repo_path: str,
    scanners: List[Scanner],
    merger: Merger,
    lineage_resolver: LineageResolver,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Run all scanners, merge, resolve lineage, attach covering proof."""
    if kwargs.get("scan_context") is None:
        respect_gitignore = bool(kwargs.get("respect_gitignore", False))
        kwargs = {
            **kwargs,
            "scan_context": ScanContext.build(repo_path, respect_gitignore=respect_gitignore),
        }

    scan_context: ScanContext = kwargs["scan_context"]
    scanner_version = _combined_scanner_version(scanners)

    partials = []
    receipts = []
    for scanner in scanners:
        partial = scanner.scan(repo_path, **kwargs)
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
        receipts.append(receipt)
        partials.append(partial)

    scanner_names = [s.name for s in scanners]
    merged = merger.merge(partials, repo_path, scanner_version, scanner_names=scanner_names)
    resolved = lineage_resolver.resolve(merged, **kwargs)

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
    resolved["_scan_partials_meta"] = {
        "scanner_names": scanner_names,
        "entity_keys_by_scanner": {
            name: sorted(
                set(p.get("entity_table_map_candidates", {}) or {})
                | set(p.get("entity_table_map", {}) or {})
            )
            for name, p in zip(scanner_names, partials, strict=True)
        },
    }
    return resolved
