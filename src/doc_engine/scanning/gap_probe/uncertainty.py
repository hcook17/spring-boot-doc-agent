"""U_w comparison index over Path A residuals (not Stage-0 completeness)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from doc_engine._compat import StrEnum

from .common import (
    WEIGHT_CODE_DEP,
    WEIGHT_COLLISION,
    WEIGHT_JOIN,
    WEIGHT_LINEAGE,
)


class UncertaintyClaim(StrEnum):
    """Closed claim ladder for the U_w comparison index (worst wins upstream)."""

    VACUOUS_NO_SUPPORT = "vacuous_no_support"
    VACUOUS_NO_SUPPORT_WITH_S3 = "vacuous_no_support_with_s3_stamps"
    WITH_UNSCORED_S3 = "comparison_index_with_unscored_s3"
    PARTIAL_SUPPORT = "comparison_index_partial_support"
    FULL_SUPPORT = "comparison_index_full_support"


_WEIGHTS_BLOCK = {
    "w_c": WEIGHT_COLLISION,
    "w_j": WEIGHT_JOIN,
    "w_l": WEIGHT_LINEAGE,
    "w_d": WEIGHT_CODE_DEP,
}


def _vacuous_uncertainty_block(
    *,
    claim: UncertaintyClaim,
    callable_absence: int,
    unproven: int,
) -> Dict[str, Any]:
    return {
        "U": None,
        "claim": claim,
        "slot": "comparison_index",
        "support": [],
        "imputed_axes": ["coll", "join", "lin", "code"],
        "callable_absence": callable_absence,
        "unproven": unproven,
        "note": (
            "U is null: no Path A rate dens were measured. "
            "Not Stage-0 completeness; not 'healthy'."
        ),
        "weights": dict(_WEIGHTS_BLOCK),
        "terms": {},
        "residuals": {
            "R_coll": None,
            "join_gap": None,
            "lineage_gap": None,
            "code_dep_gap": None,
        },
    }


def _supported_claim(
    *,
    unscored_s3: bool,
    imputed_axes: List[str],
) -> UncertaintyClaim:
    if unscored_s3:
        return UncertaintyClaim.WITH_UNSCORED_S3
    if imputed_axes:
        return UncertaintyClaim.PARTIAL_SUPPORT
    return UncertaintyClaim.FULL_SUPPORT


def _supported_uncertainty_block(
    *,
    collision_rate: float,
    join_rate: float,
    lineage_rate: float,
    code_dep_rate: float,
    measured_axes: List[str],
    imputed_axes: List[str],
    callable_absence: int,
    unproven: int,
    unscored_s3: bool,
) -> Dict[str, Any]:
    residuals = {
        "R_coll": collision_rate,
        "join_gap": 1.0 - join_rate,
        "lineage_gap": 1.0 - lineage_rate,
        "code_dep_gap": 1.0 - code_dep_rate,
    }
    comparison_index = (
        WEIGHT_COLLISION * collision_rate
        + WEIGHT_JOIN * (1.0 - join_rate)
        + WEIGHT_LINEAGE * (1.0 - lineage_rate)
        + WEIGHT_CODE_DEP * (1.0 - code_dep_rate)
    )
    return {
        "U": comparison_index,
        "claim": _supported_claim(unscored_s3=unscored_s3, imputed_axes=imputed_axes),
        "slot": "comparison_index",
        "support": measured_axes,
        "imputed_axes": imputed_axes,
        "callable_absence": callable_absence,
        "unproven": unproven,
        "note": (
            "U_w compares Path A residuals only. Imputed axes treat missing dens "
            "as perfect. ABSENCE/UNPROVEN are not folded into U — when present, "
            "claim is comparison_index_with_unscored_s3. Not Stage-0 completeness."
        ),
        "weights": dict(_WEIGHTS_BLOCK),
        "terms": {
            "collision": WEIGHT_COLLISION * collision_rate,
            "join_gap": WEIGHT_JOIN * (1.0 - join_rate),
            "lineage_gap": WEIGHT_LINEAGE * (1.0 - lineage_rate),
            "code_dep_gap": WEIGHT_CODE_DEP * (1.0 - code_dep_rate),
        },
        "residuals": residuals,
    }


def _partition_axes(
    axis_values: Dict[str, Optional[float]],
) -> Tuple[List[str], List[str]]:
    measured = [name for name, value in axis_values.items() if value is not None]
    imputed = [name for name, value in axis_values.items() if value is None]
    return measured, imputed


def _vacuous_claim(unscored_s3: bool) -> UncertaintyClaim:
    if unscored_s3:
        return UncertaintyClaim.VACUOUS_NO_SUPPORT_WITH_S3
    return UncertaintyClaim.VACUOUS_NO_SUPPORT


def _imputed_or(value: Optional[float], default: float) -> float:
    return default if value is None else value


def compute_uncertainty(
    r_coll: Optional[float],
    r_join: Optional[float],
    r_lin_mean: Optional[float],
    r_code_dep: Optional[float],
    *,
    callable_absence: int = 0,
    unproven: int = 0,
) -> Dict[str, Any]:
    """U_w comparison index — not Stage-0 completeness.

    Claim ladder (worst wins):
    - ``vacuous_no_support`` — every dens undefined → U null (never 0.0)
    - ``comparison_index_with_unscored_s3`` — ABSENCE/UNPROVEN present; not in U
    - ``comparison_index_partial_support`` — some dens measured, others imputed
    - ``comparison_index_full_support`` — all four dens measured
    """
    measured_axes, imputed_axes = _partition_axes(
        {
            "coll": r_coll,
            "join": r_join,
            "lin": r_lin_mean,
            "code": r_code_dep,
        }
    )
    absence_count = int(callable_absence)
    unproven_count = int(unproven)
    unscored_s3 = absence_count > 0 or unproven_count > 0

    if not measured_axes:
        return _vacuous_uncertainty_block(
            claim=_vacuous_claim(unscored_s3),
            callable_absence=absence_count,
            unproven=unproven_count,
        )

    return _supported_uncertainty_block(
        collision_rate=_imputed_or(r_coll, 0.0),
        join_rate=_imputed_or(r_join, 1.0),
        lineage_rate=_imputed_or(r_lin_mean, 1.0),
        code_dep_rate=_imputed_or(r_code_dep, 1.0),
        measured_axes=measured_axes,
        imputed_axes=imputed_axes,
        callable_absence=absence_count,
        unproven=unproven_count,
        unscored_s3=unscored_s3,
    )
