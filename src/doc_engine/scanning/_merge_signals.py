#!/usr/bin/env python3
"""Deterministic merge of partial spring_signals.json dicts from scanner backends.

The merge is deterministic and rule-based: no LLM involvement. Downstream
stages read the merged output exactly as they read a single-scanner output.
"""

import logging
from typing import Any, Dict, List, Optional

from doc_engine.core.protocols import Merger
from doc_engine.scanning.java_extract import to_snake_case

_LOG = logging.getLogger(__name__)


def _default_dict() -> Dict[str, Any]:
    return {
        "schema_version": 7,
        "scanner_version": None,
        "repo_path": None,
        "files_scanned": {},
        "entity_table_map": {},
        "evidence": {},
        "file_signature_algorithm": "sha256",
        "file_signatures": {},
        "redaction_zones": {},
        "config_key_sets": {},
    }


def _dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate evidence rows by (file, line, rule_id), preserving first seen."""
    seen: set = set()
    result: List[Dict[str, Any]] = []
    for row in rows:
        key = (row.get("file"), row.get("line"), row.get("rule_id"))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _merge_evidence(partials: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Merge evidence buckets from all backends and deduplicate rows."""
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for partial in partials:
        for bucket_name, rows in partial.get("evidence", {}).items():
            buckets.setdefault(bucket_name, []).extend(rows)
    merged = {}
    for bucket_name, rows in buckets.items():
        merged[bucket_name] = _dedupe_rows(rows)
    return merged


def _seed_entity_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    seeded = dict(entry)
    if "candidates" in seeded:
        seeded["candidates"] = list(seeded["candidates"])
    return seeded


def _entries_disagree(existing: Dict[str, Any], entry: Dict[str, Any]) -> bool:
    return (
        existing.get("table") != entry.get("table")
        or existing.get("file") != entry.get("file")
    )


def _mark_contested(existing: Dict[str, Any], entry: Dict[str, Any]) -> None:
    existing["status"] = "contested"
    candidates = existing.setdefault("candidates", [dict(existing)])
    candidate_copy = dict(entry)
    if candidate_copy not in candidates:
        candidates.append(candidate_copy)


def _merge_one_entity_entry(
    merged: Dict[str, Any],
    class_name: str,
    entry: Dict[str, Any],
) -> None:
    if class_name not in merged:
        merged[class_name] = _seed_entity_entry(entry)
        return
    existing = merged[class_name]
    if _entries_disagree(existing, entry):
        _mark_contested(existing, entry)


