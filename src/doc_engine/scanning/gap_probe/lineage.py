"""R_lin: lineage availability rates under callable / pooled scoring envs."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .common import (
    SCORING_ENV_CALLABLE,
    SCORING_ENV_POOLED,
    ScoringEnv,
    _rate,
    _rate_block,
)


def _reason_mentions(reason: str, *needles: str) -> bool:
    lowered = reason.lower()
    return any(needle in reason or needle in lowered for needle in needles)


def _lineage_reason_class(reason: Optional[str]) -> str:
    if not reason:
        return "unavailable_unknown"
    if _reason_mentions(reason, "InvalidSyntaxException", "unparsable"):
        return "dialect_or_syntax"
    if _reason_mentions(reason, "contested"):
        return "contested_refuse"
    if _reason_mentions(reason, "not found", "no entity"):
        return "entity_lookup"
    return "unavailable_other"


def _dominant_failure_stratum(lin: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Pick the mode failure_taxonomy reason for design_reopen (callable R_lin)."""
    taxonomy = {
        reason: count
        for reason, count in (lin.get("failure_taxonomy") or {}).items()
        if reason != "null_query"
    }
    if not taxonomy:
        taxonomy = lin.get("failure_taxonomy") or {}
    if not taxonomy:
        return None
    reason, count = max(taxonomy.items(), key=lambda item: item[1])
    return {"reason_class": reason, "count": count}


def _null_query_outcome(
    row: Mapping[str, Any],
    *,
    query_kind: str,
    scoring_env: ScoringEnv | str,
) -> tuple[str, bool, Dict[str, Any], str]:
    failure = {
        "layer": "lineage",
        "stratum": "null_query",
        "reason_class": "null_query",
        "file": row.get("file"),
        "line": row.get("line"),
        "query_kind": query_kind,
    }
    # Pooled folds uncallable rows into native as failed trials.
    stratum = "native" if scoring_env == SCORING_ENV_POOLED else "null_query"
    return stratum, False, failure, "null_query"


def _unavailable_lineage_failure(
    row: Mapping[str, Any],
    *,
    stratum: str,
    query_kind: str,
    lineage: Mapping[str, Any],
) -> Tuple[Dict[str, Any], str]:
    reason_class = _lineage_reason_class(
        lineage.get("reason") if isinstance(lineage, Mapping) else None
    )
    failure = {
        "layer": "lineage",
        "stratum": stratum,
        "reason_class": reason_class,
        "file": row.get("file"),
        "line": row.get("line"),
        "query_kind": query_kind,
        "reason": (lineage.get("reason") if isinstance(lineage, Mapping) else None),
    }
    return failure, reason_class


def _lineage_row_outcome(
    row: Mapping[str, Any],
    *,
    scoring_env: ScoringEnv | str,
) -> tuple[str, bool, Optional[Dict[str, Any]], Optional[str]]:
    """Classify one raw_queries row for R_lin.

    Returns (stratum, available, failure_or_None, taxonomy_key_or_None).
    """
    query = row.get("query")
    query_kind = str(row.get("query_kind") or "other")
    lineage = row.get("lineage") if isinstance(row.get("lineage"), Mapping) else {}
    available = bool(lineage.get("available"))

    if query is None:
        return _null_query_outcome(row, query_kind=query_kind, scoring_env=scoring_env)

    stratum = query_kind if query_kind in {"native", "jpql"} else "other"
    if available:
        return stratum, True, None, None
    failure, reason_class = _unavailable_lineage_failure(
        row,
        stratum=stratum,
        query_kind=query_kind,
        lineage=lineage,
    )
    return stratum, False, failure, reason_class


def _raw_query_rows(signals: Mapping[str, Any]) -> List[Any]:
    evidence = signals.get("evidence") or {}
    rows = evidence.get("raw_queries") if isinstance(evidence, Mapping) else None
    return rows if isinstance(rows, list) else []


def _bump_stratum_counts(
    strata: Dict[str, Dict[str, int]],
    *,
    stratum: str,
    available: bool,
) -> None:
    slot = strata.setdefault(stratum, {"available": 0, "total": 0})
    slot["total"] += 1
    if available:
        slot["available"] += 1


def _apply_lineage_row(
    row: Any,
    *,
    scoring_env: ScoringEnv | str,
    strata: Dict[str, Dict[str, int]],
    failures: List[Dict[str, Any]],
    taxonomy: Counter[str],
) -> None:
    if not isinstance(row, Mapping):
        return
    stratum, available, failure, taxonomy_key = _lineage_row_outcome(
        row, scoring_env=scoring_env,
    )
    _bump_stratum_counts(strata, stratum=stratum, available=available)
    if taxonomy_key is not None:
        taxonomy[taxonomy_key] += 1
    if failure is not None:
        failures.append(failure)


def _accumulate_lineage_trials(
    rows: Sequence[Any],
    *,
    scoring_env: ScoringEnv | str,
) -> Tuple[Dict[str, Dict[str, int]], List[Dict[str, Any]], Counter[str]]:
    strata: Dict[str, Dict[str, int]] = {}
    failures: List[Dict[str, Any]] = []
    taxonomy: Counter[str] = Counter()
    for row in rows:
        _apply_lineage_row(
            row,
            scoring_env=scoring_env,
            strata=strata,
            failures=failures,
            taxonomy=taxonomy,
        )
    return strata, failures, taxonomy


def _mean_slots_for_scoring_env(
    strata: Mapping[str, Dict[str, int]],
    scoring_env: ScoringEnv | str,
) -> Mapping[str, Dict[str, int]]:
    # Under callable, exclude null_query stratum from mean.
    if scoring_env == SCORING_ENV_CALLABLE:
        return {
            name: slot for name, slot in strata.items() if name != "null_query"
        }
    return strata


def _strata_rate_blocks(
    strata: Mapping[str, Dict[str, int]],
) -> Dict[str, Any]:
    return {
        stratum_name: _rate_block(slot["available"], slot["total"])
        for stratum_name, slot in sorted(strata.items())
    }


def measure_r_lin(
    signals: Mapping[str, Any],
    *,
    scoring_env: ScoringEnv | str = SCORING_ENV_CALLABLE,
) -> Dict[str, Any]:
    """Lineage rates under scoring environment `callable` (normative) or `pooled`."""
    if scoring_env not in {ScoringEnv.CALLABLE, ScoringEnv.POOLED}:
        raise ValueError(f"unknown scoring_env: {scoring_env}")

    strata, failures, taxonomy = _accumulate_lineage_trials(
        _raw_query_rows(signals),
        scoring_env=scoring_env,
    )
    mean_slots = _mean_slots_for_scoring_env(strata, scoring_env)
    weighted_numerator = sum(slot["available"] for slot in mean_slots.values())
    weighted_denominator = sum(slot["total"] for slot in mean_slots.values())

    return {
        "scoring_env": scoring_env,
        "strata": _strata_rate_blocks(strata),
        "mean_rate": _rate(weighted_numerator, weighted_denominator),
        "numerator": weighted_numerator,
        "denominator": weighted_denominator,
        "callable_denominator": weighted_denominator,
        "failure_taxonomy": dict(sorted(taxonomy.items())),
        "failures": failures,
    }
