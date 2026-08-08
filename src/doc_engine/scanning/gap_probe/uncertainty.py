"""U_w comparison index over Path A residuals (not Stage-0 completeness)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .common import (
    WEIGHT_CODE_DEP,
    WEIGHT_COLLISION,
    WEIGHT_JOIN,
    WEIGHT_LINEAGE,
)


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
    - ``comparison_index_imputed_missing_as_perfect`` — all four dens measured
      (historical formula; name kept for full-support path)
    """
    axis_values = {
        "coll": r_coll,
        "join": r_join,
        "lin": r_lin_mean,
        "code": r_code_dep,
    }
    measured_axes = [name for name, val in axis_values.items() if val is not None]
    imputed_axes = [name for name, val in axis_values.items() if val is None]
    abs_n = int(callable_absence)
    unp_n = int(unproven)
    unscored_s3 = abs_n > 0 or unp_n > 0

    if not measured_axes:
        claim = "vacuous_no_support"
        if unscored_s3:
            # Vacuous Path A dens but S3 stamps exist — still not a U value.
            claim = "vacuous_no_support_with_s3_stamps"
        return {
            "U": None,
            "claim": claim,
            "slot": "comparison_index",
            "support": [],
            "imputed_axes": list(axis_values),
            "callable_absence": abs_n,
            "unproven": unp_n,
            "note": (
                "U is null: no Path A rate dens were measured. "
                "Not Stage-0 completeness; not 'healthy'."
            ),
            "weights": {
                "w_c": WEIGHT_COLLISION,
                "w_j": WEIGHT_JOIN,
                "w_l": WEIGHT_LINEAGE,
                "w_d": WEIGHT_CODE_DEP,
            },
            "terms": {},
            "residuals": {
                "R_coll": None,
                "join_gap": None,
                "lineage_gap": None,
                "code_dep_gap": None,
            },
        }

    coll = r_coll if r_coll is not None else 0.0
    join = r_join if r_join is not None else 1.0
    lin = r_lin_mean if r_lin_mean is not None else 1.0
    code = r_code_dep if r_code_dep is not None else 1.0
    residuals = {
        "R_coll": coll,
        "join_gap": 1.0 - join,
        "lineage_gap": 1.0 - lin,
        "code_dep_gap": 1.0 - code,
    }
    u = (
        WEIGHT_COLLISION * coll
        + WEIGHT_JOIN * (1.0 - join)
        + WEIGHT_LINEAGE * (1.0 - lin)
        + WEIGHT_CODE_DEP * (1.0 - code)
    )
    if unscored_s3:
        claim = "comparison_index_with_unscored_s3"
    elif imputed_axes:
        claim = "comparison_index_partial_support"
    else:
        claim = "comparison_index_full_support"

    return {
        "U": u,
        "claim": claim,
        "slot": "comparison_index",
        "support": measured_axes,
        "imputed_axes": imputed_axes,
        "callable_absence": abs_n,
        "unproven": unp_n,
        "note": (
            "U_w compares Path A residuals only. Imputed axes treat missing dens "
            "as perfect. ABSENCE/UNPROVEN are not folded into U — when present, "
            "claim is comparison_index_with_unscored_s3. Not Stage-0 completeness."
        ),
        "weights": {
            "w_c": WEIGHT_COLLISION,
            "w_j": WEIGHT_JOIN,
            "w_l": WEIGHT_LINEAGE,
            "w_d": WEIGHT_CODE_DEP,
        },
        "terms": {
            "collision": WEIGHT_COLLISION * coll,
            "join_gap": WEIGHT_JOIN * (1.0 - join),
            "lineage_gap": WEIGHT_LINEAGE * (1.0 - lin),
            "code_dep_gap": WEIGHT_CODE_DEP * (1.0 - code),
        },
        "residuals": residuals,
    }
