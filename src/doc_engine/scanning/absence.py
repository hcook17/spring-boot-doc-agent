"""Evidence-backed ABSENCE / UNPROVEN writers (callable-trial discipline).

callable(F) ⇔ covering verifies ∧ rule pack applied ∧ family_witness(F).
See claude/research/stage0-covering-absence-recall-2026-07-30.md.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional

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


def _family_witness(
    family: str,
    signals: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    spec = _FAMILY_SPEC[family]
    if family == "config":
        keys = signals.get("config_key_sets") or {}
        if keys:
            return {"kind": "config_key_sets", "ref": sorted(keys)[0]}
        return None
    for row in _dep_rows(signals):
        hay = " ".join(
            str(row.get(k) or "")
            for k in ("match", "coordinate", "plugin_id", "configuration")
        )
        if isinstance(row.get("coordinate"), dict):
            coord = row["coordinate"]
            hay += " " + " ".join(str(coord.get(k) or "") for k in ("group", "name", "version"))
        for pat in spec["dep_patterns"]:
            if pat.search(hay):
                return {
                    "kind": "deployment_dependency",
                    "ref": row.get("file"),
                    "line": row.get("line"),
                    "match": row.get("match"),
                }
    return None


def _positive_hits(family: str, signals: Mapping[str, Any]) -> int:
    """Count Path A rows that are *family-relevant* presence evidence.

    Shared evidence buckets (e.g. observability for both redis and actuator)
    must not count an unrelated ``rule_id`` as presence for every family that
    lists the bucket — that erased UNPROVEN under hits-first short-circuit.
    """
    spec = _FAMILY_SPEC[family]
    if family == "config":
        keys = signals.get("config_key_sets") or {}
        return 1 if keys else 0

    evidence = signals.get("evidence") or {}
    n = 0
    for bucket in spec["buckets"]:
        for row in evidence.get(bucket) or []:
            rule_id = str(row.get("rule_id") or "")
            match = str(row.get("match") or "")
            hay = f"{rule_id} {match}"
            # Prefer family-prefixed structural rules (messaging__, security__).
            if rule_id.startswith(f"{family}__"):
                n += 1
                continue
            # Dep-linked families: pattern must hit rule_id or match text.
            hit = False
            for pat in spec["dep_patterns"]:
                if pat.search(hay):
                    hit = True
                    break
            if hit:
                n += 1
    return n


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
        witness = _family_witness(family, signals)
        hits = _positive_hits(family, signals)
        callable_trial = bool(
            covering_ok and astgrep_receipt_complete and witness is not None
        )
        # Presence short-circuits — never UNPROVEN a family Path A already hit.
        if hits > 0:
            continue
        if callable_trial:
            predicate = "ABSENCE"
            trial = "callable"
        else:
            predicate = "UNPROVEN"
            trial = "non_callable"
        facts.append(
            {
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
        )
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
