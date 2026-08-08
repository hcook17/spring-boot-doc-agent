"""R_join: Path A entity_table_map ↔ MAPS_TO fact identity keys."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from doc_engine.scanning.symbol import SymbolError, parse

from .common import _maps_to, _rate_block


def _fact_identity_keys(fact: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    quals = fact.get("qualifiers") or {}
    if not isinstance(quals, Mapping):
        return keys
    fqcn = quals.get("fqcn")
    if fqcn:
        keys.add(f"fqcn:{fqcn}")
    display = quals.get("display_name")
    package = None
    try:
        parsed = parse(str(fact.get("subject")))
        package = ".".join(parsed.namespaces) if parsed.namespaces else None
        if display:
            keys.add(f"simple:{display}")
        if package and display:
            keys.add(f"pkg_simple:{package}|{display}")
    except SymbolError:
        if display:
            keys.add(f"simple:{display}")
    return keys


def measure_r_join(
    signals: Mapping[str, Any],
    facts: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    entity_map = signals.get("entity_table_map") or {}
    if not isinstance(entity_map, Mapping):
        entity_map = {}
    fact_keys: set[str] = set()
    for fact in _maps_to(facts):
        fact_keys |= _fact_identity_keys(fact)

    matched = 0
    failures: List[Dict[str, Any]] = []
    for name, entry in entity_map.items():
        if not isinstance(entry, Mapping):
            continue
        candidates = entry.get("candidates") if entry.get("status") == "contested" else None
        sources: List[Mapping[str, Any]] = (
            [candidate for candidate in candidates if isinstance(candidate, Mapping)]
            if isinstance(candidates, list) and candidates
            else [entry]
        )
        hit = False
        for source in sources:
            fqcn = source.get("fqcn") or entry.get("fqcn")
            package = source.get("package") or entry.get("package")
            keys = {f"simple:{name}"}
            if fqcn:
                keys.add(f"fqcn:{fqcn}")
            if package:
                keys.add(f"pkg_simple:{package}|{name}")
            if keys & fact_keys:
                hit = True
                break
        if hit:
            matched += 1
        else:
            failures.append(
                {
                    "layer": "join",
                    "stratum": "path_a_to_facts",
                    "reason_class": "unmatched",
                    "simple_name": name,
                    "file": entry.get("file"),
                }
            )
    denominator = len(entity_map)
    out = _rate_block(matched, denominator)
    out["failures"] = failures
    return out
