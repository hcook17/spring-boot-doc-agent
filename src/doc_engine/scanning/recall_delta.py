"""Entity recall delta between native (ast-grep) and oracle arms.

Emits RECALL_MISS facts with STRUCTURAL | EVIDENTIARY verdicts when an
oracle arm contributed entity_table_map candidates. Without an oracle arm,
returns [] — default Stage 0 must not claim recall.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Set


def _entity_keys(partial: Mapping[str, Any]) -> Set[str]:
    keys: Set[str] = set()
    for name in partial.get("entity_table_map", {}) or {}:
        keys.add(str(name))
    for name in partial.get("entity_table_map_candidates", {}) or {}:
        keys.add(str(name))
    return keys


def _fqcn_for(signals: Mapping[str, Any], class_name: str) -> Optional[str]:
    entry = (signals.get("entity_table_map") or {}).get(class_name) or {}
    return entry.get("fqcn")


def _recall_verdict(
    signals: Mapping[str, Any],
    *,
    name: str,
    oracle_arm: str,
) -> str:
    # Heuristic: simple-name only in oracle often STRUCTURAL (inheritance /
    # pattern expressiveness); classpath-only → EVIDENTIARY when CodeQL.
    if oracle_arm != "codeql":
        return "STRUCTURAL"
    if name in (signals.get("entity_table_map") or {}):
        return "STRUCTURAL"
    # Present in CodeQL bag, absent from merged map after contest —
    # still a miss relative to native keys supplied.
    return "EVIDENTIARY" if name.endswith("Impl") else "STRUCTURAL"


def _recall_miss_fact(
    signals: Mapping[str, Any],
    *,
    name: str,
    oracle_arm: str,
    native_arm: str,
) -> Dict[str, Any]:
    fqcn = _fqcn_for(signals, name)
    return {
        "predicate": "RECALL_MISS",
        "subject": f"entity:{name}",
        "object": fqcn,
        "qualifiers": {
            "verdict": _recall_verdict(signals, name=name, oracle_arm=oracle_arm),
            "oracle_arm": oracle_arm,
            "native_arm": native_arm,
            "display_name": name,
            "fqcn": fqcn,
        },
        "file": ((signals.get("entity_table_map") or {}).get(name) or {}).get("file"),
        "line": None,
        "rule_id": "persistence__entity",
        "scanner": "recall-delta-writer",
    }


def write_recall_miss_facts(
    signals: Mapping[str, Any],
    *,
    native_entity_keys: Set[str],
    oracle_entity_keys: Set[str],
    oracle_arm: str,
    native_arm: str = "ast-grep",
) -> List[Dict[str, Any]]:
    """Oracle − native → RECALL_MISS. Inheritance-shaped names → STRUCTURAL."""
    if not oracle_entity_keys:
        return []
    return [
        _recall_miss_fact(
            signals, name=name, oracle_arm=oracle_arm, native_arm=native_arm,
        )
        for name in sorted(oracle_entity_keys - native_entity_keys)
    ]


def collect_arm_entity_keys(
    partials: List[Mapping[str, Any]],
    *,
    scanner_names: List[str],
) -> tuple[Set[str], Set[str], Optional[str]]:
    """Return (native_keys, oracle_keys, oracle_arm_name).

    Native arm is ast-grep. Oracle arms: codeql (wired), multipass/metamodel
    when registered as scanner names (research → optional profile).
    """
    native: Set[str] = set()
    oracle: Set[str] = set()
    oracle_arm: Optional[str] = None
    for name, partial in zip(scanner_names, partials, strict=True):
        keys = _entity_keys(partial)
        if name == "ast-grep":
            native |= keys
        elif name in {"codeql", "multipass", "metamodel"}:
            oracle |= keys
            oracle_arm = name
        else:
            pass
    return native, oracle, oracle_arm
