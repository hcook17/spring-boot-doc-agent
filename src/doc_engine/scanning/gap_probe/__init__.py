"""Stage-0 gap measurement probe (AET / DDIA rates with closed denominators).

Derived Stage-0 rate views over signals/facts SoR; domain modules per rate
family (DDIA maintainability / SoR-vs-derived). Public import path
``doc_engine.scanning.gap_probe`` stays stable after the package split.

See claude/research/aet-measurement-2026-07-30.md
and claude/research/gap-probe-measurement-design-2026-07-30.md.
"""

from __future__ import annotations

from .absence_recall import (
    _astgrep_receipt_complete,
    _trusted_codeql_oracle_arm,
    load_and_verify_covering,
    measure_r_absence,
    measure_r_recall,
)
from .code_dep import (
    _code_keyword_hits_for_family,
    _count_deployment_families,
    measure_r_code_dep,
)
from .common import (
    _CODE_BUCKET_BY_FAMILY,
    _DEP_FAMILY_PATTERNS,
    GAP_PROBE_SCHEMA_VERSION,
    SCORING_ENV_CALLABLE,
    SCORING_ENV_POOLED,
    WEIGHT_CODE_DEP,
    WEIGHT_COLLISION,
    WEIGHT_JOIN,
    WEIGHT_LINEAGE,
    CoveringPreconditionError,
    RateKey,
    ScoringEnv,
    _load_facts_jsonl,
    _load_json,
    _maps_to,
    _rate,
    _rate_block,
)
from .failures import apply_failure_budget, failure_locator, sort_failures
from .join import _fact_identity_keys, measure_r_join
from .lineage import _dominant_failure_stratum, _lineage_reason_class, _lineage_row_outcome, measure_r_lin
from .registry import (
    RATE_REGISTRY,
    GapViews,
    MeasureContext,
    MeasuredRates,
    RecallClaim,
    RegisteredMeasure,
    assemble_gap_views,
    prepare_measure_context,
    run_rate_registry,
)
from .report import (
    _delta_rate,
    build_gap_report,
    run_gap_probe,
    write_gap_report,
)
from .symbol_collision import measure_r_coll, measure_r_sym
from .uncertainty import UncertaintyClaim, compute_uncertainty

__all__ = [
    "CoveringPreconditionError",
    "GAP_PROBE_SCHEMA_VERSION",
    "GapViews",
    "MeasuredRates",
    "MeasureContext",
    "RATE_REGISTRY",
    "RateKey",
    "RecallClaim",
    "RegisteredMeasure",
    "SCORING_ENV_CALLABLE",
    "SCORING_ENV_POOLED",
    "ScoringEnv",
    "UncertaintyClaim",
    "WEIGHT_CODE_DEP",
    "WEIGHT_COLLISION",
    "WEIGHT_JOIN",
    "WEIGHT_LINEAGE",
    "_CODE_BUCKET_BY_FAMILY",
    "_DEP_FAMILY_PATTERNS",
    "_astgrep_receipt_complete",
    "_code_keyword_hits_for_family",
    "_count_deployment_families",
    "_delta_rate",
    "_dominant_failure_stratum",
    "_fact_identity_keys",
    "_lineage_reason_class",
    "_lineage_row_outcome",
    "_load_facts_jsonl",
    "_load_json",
    "_maps_to",
    "_rate",
    "_rate_block",
    "_trusted_codeql_oracle_arm",
    "apply_failure_budget",
    "assemble_gap_views",
    "build_gap_report",
    "compute_uncertainty",
    "failure_locator",
    "load_and_verify_covering",
    "measure_r_absence",
    "measure_r_code_dep",
    "measure_r_coll",
    "measure_r_join",
    "measure_r_lin",
    "measure_r_recall",
    "measure_r_sym",
    "prepare_measure_context",
    "run_gap_probe",
    "run_rate_registry",
    "sort_failures",
    "write_gap_report",
]
