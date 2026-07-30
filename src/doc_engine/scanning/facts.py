"""Project spring_signals.json into a thin dual-emit fact ledger (facts.jsonl).

Phase 1 sidecar: does not replace entity_table_map or evidence bags.
See claude/research/fact-store-phase1-decision-memo-2026-07-30.md §3.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional

PathLike = str | Path


def facts_path_for_signals_out(out_path: PathLike) -> Path:
    """Return sibling ``facts.jsonl`` next to a spring_signals ``--out`` path."""
    return Path(out_path).resolve().parent / "facts.jsonl"


def _default_scanner(signals: Mapping[str, Any]) -> Optional[str]:
    scanners = signals.get("scanners") or []
    if not scanners:
        return None
    return ",".join(str(s) for s in scanners)


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


def _maps_to_from_entity_table_map(
    entity_table_map: Mapping[str, Any],
    default_scanner: Optional[str],
) -> List[Dict[str, Any]]:
    """Derived stub: contested entries become one MAPS_TO per candidate."""
    facts: List[Dict[str, Any]] = []
    for class_name, entry in entity_table_map.items():
        if not isinstance(entry, Mapping):
            continue
        status = entry.get("status")
        candidates = entry.get("candidates")
        if status == "contested" and isinstance(candidates, list) and candidates:
            for cand in candidates:
                if not isinstance(cand, Mapping):
                    continue
                quals: Dict[str, Any] = {"status": "contested"}
                if cand.get("table_name_source") is not None:
                    quals["table_name_source"] = cand.get("table_name_source")
                elif entry.get("table_name_source") is not None:
                    quals["table_name_source"] = entry.get("table_name_source")
                facts.append(
                    _fact(
                        predicate="MAPS_TO",
                        subject=str(class_name),
                        object_=None if cand.get("table") is None else str(cand.get("table")),
                        qualifiers=quals,
                        file=None if cand.get("file") is None else str(cand.get("file")),
                        line=cand.get("line") if isinstance(cand.get("line"), int) else None,
                        rule_id=cand.get("rule_id") or entry.get("rule_id"),
                        scanner=cand.get("scanner") or default_scanner,
                    )
                )
            continue

        quals = {}
        if entry.get("status") is not None:
            quals["status"] = entry.get("status")
        if entry.get("table_name_source") is not None:
            quals["table_name_source"] = entry.get("table_name_source")
        facts.append(
            _fact(
                predicate="MAPS_TO",
                subject=str(class_name),
                object_=None if entry.get("table") is None else str(entry.get("table")),
                qualifiers=quals,
                file=None if entry.get("file") is None else str(entry.get("file")),
                line=entry.get("line") if isinstance(entry.get("line"), int) else None,
                rule_id=entry.get("rule_id"),
                scanner=entry.get("scanner") or default_scanner,
            )
        )
    return facts


def _facts_from_evidence(
    evidence: Mapping[str, Any],
    default_scanner: Optional[str],
) -> List[Dict[str, Any]]:
    facts: List[Dict[str, Any]] = []
    for _bucket, hits in evidence.items():
        if not isinstance(hits, list):
            continue
        for hit in hits:
            if not isinstance(hit, Mapping):
                continue
            file_path = hit.get("file")
            if file_path is None:
                continue
            rule_id = hit.get("rule_id")
            predicate = str(rule_id) if rule_id else "EVIDENCE"
            match = hit.get("match")
            facts.append(
                _fact(
                    predicate=predicate,
                    subject=str(file_path),
                    object_=None if match is None else str(match),
                    qualifiers={"bucket": _bucket} if _bucket else {},
                    file=str(file_path),
                    line=hit.get("line") if isinstance(hit.get("line"), int) else None,
                    rule_id=None if rule_id is None else str(rule_id),
                    scanner=hit.get("scanner") or default_scanner,
                )
            )
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
    facts.sort(key=_sort_key)
    return facts


def write_facts_jsonl(path: PathLike, facts: List[Mapping[str, Any]]) -> None:
    """Write fact records as UTF-8 JSON Lines (one object per line)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for fact in facts:
            fh.write(json.dumps(fact, ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def fact_emit_counts(facts: List[Mapping[str, Any]]) -> Dict[str, int]:
    """Return counters for dual-emit observability (gap/error analysis)."""
    maps_to = 0
    maps_to_contested = 0
    evidence = 0
    for fact in facts:
        predicate = fact.get("predicate")
        if predicate == "MAPS_TO":
            maps_to += 1
            quals = fact.get("qualifiers") or {}
            if isinstance(quals, Mapping) and quals.get("status") == "contested":
                maps_to_contested += 1
        else:
            evidence += 1
    return {
        "facts_total": len(facts),
        "facts_maps_to": maps_to,
        "facts_maps_to_contested": maps_to_contested,
        "facts_evidence": evidence,
    }
