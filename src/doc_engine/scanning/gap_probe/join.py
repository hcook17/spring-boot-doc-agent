"""R_join: Path A entity_table_map ↔ MAPS_TO fact identity keys."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from doc_engine._compat import StrEnum
from doc_engine.scanning.symbol import SymbolError, parse

from .common import _maps_to, _rate_block


class EntityMapStatus(StrEnum):
    """Closed Path A entity_table_map status values used by R_join."""

    CONTESTED = "contested"


def _add_fqcn_key(keys: set[str], fqcn: Any) -> None:
    if fqcn:
        keys.add(f"fqcn:{fqcn}")


def _add_display_keys(
    keys: set[str],
    display_name: Any,
    package: Optional[str],
) -> None:
    if not display_name:
        return
    keys.add(f"simple:{display_name}")
    if package:
        keys.add(f"pkg_simple:{package}|{display_name}")


def _subject_package(subject: Any) -> Optional[str]:
    try:
        parsed = parse(str(subject))
    except SymbolError:
        return None
    if not parsed.namespaces:
        return None
    return ".".join(parsed.namespaces)


def _fact_identity_keys(fact: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    qualifiers = fact.get("qualifiers") or {}
    if not isinstance(qualifiers, Mapping):
        return keys
    _add_fqcn_key(keys, qualifiers.get("fqcn"))
    _add_display_keys(
        keys,
        qualifiers.get("display_name"),
        _subject_package(fact.get("subject")),
    )
    return keys


def _collect_maps_to_identity_keys(facts: Sequence[Mapping[str, Any]]) -> set[str]:
    fact_keys: set[str] = set()
    for fact in _maps_to(facts):
        fact_keys |= _fact_identity_keys(fact)
    return fact_keys


def _contested_candidate_sources(entry: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    candidates = entry.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return [entry]
    typed = [candidate for candidate in candidates if isinstance(candidate, Mapping)]
    return typed or [entry]


def _entity_join_sources(entry: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """Settled entries join as themselves; contested entries expand candidates."""
    if entry.get("status") != EntityMapStatus.CONTESTED:
        return [entry]
    return _contested_candidate_sources(entry)


def _entity_identity_keys(
    simple_name: str,
    entry: Mapping[str, Any],
    source: Mapping[str, Any],
) -> set[str]:
    keys = {f"simple:{simple_name}"}
    _add_fqcn_key(keys, source.get("fqcn") or entry.get("fqcn"))
    package = source.get("package") or entry.get("package")
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


def _score_one_entity(
    simple_name: str,
    entry: Any,
    fact_keys: set[str],
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Return (matched, failure_or_None) for one entity_map entry."""
    if not isinstance(entry, Mapping):
        return False, None
    if _entity_matches_fact_keys(simple_name, entry, fact_keys):
        return True, None
    return False, _unmatched_join_failure(simple_name, entry)


def _score_path_a_join(
    entity_map: Mapping[str, Any],
    fact_keys: set[str],
) -> Tuple[int, List[Dict[str, Any]]]:
    """Count Path A entities that settle onto at least one MAPS_TO identity key."""
    matched = 0
    failures: List[Dict[str, Any]] = []
    for simple_name, entry in entity_map.items():
        is_match, failure = _score_one_entity(simple_name, entry, fact_keys)
        if is_match:
            matched += 1
        elif failure is not None:
            failures.append(failure)
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
