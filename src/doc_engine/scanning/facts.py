"""Project spring_signals.json into a thin dual-emit fact ledger (facts.jsonl).

Phase 1 sidecar: does not replace entity_table_map or evidence bags.
See claude/research/fact-store-phase1-decision-memo-2026-07-30.md §3.

L3: MAPS_TO subjects are SCIP-inspired type symbols (see scanning.symbol);
Path A entity_table_map keys remain simple class names.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional

from doc_engine.scanning.symbol import SymbolError, format_type, fqcn_of, parse

PathLike = str | Path


def facts_path_for_signals_out(out_path: PathLike) -> Path:
    """Return sibling ``facts.jsonl`` next to a spring_signals ``--out`` path."""
    return Path(out_path).resolve().parent / "facts.jsonl"


def _default_scanner(signals: Mapping[str, Any]) -> Optional[str]:
    scanners = signals.get("scanners") or []
    if not scanners:
        return None
    return ",".join(str(scanner) for scanner in scanners)


def _fact(
    *,
    predicate: str,
    subject: str,
    object_: Optional[str] = None,
    qualifiers: Optional[MutableMapping[str, Any]] = None,
    file: Optional[str] = None,
    line: Optional[int] = None,
    rule_id: Optional[str] = None,
    scanner: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "predicate": predicate,
        "subject": subject,
        "object": object_,
        "qualifiers": dict(qualifiers) if qualifiers else {},
        "file": file,
        "line": line,
        "rule_id": rule_id,
        "scanner": scanner,
    }


def _sort_key(fact: Mapping[str, Any]) -> tuple:
    line = fact.get("line")
    return (
        str(fact.get("predicate") or ""),
        str(fact.get("subject") or ""),
        str(fact.get("object") or ""),
        str(fact.get("file") or ""),
        -1 if line is None else int(line),
    )


def _type_symbol_quals(
    class_name: str,
    source: Mapping[str, Any],
    *,
    base_quals: Optional[MutableMapping[str, Any]] = None,
) -> tuple[str, Dict[str, Any]]:
    """Build type symbol subject + display/fqcn qualifiers from a map entry or candidate."""
    package = source.get("package")
    package_s = str(package) if package is not None else None
    fqcn = source.get("fqcn")
    if fqcn is None:
        fqcn = fqcn_of(package_s, class_name)
    else:
        fqcn = str(fqcn)
    subject = format_type(package_s, class_name)
    quals: Dict[str, Any] = dict(base_quals) if base_quals else {}
    quals["display_name"] = class_name
    quals["fqcn"] = fqcn
    quals["symbol_kind"] = "type"
    return subject, quals


def _maps_to_fact_from_source(
    class_name: str,
    source: Mapping[str, Any],
    *,
    base_quals: Dict[str, Any],
    default_scanner: Optional[str],
    fallback_rule_id: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build one MAPS_TO fact from a contested candidate or settled map entry."""
    subject, quals = _type_symbol_quals(str(class_name), source, base_quals=base_quals)
    return _fact(
        predicate="MAPS_TO",
        subject=subject,
        object_=None if source.get("table") is None else str(source.get("table")),
        qualifiers=quals,
        file=None if source.get("file") is None else str(source.get("file")),
        line=source.get("line") if isinstance(source.get("line"), int) else None,
        rule_id=source.get("rule_id") or fallback_rule_id,
        scanner=source.get("scanner") or default_scanner,
    )


def _contested_table_name_source(
    candidate: Mapping[str, Any],
    entry: Mapping[str, Any],
) -> Any:
    if candidate.get("table_name_source") is not None:
        return candidate.get("table_name_source")
    return entry.get("table_name_source")


