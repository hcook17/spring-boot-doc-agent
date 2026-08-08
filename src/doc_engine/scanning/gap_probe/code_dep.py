"""R_code|dep: deployment-family evidence covered by code-bucket keywords."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .common import (
    _CODE_BUCKET_BY_FAMILY,
    _DEP_FAMILY_PATTERNS,
    _rate_block,
)


def _row_text(row: Mapping[str, Any], fields: Sequence[str]) -> str:
    return " ".join(str(row.get(field) or "") for field in fields)


def _bump_dep_families_for_row(dep_counts: Counter[str], row: Any) -> None:
    """Increment family counters when *row* text matches a dep-family pattern."""
    if not isinstance(row, Mapping):
        return
    text = _row_text(row, ("match", "rule_id", "file"))
    for family, pattern in _DEP_FAMILY_PATTERNS:
        if pattern.search(text):
            dep_counts[family] += 1


def _count_deployment_families(deployment_rows: Sequence[Any]) -> Counter[str]:
    """Count deployment evidence rows that match each dep-family pattern."""
    dep_counts: Counter[str] = Counter()
    for row in deployment_rows:
        _bump_dep_families_for_row(dep_counts, row)
    return dep_counts


def _row_matches_pattern(
    row: Any,
    pattern: re.Pattern[str],
    fields: Sequence[str],
) -> bool:
    if not isinstance(row, Mapping):
        return False
    return bool(pattern.search(_row_text(row, fields)))


def _bucket_keyword_hits(
    rows: Any,
    pattern: re.Pattern[str],
) -> int:
    if not isinstance(rows, list):
        return 0
    return sum(
        1 for row in rows if _row_matches_pattern(row, pattern, ("match", "rule_id"))
    )


def _code_keyword_hits_for_family(
    evidence: Mapping[str, Any],
    family: str,
    pattern: re.Pattern[str],
) -> int:
    """Count code-bucket rows whose match/rule_id text matches a dep family."""
    hits = 0
    for bucket in _CODE_BUCKET_BY_FAMILY.get(family, ()):
        hits += _bucket_keyword_hits(evidence.get(bucket) or [], pattern)
    return hits


def _family_coverage(
    family: str,
    dep_signal_count: int,
    keyword_hits: int,
) -> Tuple[int, Dict[str, Any], Optional[Dict[str, Any]]]:
    """Return covered weight, per-family row, and optional failure for one family."""
    covered_weight = dep_signal_count if keyword_hits > 0 else 0
    per_family = {
        "dep_signals": dep_signal_count,
        "code_keyword_hits": keyword_hits,
        "covered_dep_weight": covered_weight,
    }
    if keyword_hits > 0:
        return covered_weight, per_family, None
    failure = {
        "layer": "dep_code",
        "stratum": family,
        "reason_class": "dep_without_code_keyword",
        "dep_signals": dep_signal_count,
    }
    return covered_weight, per_family, failure


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def measure_r_code_dep(signals: Mapping[str, Any]) -> Dict[str, Any]:
    evidence = _as_mapping(signals.get("evidence") or {})
    deployment = _as_list(evidence.get("deployment") or [])

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
        covered, family_row, failure = _family_coverage(
            family, dep_signal_count, keyword_hits,
        )
        dep_total += dep_signal_count
        code_hits += covered
        per_family[family] = family_row
        if failure is not None:
            failures.append(failure)

    out = _rate_block(code_hits, dep_total)
    out["per_family"] = per_family
    out["failures"] = failures
    return out
