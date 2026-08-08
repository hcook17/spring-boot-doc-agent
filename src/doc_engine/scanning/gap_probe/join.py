"""R_join: Path A entity_table_map ↔ MAPS_TO fact identity keys."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple

from doc_engine._compat import StrEnum
from doc_engine.scanning.symbol import SymbolError, parse

from .common import _maps_to, _rate_block


class EntityMapStatus(StrEnum):
    """Closed Path A entity_table_map status values used by R_join."""

    CONTESTED = "contested"


def _fact_identity_keys(fact: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    qualifiers = fact.get("qualifiers") or {}
    if not isinstance(qualifiers, Mapping):
        return keys
    fqcn = qualifiers.get("fqcn")
    if fqcn:
        keys.add(f"fqcn:{fqcn}")
    display_name = qualifiers.get("display_name")
    try:
        parsed = parse(str(fact.get("subject")))
        package = ".".join(parsed.namespaces) if parsed.namespaces else None
        if display_name:
            keys.add(f"simple:{display_name}")
        if package and display_name:
            keys.add(f"pkg_simple:{package}|{display_name}")
    except SymbolError:
        if display_name:
            keys.add(f"simple:{display_name}")
    return keys


def _collect_maps_to_identity_keys(facts: Sequence[Mapping[str, Any]]) -> set[str]:
    fact_keys: set[str] = set()
    for fact in _maps_to(facts):
        fact_keys |= _fact_identity_keys(fact)
    return fact_keys


def _entity_join_sources(entry: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """Settled entries join as themselves; contested entries expand candidates."""
    if entry.get("status") != EntityMapStatus.CONTESTED:
        return [entry]
    candidates = entry.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return [entry]
    typed = [candidate for candidate in candidates if isinstance(candidate, Mapping)]
    return typed or [entry]


def _entity_identity_keys(
    simple_name: str,
    entry: Mapping[str, Any],
    source: Mapping[str, Any],
) -> set[str]:
    keys = {f"simple:{simple_name}"}
    fqcn = source.get("fqcn") or entry.get("fqcn")
    package = source.get("package") or entry.get("package")
    if fqcn:
        keys.add(f"fqcn:{fqcn}")
    if package:
        keys.add(f"pkg_simple:{package}|{simple_name}")
    return keys


def _entity_matches_fact_keys(
    simple_name: str,
    entry: Mapping[str, Any],
    fact_keys: set[str],
) -> bool:
    for source in _entity_join_sources(entry):
        if _entity_identity_keys(simple_name, entry, source) & fact_keys:
            return True
    return False


def _unmatched_join_failure(
    simple_name: str,
    entry: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "layer": "join",
        "stratum": "path_a_to_facts",
        "reason_class": "unmatched",
        "simple_name": simple_name,
        "file": entry.get("file"),
    }


def _score_path_a_join(
    entity_map: Mapping[str, Any],
    fact_keys: set[str],
) -> Tuple[int, List[Dict[str, Any]]]:
    """Count Path A entities that settle onto at least one MAPS_TO identity key."""
    matched = 0
    failures: List[Dict[str, Any]] = []
    for simple_name, entry in entity_map.items():
        if not isinstance(entry, Mapping):
            continue
        if _entity_matches_fact_keys(simple_name, entry, fact_keys):
            matched += 1
        else:
            failures.append(_unmatched_join_failure(simple_name, entry))
    return matched, failures


def measure_r_join(
    signals: Mapping[str, Any],
    facts: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    entity_map = signals.get("entity_table_map") or {}
    if not isinstance(entity_map, Mapping):
        entity_map = {}
    fact_keys = _collect_maps_to_identity_keys(facts)
    matched, failures = _score_path_a_join(entity_map, fact_keys)
    block = _rate_block(matched, len(entity_map))
    block["failures"] = failures
    return block