def _merge_entity_table_map(partials: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge entity_table_map entries.

    If multiple backends map the same simple class name, the first backend's
    entry wins and the entry is marked contested with candidates from all
    backends.
    """
    merged: Dict[str, Any] = {}
    for partial in partials:
        for class_name, entry in partial.get("entity_table_map", {}).items():
            _merge_one_entity_entry(merged, class_name, entry)
    return merged


def _candidate_record(class_name: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    record = {
        "file": entry["file"],
        "table": entry["table"],
        "table_name_source": entry["table_name_source"],
        "fqcn": entry.get("fqcn") or class_name,
    }
    if entry.get("package") is not None:
        record["package"] = entry["package"]
    return record


def _ordered_unique_by_file(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_file: Dict[str, Dict[str, Any]] = {}
    for cand in candidates:
        by_file.setdefault(cand["file"], cand)
    return sorted(by_file.values(), key=lambda entry: entry["file"])


def _finalize_one_entity(
    class_name: str,
    candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    ordered = _ordered_unique_by_file(candidates)
    winner = dict(ordered[0])
    if len(ordered) <= 1:
        return winner
    winner["status"] = "contested"
    winner["candidates"] = [_candidate_record(class_name, entry) for entry in ordered]
    _LOG.warning(
        "entity_table_map key %r is contested — %d @Entity classes share "
        "this simple name across packages; JPQL lineage for this name will "
        "be unavailable rather than guessed. Files: %s",
        class_name,
        len(ordered),
        ", ".join(entry["file"] for entry in ordered),
    )
    return winner


def _finalize_entity_table_map(entity_candidates: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Collapse per-simple-name candidate lists into entity_table_map.

    Keyed by simple class name alone, so two @Entity classes in different
    packages collide. Lowest file path wins citation-identity fields for
    drift-check stability; when more than one candidate exists the entry is
    status=contested with a candidates list.
    """
    return {
        class_name: _finalize_one_entity(class_name, candidates)
        for class_name, candidates in entity_candidates.items()
    }


def _entity_candidate_from_row(row: Dict[str, Any], class_name: str) -> Dict[str, Any]:
    candidate = {
        "file": row["file"],
        "table": row.get("table", to_snake_case(class_name)),
        "table_name_source": row.get("table_name_source", "inferred-default-naming"),
        "rule_id": row.get("rule_id", "persistence__entity"),
        "match": row.get("match", ""),
        "fqcn": row.get("fqcn") or class_name,
    }
    if row.get("package") is not None:
        candidate["package"] = row["package"]
    return candidate


def _collect_entity_candidates(
    partial: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    candidates: Dict[str, List[Dict[str, Any]]] = {}
    for row in partial.get("evidence", {}).get("persistence", []):
        if row.get("rule_id") != "persistence__entity":
            continue
        class_name = row.get("class_name")
        if not class_name:
            continue
        candidates.setdefault(class_name, []).append(
            _entity_candidate_from_row(row, class_name)
        )
    return candidates


def _build_entity_table_map_from_evidence(partial: Dict[str, Any]) -> Dict[str, Any]:
    """Build entity_table_map from persistence__entity evidence rows."""
    return _finalize_entity_table_map(_collect_entity_candidates(partial))


def _merge_redaction_zones(partials: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Merge redaction_zones per file."""
    merged: Dict[str, List[Dict[str, Any]]] = {}
    for partial in partials:
        for file_path, zones in partial.get("redaction_zones", {}).items():
            merged.setdefault(file_path, []).extend(zones)
    return merged


def _merge_config_key_sets(partials: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Merge config_key_sets per file, deduplicating keys."""
    merged: Dict[str, List[str]] = {}
    for partial in partials:
        for file_path, keys in partial.get("config_key_sets", {}).items():
            merged.setdefault(file_path, []).extend(keys)
    for file_path in merged:
        merged[file_path] = sorted(set(merged[file_path]))
    return merged


def _record_file_signature(
    merged: Dict[str, str],
    file_path: str,
    sig: str,
) -> None:
    if file_path in merged and merged[file_path] != sig:
        _LOG.warning(
            "file_signatures conflict for %s: keeping %s, ignoring %s "
            "(covering proof uses walk SoR, not this Path A map)",
            file_path,
            merged[file_path],
            sig,
        )
        return
    merged[file_path] = sig


def _merge_file_signatures(partials: List[Dict[str, Any]]) -> Dict[str, str]:
    """Merge Path A ``file_signatures`` maps (first-wins on conflict).

    The Stage-0 covering proof is built from the walk SoR
    (``ScanContext.file_signatures``), not this merged dict. Conflicts here are
    therefore Path A / drift telemetry issues — log and keep the first hash.
    """
    merged: Dict[str, str] = {}
    for partial in partials:
        for file_path, sig in partial.get("file_signatures", {}).items():
            _record_file_signature(merged, file_path, sig)
    return merged


def _merge_files_scanned(partials: List[Dict[str, Any]]) -> Dict[str, int]:
    """Sum files_scanned counts across backends."""
    merged: Dict[str, int] = {}
    for partial in partials:
        for category, count in partial.get("files_scanned", {}).items():
            merged[category] = merged.get(category, 0) + count
    return merged


def _sort_evidence(evidence: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """Sort every bucket by (file, line) for deterministic output."""
    sorted_evidence = {}
    for bucket_name in sorted(evidence.keys()):
        rows = evidence[bucket_name]
        sorted_evidence[bucket_name] = sorted(
            rows, key=lambda r: (r.get("file", ""), r.get("line", 0))
        )
    return sorted_evidence


def _entity_maps_from_partials(partials: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    entity_maps: List[Dict[str, Any]] = []
    for partial in partials:
        if "entity_table_map_candidates" in partial:
            entity_maps.append(
                _finalize_entity_table_map(partial["entity_table_map_candidates"])
            )
        if "entity_table_map" in partial:
            entity_maps.append(partial["entity_table_map"])
    return entity_maps


def _resolve_merged_entity_map(
    partials: List[Dict[str, Any]],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    merged_map = _merge_entity_table_map(
        [{"entity_table_map": em} for em in _entity_maps_from_partials(partials)]
    )
    if merged_map:
        return merged_map
    return _build_entity_table_map_from_evidence(result)


def merge(
    partials: List[Dict[str, Any]],
    repo_path: str,
    scanner_version: str,
    scanner_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Merge partial spring_signals.json dicts into one canonical output.

    Args:
        partials: list of partial dicts from scanner backends.
        repo_path: absolute path to the scanned repository.
        scanner_version: combined version hash covering all backends and rules.
        scanner_names: ordered list of scanner names that produced the partials.

    Returns:
        A complete spring_signals.json dict with schema_version 7.
    """
    result = _default_dict()
    result["repo_path"] = repo_path
    result["scanner_version"] = scanner_version
    result["scanners"] = list(scanner_names) if scanner_names else []

    # Evidence first — entity_table_map derivation reads the merged bag.
    result["evidence"] = _sort_evidence(_merge_evidence(partials))
    result["entity_table_map"] = dict(
        sorted(_resolve_merged_entity_map(partials, result).items())
    )
    result["redaction_zones"] = _merge_redaction_zones(partials)
    result["config_key_sets"] = _merge_config_key_sets(partials)
    result["file_signatures"] = _merge_file_signatures(partials)
    result["files_scanned"] = _merge_files_scanned(partials)
    return result


def sort_entity_table_map(entity_table_map: Dict[str, Any]) -> Dict[str, Any]:
    """Sort entity_table_map by class name for deterministic output."""
    return dict(sorted(entity_table_map.items()))


class SpringSignalMerger(Merger):
    """Spring Boot implementation of the Merger protocol.

    Merges partial spring_signals.json dicts from the filesystem, CodeQL, and
    ast-grep scanners into one canonical output.
    """

    def merge(
        self,
        partials: List[Dict[str, Any]],
        repo_path: str,
        scanner_version: str,
        scanner_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return merge(partials, repo_path, scanner_version, scanner_names=scanner_names)
