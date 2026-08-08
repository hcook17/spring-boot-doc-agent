"""Evidence-backed ABSENCE / UNPROVEN writers (callable-trial discipline).

callable(F) ⇔ covering verifies ∧ rule pack applied ∧ family_witness(F).
See claude/research/stage0-covering-absence-recall-2026-07-30.md.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

# Family → (evidence buckets that count as positive hits, dep regexes)
_FAMILY_SPEC: Dict[str, Dict[str, Any]] = {
    "messaging": {
        "buckets": ("messaging",),
        "dep_patterns": (re.compile(r"kafka|rabbit|amqp|jms", re.I),),
    },
    "redis": {
        "buckets": ("observability", "configuration", "outbound_clients"),
        "dep_patterns": (re.compile(r"redis", re.I),),
    },
    "feign": {
        "buckets": ("outbound_clients",),
        "dep_patterns": (re.compile(r"feign|openfeign", re.I),),
    },
    "actuator": {
        "buckets": ("observability", "configuration"),
        "dep_patterns": (re.compile(r"actuator", re.I),),
    },
    "aws_secrets": {
        "buckets": ("configuration", "security"),
        "dep_patterns": (re.compile(r"secretsmanager|aws.?secrets", re.I),),
    },
    "security": {
        "buckets": ("security",),
        "dep_patterns": (
            re.compile(r"spring-boot-starter-security|springframework\.security", re.I),
        ),
    },
    "config": {
        "buckets": ("configuration",),
        "dep_patterns": (),
    },
}


def _dep_rows(signals: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for row in signals.get("evidence", {}).get("deployment", []) or []:
        rows.append(row)
    return rows


def _config_witness(signals: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    keys = signals.get("config_key_sets") or {}
    if not keys:
        return None
    return {"kind": "config_key_sets", "ref": sorted(keys)[0]}


def _dep_row_haystack(row: Mapping[str, Any]) -> str:
    hay = " ".join(
        str(row.get(key) or "")
        for key in ("match", "coordinate", "plugin_id", "configuration")
    )
    coordinate = row.get("coordinate")
    if not isinstance(coordinate, dict):
        return hay
    return hay + " " + " ".join(
        str(coordinate.get(key) or "") for key in ("group", "name", "version")
    )


def _dep_witness_for_row(
    row: Mapping[str, Any],
    patterns: Sequence[Any],
) -> Optional[Dict[str, Any]]:
    hay = _dep_row_haystack(row)
    for pattern in patterns:
        if pattern.search(hay):
            return {
                "kind": "deployment_dependency",
                "ref": row.get("file"),
                "line": row.get("line"),
                "match": row.get("match"),
            }
    return None


def _family_witness(
    family: str,
    signals: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    if family == "config":
        return _config_witness(signals)
    patterns = _FAMILY_SPEC[family]["dep_patterns"]
    for row in _dep_rows(signals):
        witness = _dep_witness_for_row(row, patterns)
        if witness is not None:
            return witness
    return None


def _row_is_family_hit(
    row: Mapping[str, Any],
    *,
    family: str,
    patterns: Sequence[Any],
) -> bool:
    rule_id = str(row.get("rule_id") or "")
    match = str(row.get("match") or "")
    # Prefer family-prefixed structural rules (messaging__, security__).
    if rule_id.startswith(f"{family}__"):
        return True
    hay = f"{rule_id} {match}"
    return any(pattern.search(hay) for pattern in patterns)


def _bucket_family_hits(
    rows: Any,
    *,
    family: str,
    patterns: Sequence[Any],
) -> int:
    if not rows:
        return 0
    return sum(
        1
        for row in rows
        if isinstance(row, Mapping)
        and _row_is_family_hit(row, family=family, patterns=patterns)
    )


def _config_positive_hits(signals: Mapping[str, Any]) -> int:
    keys = signals.get("config_key_sets") or {}
    return 1 if keys else 0


def _evidence_positive_hits(family: str, signals: Mapping[str, Any]) -> int:
    spec = _FAMILY_SPEC[family]
    evidence = signals.get("evidence") or {}
    patterns = spec["dep_patterns"]
    return sum(
        _bucket_family_hits(
            evidence.get(bucket) or [],
            family=family,
            patterns=patterns,
        )
        for bucket in spec["buckets"]
    )


def _positive_hits(family: str, signals: Mapping[str, Any]) -> int:
    """Count Path A rows that are *family-relevant* presence evidence.

    Shared evidence buckets (e.g. observability for both redis and actuator)
    must not count an unrelated ``rule_id`` as presence for every family that
    lists the bucket — that erased UNPROVEN under hits-first short-circuit.
    """
    if family == "config":
        return _config_positive_hits(signals)
    return _evidence_positive_hits(family, signals)


def _absence_predicate(callable_trial: bool) -> tuple[str, str]:
    if callable_trial:
        return "ABSENCE", "callable"
    return "UNPROVEN", "non_callable"


def _absence_fact_for_family(
    family: str,
    signals: Mapping[str, Any],
    *,
    covering_ok: bool,
    covering_root: Optional[str],
    scanner_version: Optional[str],
    astgrep_receipt_complete: bool,
) -> Optional[Dict[str, Any]]:
    witness = _family_witness(family, signals)
    hits = _positive_hits(family, signals)
    # Presence short-circuits — never UNPROVEN a family Path A already hit.
    if hits > 0:
        return None
    callable_trial = bool(
        covering_ok and astgrep_receipt_complete and witness is not None
    )
    predicate, trial = _absence_predicate(callable_trial)
    return {
        "predicate": predicate,
        "subject": f"family:{family}",
        "object": None,
        "qualifiers": {
            "trial": trial,
            "family": family,
            "family_witness": witness,
            "covering_root": covering_root,
            "scanner_version": scanner_version,
            "positive_hits": hits,
        },
        "file": (witness or {}).get("ref"),
        "line": (witness or {}).get("line"),
        "rule_id": None,
        "scanner": "absence-writer",
    }


def write_absence_facts(
    signals: Mapping[str, Any],
    *,
    covering_ok: bool,
    covering_root: Optional[str],
    scanner_version: Optional[str],
    astgrep_receipt_complete: bool,
) -> List[Dict[str, Any]]:
    """Emit ABSENCE or UNPROVEN facts for each known family.

    Transform order (absence claims only — presence lives on Path A SoR):
      hits > 0     → no stamp
      callable     → ABSENCE
      else         → UNPROVEN
    """
    facts: List[Dict[str, Any]] = []
    for family in sorted(_FAMILY_SPEC):
        fact = _absence_fact_for_family(
            family,
            signals,
            covering_ok=covering_ok,
            covering_root=covering_root,
            scanner_version=scanner_version,
            astgrep_receipt_complete=astgrep_receipt_complete,
        )
        if fact is not None:
            facts.append(fact)
    return facts


def count_callable_trials(
    signals: Mapping[str, Any],
    *,
    covering_ok: bool,
    astgrep_receipt_complete: bool,
) -> int:
    """Number of families for which callable(F) holds (ABSENCE denom support)."""
    n = 0
    for family in _FAMILY_SPEC:
        witness = _family_witness(family, signals)
        if covering_ok and astgrep_receipt_complete and witness is not None:
            n += 1
    return n