def _maps_to_from_contested_entry(
    class_name: str,
    entry: Mapping[str, Any],
    candidates: list,
    default_scanner: Optional[str],
) -> List[Dict[str, Any]]:
    """One MAPS_TO per contested table candidate."""
    facts: List[Dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        quals: Dict[str, Any] = {"status": "contested"}
        table_name_source = _contested_table_name_source(candidate, entry)
        if table_name_source is not None:
            quals["table_name_source"] = table_name_source
        facts.append(
            _maps_to_fact_from_source(
                class_name,
                candidate,
                base_quals=quals,
                default_scanner=default_scanner,
                fallback_rule_id=entry.get("rule_id"),
            )
        )
    return facts


def _maps_to_from_settled_entry(
    class_name: str,
    entry: Mapping[str, Any],
    default_scanner: Optional[str],
) -> Dict[str, Any]:
    """One MAPS_TO for a non-contested entity_table_map entry."""
    quals: Dict[str, Any] = {}
    if entry.get("status") is not None:
        quals["status"] = entry.get("status")
    if entry.get("table_name_source") is not None:
        quals["table_name_source"] = entry.get("table_name_source")
    return _maps_to_fact_from_source(
        class_name,
        entry,
        base_quals=quals,
        default_scanner=default_scanner,
    )


def _is_contested_entry(entry: Mapping[str, Any]) -> bool:
    candidates = entry.get("candidates")
    return entry.get("status") == "contested" and isinstance(candidates, list) and bool(candidates)


def _maps_to_from_one_entry(
    class_name: str,
    entry: Any,
    default_scanner: Optional[str],
) -> List[Dict[str, Any]]:
    if not isinstance(entry, Mapping):
        return []
    if _is_contested_entry(entry):
        return _maps_to_from_contested_entry(
            class_name, entry, entry.get("candidates"), default_scanner,
        )
    return [_maps_to_from_settled_entry(class_name, entry, default_scanner)]


def _maps_to_from_entity_table_map(
    entity_table_map: Mapping[str, Any],
    default_scanner: Optional[str],
) -> List[Dict[str, Any]]:
    """Derived stub: contested entries become one MAPS_TO per candidate.

    Each MAPS_TO subject is a type-level claim-symbol (distinct across packages).
    """
    facts: List[Dict[str, Any]] = []
    for class_name, entry in entity_table_map.items():
        facts.extend(_maps_to_from_one_entry(class_name, entry, default_scanner))
    return facts


def _evidence_hit_fact(
    hit: Mapping[str, Any],
    *,
    bucket: Any,
    default_scanner: Optional[str],
) -> Optional[Dict[str, Any]]:
    file_path = hit.get("file")
    if file_path is None:
        return None
    rule_id = hit.get("rule_id")
    match = hit.get("match")
    return _fact(
        predicate=str(rule_id) if rule_id else "EVIDENCE",
        subject=str(file_path),
        object_=None if match is None else str(match),
        qualifiers={"bucket": bucket} if bucket else {},
        file=str(file_path),
        line=hit.get("line") if isinstance(hit.get("line"), int) else None,
        rule_id=None if rule_id is None else str(rule_id),
        scanner=hit.get("scanner") or default_scanner,
    )


def _append_evidence_hit(
    facts: List[Dict[str, Any]],
    hit: Any,
    *,
    bucket: Any,
    default_scanner: Optional[str],
) -> None:
    if not isinstance(hit, Mapping):
        return
    fact = _evidence_hit_fact(hit, bucket=bucket, default_scanner=default_scanner)
    if fact is not None:
        facts.append(fact)


def _facts_from_bucket(
    bucket: Any,
    hits: Any,
    default_scanner: Optional[str],
) -> List[Dict[str, Any]]:
    if not isinstance(hits, list):
        return []
    facts: List[Dict[str, Any]] = []
    for hit in hits:
        _append_evidence_hit(
            facts, hit, bucket=bucket, default_scanner=default_scanner,
        )
    return facts


def _facts_from_evidence(
    evidence: Mapping[str, Any],
    default_scanner: Optional[str],
) -> List[Dict[str, Any]]:
    facts: List[Dict[str, Any]] = []
    for bucket, hits in evidence.items():
        facts.extend(_facts_from_bucket(bucket, hits, default_scanner))
    return facts


def _astgrep_receipt_complete(proof: Mapping[str, Any]) -> bool:
    for receipt in proof.get("receipts") or []:
        if (
            isinstance(receipt, Mapping)
            and receipt.get("scanner") == "ast-grep"
            and receipt.get("status") == "complete"
        ):
            return True
    return False


def _covering_state(signals: Mapping[str, Any]) -> tuple[bool, Optional[str], bool]:
    """Return (covering_ok, covering_root, astgrep_receipt_complete)."""
    from doc_engine.scanning.covering import verify_covering_proof

    proof = signals.get("_covering_proof")
    if not isinstance(proof, Mapping):
        return False, None, False
    covering_root = proof.get("inventory_root")
    scanner_version = signals.get("scanner_version")
    sigs = signals.get("file_signatures") or {}
    covering_ok = False
    if isinstance(sigs, Mapping) and scanner_version:
        covering_ok, _ = verify_covering_proof(
            proof,
            file_signatures=sigs,
            scanner_version=str(scanner_version),
        )
    return (
        covering_ok,
        covering_root if isinstance(covering_root, str) else None,
        _astgrep_receipt_complete(proof),
    )


def _first_oracle_arm(
    entity_keys: Mapping[str, Any],
) -> Optional[tuple[str, set[str]]]:
    for arm in ("codeql", "multipass", "metamodel"):
        oracle = set(entity_keys.get(arm) or [])
        if oracle:
            return arm, oracle
    return None


def _recall_facts_from_meta(
    signals: Mapping[str, Any],
    meta: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    from doc_engine.scanning.recall_delta import write_recall_miss_facts

    entity_keys = meta.get("entity_keys_by_scanner") or {}
    if not isinstance(entity_keys, Mapping):
        return []
    selected = _first_oracle_arm(entity_keys)
    if selected is None:
        return []
    arm, oracle = selected
    return write_recall_miss_facts(
        signals,
        native_entity_keys=set(entity_keys.get("ast-grep") or []),
        oracle_entity_keys=oracle,
        oracle_arm=arm,
    )


def covering_writer_facts(signals: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """ABSENCE/UNPROVEN + RECALL_MISS from covering proof + per-arm entity keys.

    Internal keys ``_covering_proof`` / ``_scan_partials_meta`` are consumed when
    present (orchestrator). Without a proof, absence stamps are all UNPROVEN and
    recall is omitted.
    """
    from doc_engine.scanning.absence import write_absence_facts

    covering_ok, covering_root, astgrep_ok = _covering_state(signals)
    scanner_version = signals.get("scanner_version")
    facts = write_absence_facts(
        signals,
        covering_ok=covering_ok,
        covering_root=covering_root,
        scanner_version=str(scanner_version) if scanner_version else None,
        astgrep_receipt_complete=astgrep_ok,
    )
    meta = signals.get("_scan_partials_meta") or {}
    if isinstance(meta, Mapping):
        facts.extend(_recall_facts_from_meta(signals, meta))
    return facts


def facts_from_signals(signals: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Project a spring_signals dict into sorted fact records."""
    default_scanner = _default_scanner(signals)
    facts: List[Dict[str, Any]] = []
    evidence = signals.get("evidence") or {}
    if isinstance(evidence, Mapping):
        facts.extend(_facts_from_evidence(evidence, default_scanner))
    entity_table_map = signals.get("entity_table_map") or {}
    if isinstance(entity_table_map, Mapping):
        facts.extend(_maps_to_from_entity_table_map(entity_table_map, default_scanner))
    facts.extend(covering_writer_facts(signals))
    facts.sort(key=_sort_key)
    return facts


def _require_maps_to_type_symbol(fact: Mapping[str, Any]) -> None:
    if fact.get("predicate") != "MAPS_TO":
        return
    subject = fact.get("subject")
    try:
        parsed = parse(str(subject))
    except SymbolError as exc:
        raise SymbolError(
            f"MAPS_TO subject is not a claim-symbol: {subject!r}"
        ) from exc
    if parsed.kind != "type":
        raise SymbolError(
            f"MAPS_TO subject must be a type symbol, got kind={parsed.kind!r}: {subject!r}"
        )


def write_facts_jsonl(path: PathLike, facts: List[Mapping[str, Any]]) -> None:
    """Write fact records as UTF-8 JSON Lines (one object per line).

    Each row is validated against the closed ``Fact`` contract before encode
    (write-time bite; see schema-contracts-decision-memo-2026-07-30 slice 1).

    ``MAPS_TO`` subjects must parse as claim-symbols (grammar memo); bare
    simple names / FQCNs are rejected so illegal identity cannot land on disk.
    """
    from doc_engine.pipeline.artifacts import Fact

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for fact in facts:
            _require_maps_to_type_symbol(fact)
            validated = Fact.model_validate(dict(fact)).model_dump()
            fh.write(json.dumps(validated, ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def _bump_maps_to_count(counts: Dict[str, int], fact: Mapping[str, Any]) -> None:
    counts["facts_maps_to"] += 1
    quals = fact.get("qualifiers") or {}
    if isinstance(quals, Mapping) and quals.get("status") == "contested":
        counts["facts_maps_to_contested"] += 1


_EMIT_COUNT_KEYS = {
    "ABSENCE": "facts_absence",
    "UNPROVEN": "facts_unproven",
    "RECALL_MISS": "facts_recall_miss",
}


def _bump_emit_count(counts: Dict[str, int], fact: Mapping[str, Any]) -> None:
    predicate = fact.get("predicate")
    if predicate == "MAPS_TO":
        _bump_maps_to_count(counts, fact)
        return
    key = _EMIT_COUNT_KEYS.get(str(predicate) if predicate is not None else "")
    if key is None:
        counts["facts_evidence"] += 1
        return
    counts[key] += 1


def fact_emit_counts(facts: List[Mapping[str, Any]]) -> Dict[str, int]:
    """Return counters for dual-emit observability (gap/error analysis)."""
    counts = {
        "facts_total": len(facts),
        "facts_maps_to": 0,
        "facts_maps_to_contested": 0,
        "facts_evidence": 0,
        "facts_absence": 0,
        "facts_unproven": 0,
        "facts_recall_miss": 0,
    }
    for fact in facts:
        _bump_emit_count(counts, fact)
    return counts
