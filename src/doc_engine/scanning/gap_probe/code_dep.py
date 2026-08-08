"""R_code|dep: deployment-family evidence covered by code-bucket keywords."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Mapping, Sequence

from .common import (
    _CODE_BUCKET_BY_FAMILY,
    _DEP_FAMILY_PATTERNS,
    _rate_block,
)


def _count_deployment_families(deployment_rows: Sequence[Any]) -> Counter[str]:
    """Count deployment evidence rows that match each dep-family pattern."""
    dep_counts: Counter[str] = Counter()
    for row in deployment_rows:
        if not isinstance(row, Mapping):
            continue
        text = " ".join(
            str(row.get(field) or "") for field in ("match", "rule_id", "file")
        )
        for family, pattern in _DEP_FAMILY_PATTERNS:
            if pattern.search(text):
                dep_counts[family] += 1
    return dep_counts


def _code_keyword_hits_for_family(
    evidence: Mapping[str, Any],
    family: str,
    pattern: re.Pattern[str],
) -> int:
    """Count code-bucket rows whose match/rule_id text matches a dep family."""
    hits = 0
    for bucket in _CODE_BUCKET_BY_FAMILY.get(family, ()):
        rows = evidence.get(bucket) or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            blob = " ".join(str(row.get(field) or "") for field in ("match", "rule_id"))
            if pattern.search(blob):
                hits += 1
    return hits


def measure_r_code_dep(signals: Mapping[str, Any]) -> Dict[str, Any]:
    evidence = signals.get("evidence") or {}
    if not isinstance(evidence, Mapping):
        evidence = {}
    deployment = evidence.get("deployment") or []
    if not isinstance(deployment, list):
        deployment = []

    dep_counts = _count_deployment_families(deployment)
    patterns = dict(_DEP_FAMILY_PATTERNS)

    code_hits = 0
    dep_total = 0
    per_family: Dict[str, Any] = {}
    failures: List[Dict[str, Any]] = []

    for family, dep_signal_count in sorted(dep_counts.items()):
        keyword_hits = _code_keyword_hits_for_family(
            evidence, family, patterns[family],
        )
        dep_total += dep_signal_count
        covered_weight = dep_signal_count if keyword_hits > 0 else 0
        code_hits += covered_weight
        per_family[family] = {
            "dep_signals": dep_signal_count,
            "code_keyword_hits": keyword_hits,
            "covered_dep_weight": covered_weight,
        }
        if keyword_hits == 0:
            failures.append(
                {
                    "layer": "dep_code",
                    "stratum": family,
                    "reason_class": "dep_without_code_keyword",
                    "dep_signals": dep_signal_count,
                }
            )

    out = _rate_block(code_hits, dep_total)
    out["per_family"] = per_family
    out["failures"] = failures
    return out
