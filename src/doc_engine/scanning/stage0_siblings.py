"""Materialize Stage-0 sidecars when reusing a Path A ``spring_signals.json``.

Skipping ``signal_scan`` (``--signals-file``) still leaves ``gap_probe`` in the
stage graph. That stage needs ``facts.jsonl`` and ``covering_proof.json`` next
to the reused signals — copy siblings when present, otherwise project facts
from signals and synthesize a filesystem covering receipt over ``file_signatures``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Mapping

from doc_engine.scanning.covering import (
    build_covering_proof,
    build_receipt,
    inventory_root,
    write_covering_proof,
)
from doc_engine.scanning.facts import facts_from_signals, write_facts_jsonl

PathLike = str | Path


class Stage0SiblingError(ValueError):
    """Raised when reused signals cannot produce Stage-0 sidecars."""


def materialize_stage0_siblings(signals_path: PathLike, out_dir: PathLike) -> None:
    """Write ``facts.jsonl`` and ``covering_proof.json`` under ``out_dir``.

    Preference order for each artifact:
    1. Copy a sibling file next to ``signals_path`` when present.
    2. Else derive from the signals payload (facts projection / covering
       receipt over ``file_signatures``).
    """
    signals_path = Path(signals_path).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not signals_path.is_file():
        raise Stage0SiblingError(f"signals not found: {signals_path}")

    signals = json.loads(signals_path.read_text(encoding="utf-8"))
    if not isinstance(signals, Mapping):
        raise Stage0SiblingError("signals root must be a JSON object")

    src_dir = signals_path.parent
    facts_dst = out_dir / "facts.jsonl"
    covering_dst = out_dir / "covering_proof.json"

    src_facts = src_dir / "facts.jsonl"
    if src_facts.is_file():
        shutil.copy2(src_facts, facts_dst)
    else:
        write_facts_jsonl(facts_dst, facts_from_signals(signals))

    src_covering = src_dir / "covering_proof.json"
    if src_covering.is_file():
        shutil.copy2(src_covering, covering_dst)
        return

    sigs = signals.get("file_signatures") or {}
    if not isinstance(sigs, Mapping) or not sigs:
        raise Stage0SiblingError(
            "cannot synthesize covering_proof: signals.file_signatures missing"
        )
    root = inventory_root(sigs)
    scanner_version = str(signals.get("scanner_version") or "reused-signals")
    proof = build_covering_proof(
        file_signatures=sigs,
        scanner_version=scanner_version,
        receipts=[
            build_receipt(
                scanner="filesystem",
                version_hash="reused-signals-file",
                scope="all_signatures",
                expected_subset_root=root,
                acked_subset_root=root,
                status="complete",
                covered_count=len(sigs),
            )
        ],
    )
    write_covering_proof(covering_dst, proof)
