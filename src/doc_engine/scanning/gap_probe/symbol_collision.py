"""R_sym / R_coll measures over MAPS_TO facts and Path A entity map."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from doc_engine.scanning.symbol import SymbolError, parse

from .common import _maps_to, _rate_block


def measure_r_sym(facts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    maps = _maps_to(facts)
    ok = 0
    failures: List[Dict[str, Any]] = []
    for f in maps:
        subject = f.get("subject")
        try:
            parsed = parse(str(subject))
            if parsed.kind != "type":
                raise SymbolError(f"kind={parsed.kind}")
            ok += 1
        except SymbolError as exc:
            failures.append(
                {
                    "layer": "facts",
                    "stratum": "maps_to_symbol",
                    "reason_class": "unparseable_or_non_type",
                    "subject": subject,
                    "file": f.get("file"),
                    "detail": str(exc),
                }
            )
    den = len(maps)
    out = _rate_block(ok, den)
    out["failures"] = failures
    return out


def measure_r_coll(signals: Mapping[str, Any]) -> Dict[str, Any]:
    entity_map = signals.get("entity_table_map") or {}
    if not isinstance(entity_map, Mapping):
        entity_map = {}
    contested = 0
    failures: List[Dict[str, Any]] = []
    for name, entry in entity_map.items():
        if not isinstance(entry, Mapping):
            continue
        if entry.get("status") == "contested":
            contested += 1
            failures.append(
                {
                    "layer": "path_a",
                    "stratum": "collision",
                    "reason_class": "contested",
                    "simple_name": name,
                    "file": entry.get("file"),
                    "candidates": len(entry.get("candidates") or []),
                }
            )
    den = len(entity_map)
    out = _rate_block(contested, den)
    out["failures"] = failures
    return out
