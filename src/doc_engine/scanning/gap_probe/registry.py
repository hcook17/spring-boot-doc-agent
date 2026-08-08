"""Closed registry of Stage-0 gap rate measures (OCP extension point).

Add a new rate by appending a ``RegisteredMeasure`` here and implementing the
callable in its domain module — ``report.build_gap_report`` stays closed to
unrelated churn. Schema keys (``R_sym``, …) remain the encoding SoR via
``RateKey``.

Optional hooks let a measure contribute uncertainty inputs, ``design_reopen``
flags, and post-harvest failures without teaching ``build_gap_report`` each
``R_*`` block shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from doc_engine._compat import StrEnum

from .absence_recall import (
    _astgrep_receipt_complete,
    _planted_recall_failures,
    _trusted_codeql_oracle_arm,
    measure_r_absence,
    measure_r_recall,
)
from .code_dep import measure_r_code_dep
from .common import RateKey, ScoringEnv
from .join import measure_r_join
from .lineage import _dominant_failure_stratum, measure_r_lin
from .symbol_collision import measure_r_coll, measure_r_sym
from .uncertainty import UncertaintyClaim, compute_uncertainty


class RecallClaim(StrEnum):
    """Closed claim stamps for the R_recall projection."""

    MEASURED = "measured"
    UNTRUSTED_PLANTED = "untrusted_planted"
    OMITTED_WITHOUT_ORACLE = "omitted_without_oracle"


@dataclass
class MeasureContext:
    """Shared inputs for registered rate callables."""

    signals: Mapping[str, Any]
    facts: Sequence[Mapping[str, Any]]
    covering_proof: Optional[Mapping[str, Any]] = None
    covering_ok: bool = False
    astgrep_ok: bool = False
    callable_trials: Optional[int] = None
    oracle_arm: bool = False
    planted_misses: int = 0


MeasureRunner = Callable[[MeasureContext], Any]
RateProjector = Callable[[Any, MeasureContext], Dict[str, Any]]
# Fragments merge into compute_uncertainty kwargs (Path A dens + S3 stamps).
UncertaintyInputs = Callable[[Any, MeasureContext], Mapping[str, Any]]
DesignReopenHook = Callable[[Any, MeasureContext], Mapping[str, Any]]
FailureHook = Callable[[Any, MeasureContext], Sequence[Mapping[str, Any]]]


@dataclass(frozen=True)
class RegisteredMeasure:
    """One gap-probe rate: run → project + optional assembly hooks."""

    key: RateKey
    run: MeasureRunner
    project: RateProjector
    collect_failures: bool = True
    harvest_failures: Optional[FailureHook] = None
    uncertainty_inputs: Optional[UncertaintyInputs] = None
    design_reopen: Optional[DesignReopenHook] = None
    extra_failures: Optional[FailureHook] = None


def _project_rate_block(
    block: Mapping[str, Any], _ctx: MeasureContext
) -> Dict[str, Any]:
    return {
        "numerator": block["numerator"],
        "denominator": block["denominator"],
        "callable_denominator": block["callable_denominator"],
        "rate": block["rate"],
    }


def _default_harvest(
    block: Any, _ctx: MeasureContext
) -> List[Dict[str, Any]]:
    if isinstance(block, Mapping):
        return list(block.get("failures") or [])
    return []


def _run_sym(ctx: MeasureContext) -> Dict[str, Any]:
    return measure_r_sym(ctx.facts)


def _run_coll(ctx: MeasureContext) -> Dict[str, Any]:
    return measure_r_coll(ctx.signals)


def _uncertainty_coll(
    block: Mapping[str, Any], _ctx: MeasureContext
) -> Mapping[str, Any]:
    return {"r_coll": block["rate"]}


def _reopen_coll(
    block: Mapping[str, Any], _ctx: MeasureContext
) -> Mapping[str, Any]:
    return {"path_a_to_symbols": (block["rate"] or 0) > 0}


def _run_join(ctx: MeasureContext) -> Dict[str, Any]:
    return measure_r_join(ctx.signals, ctx.facts)


def _uncertainty_join(
    block: Mapping[str, Any], _ctx: MeasureContext
) -> Mapping[str, Any]:
    return {"r_join": block["rate"]}


def _reopen_join(
    block: Mapping[str, Any], _ctx: MeasureContext
) -> Mapping[str, Any]:
    return {"join_incomplete": block["rate"] is None or block["rate"] < 1.0}


def _run_lin(ctx: MeasureContext) -> Dict[str, Any]:
    return {
        "callable": measure_r_lin(ctx.signals, scoring_env=ScoringEnv.CALLABLE),
        "pooled": measure_r_lin(ctx.signals, scoring_env=ScoringEnv.POOLED),
    }


def _lineage_core_fields(lineage_block: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "mean_rate": lineage_block["mean_rate"],
        "numerator": lineage_block["numerator"],
        "denominator": lineage_block["denominator"],
        "callable_denominator": lineage_block["callable_denominator"],
        "strata": lineage_block["strata"],
    }


def _project_lin(
    bundle: Mapping[str, Any], _ctx: MeasureContext
) -> Dict[str, Any]:
    callable_lineage = bundle["callable"]
    pooled_lineage = bundle["pooled"]
    return {
        "scoring_env": ScoringEnv.CALLABLE,
        **_lineage_core_fields(callable_lineage),
        "failure_taxonomy": callable_lineage["failure_taxonomy"],
        "pooled_contrast": {
            "scoring_env": ScoringEnv.POOLED,
            **_lineage_core_fields(pooled_lineage),
        },
    }


def _harvest_lin(
    bundle: Mapping[str, Any], _ctx: MeasureContext
) -> List[Dict[str, Any]]:
    # Failures live on the normative callable stratum only.
    return list((bundle.get("callable") or {}).get("failures") or [])


def _uncertainty_lin(
    bundle: Mapping[str, Any], _ctx: MeasureContext
) -> Mapping[str, Any]:
    return {"r_lin_mean": bundle["callable"]["mean_rate"]}


def _reopen_lin(
    bundle: Mapping[str, Any], _ctx: MeasureContext
) -> Mapping[str, Any]:
    return {
        "lineage_dominant_stratum": _dominant_failure_stratum(bundle["callable"]),
    }


def _run_code_dep(ctx: MeasureContext) -> Dict[str, Any]:
    return measure_r_code_dep(ctx.signals)


def _project_code_dep(
    block: Mapping[str, Any], ctx: MeasureContext
) -> Dict[str, Any]:
    projected = _project_rate_block(block, ctx)
    projected["per_family"] = block["per_family"]
    return projected


def _uncertainty_code_dep(
    block: Mapping[str, Any], _ctx: MeasureContext
) -> Mapping[str, Any]:
    return {"r_code_dep": block["rate"]}


def _run_absence(ctx: MeasureContext) -> Dict[str, Any]:
    return measure_r_absence(ctx.facts, callable_trials=ctx.callable_trials)


def _project_absence(
    block: Mapping[str, Any], ctx: MeasureContext
) -> Dict[str, Any]:
    return {
        "numerator": block["numerator"],
        "denominator": block["denominator"],
        "callable_denominator": block["callable_denominator"],
        "rate": block["rate"],
        "callable_absence": block["callable_absence"],
        "callable_trials": ctx.callable_trials,
        "unproven": block["unproven"],
        "polarity": "failure_mass",
        "omitted": block["rate"] is None,
        "note": block["note"],
    }


def _uncertainty_absence(
    block: Mapping[str, Any], _ctx: MeasureContext
) -> Mapping[str, Any]:
    return {
        "callable_absence": int(block["callable_absence"]),
        "unproven": int(block["unproven"]),
    }


def _reopen_absence(
    block: Mapping[str, Any], _ctx: MeasureContext
) -> Mapping[str, Any]:
    return {
        "unproven_present": bool(block["unproven"]),
        "absence_present": bool(block["callable_absence"]),
        "r_absence_failure_mass": block.get("rate"),
    }


def _run_recall(ctx: MeasureContext) -> Optional[Dict[str, Any]]:
    return measure_r_recall(ctx.facts, oracle_arm_present=ctx.oracle_arm)


def _measured_recall_projection(block: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "numerator": block["numerator"],
        "denominator": block["denominator"],
        "callable_denominator": block["callable_denominator"],
        "rate": block["rate"],
        "structural": block["structural"],
        "evidentiary": block["evidentiary"],
        "omitted": False,
        "claim": RecallClaim.MEASURED,
    }


def _omitted_recall_projection(*, claim: RecallClaim, note: str) -> Dict[str, Any]:
    return {
        "numerator": 0,
        "denominator": 0,
        "callable_denominator": 0,
        "rate": None,
        "omitted": True,
        "claim": claim,
        "note": note,
    }


def _project_recall(
    block: Optional[Mapping[str, Any]], ctx: MeasureContext
) -> Dict[str, Any]:
    if block is not None:
        return _measured_recall_projection(block)
    if ctx.planted_misses > 0:
        return _omitted_recall_projection(
            claim=RecallClaim.UNTRUSTED_PLANTED,
            note=(
                "Planted RECALL_MISS stamps are not an oracle. "
                "R_recall stays omitted until a trusted CodeQL receipt is present."
            ),
        )
    return _omitted_recall_projection(
        claim=RecallClaim.OMITTED_WITHOUT_ORACLE,
        note="R_recall requires a trusted CodeQL covering receipt",
    )


def _reopen_recall(
    block: Optional[Mapping[str, Any]], ctx: MeasureContext
) -> Mapping[str, Any]:
    return {
        "structural_recall_misses": bool(block and block.get("structural")),
        "untrusted_planted_recall": bool(ctx.planted_misses and not ctx.oracle_arm),
    }


def _extra_recall(
    block: Optional[Mapping[str, Any]], ctx: MeasureContext
) -> Sequence[Mapping[str, Any]]:
    if block is None and ctx.planted_misses > 0:
        return _planted_recall_failures(ctx.facts)
    return []


# Extension point: append a RegisteredMeasure for a new R_* family.
RATE_REGISTRY: tuple[RegisteredMeasure, ...] = (
    RegisteredMeasure(RateKey.SYM, _run_sym, _project_rate_block),
    RegisteredMeasure(
        RateKey.COLL,
        _run_coll,
        _project_rate_block,
        uncertainty_inputs=_uncertainty_coll,
        design_reopen=_reopen_coll,
    ),
    RegisteredMeasure(
        RateKey.JOIN,
        _run_join,
        _project_rate_block,
        uncertainty_inputs=_uncertainty_join,
        design_reopen=_reopen_join,
    ),
    RegisteredMeasure(
        RateKey.LIN,
        _run_lin,
        _project_lin,
        harvest_failures=_harvest_lin,
        uncertainty_inputs=_uncertainty_lin,
        design_reopen=_reopen_lin,
    ),
    RegisteredMeasure(
        RateKey.CODE_DEP,
        _run_code_dep,
        _project_code_dep,
        uncertainty_inputs=_uncertainty_code_dep,
    ),
    RegisteredMeasure(
        RateKey.ABSENCE,
        _run_absence,
        _project_absence,
        uncertainty_inputs=_uncertainty_absence,
        design_reopen=_reopen_absence,
    ),
    RegisteredMeasure(
        RateKey.RECALL,
        _run_recall,
        _project_recall,
        design_reopen=_reopen_recall,
        extra_failures=_extra_recall,
    ),
)


@dataclass
class MeasuredRates:
    """Result of running ``RATE_REGISTRY`` once over a context."""

    blocks: Dict[str, Any] = field(default_factory=dict)
    rates: Dict[str, Any] = field(default_factory=dict)
    failures: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class GapViews:
    """Rates plus folded uncertainty / design_reopen from registry hooks.

    ``design_reopen`` holds measure-contributed flags and ``vacuous_uncertainty``.
    Report assembly still adds ``truncation_alarm`` after the failure budget.
    """

    measured: MeasuredRates
    uncertainty: Dict[str, Any]
    design_reopen: Dict[str, Any]


_UNCERTAINTY_DEFAULTS: Dict[str, Any] = {
    "r_coll": None,
    "r_join": None,
    "r_lin_mean": None,
    "r_code_dep": None,
    "callable_absence": 0,
    "unproven": 0,
}


def prepare_measure_context(
    signals: Mapping[str, Any],
    facts: Sequence[Mapping[str, Any]],
    *,
    covering_proof: Optional[Mapping[str, Any]],
    covering_ok: bool,
    callable_trials: int,
) -> MeasureContext:
    """Fill covering/oracle fields shared by registered measures."""
    planted_misses = sum(
        1 for fact in facts if fact.get("predicate") == "RECALL_MISS"
    )
    return MeasureContext(
        signals=signals,
        facts=facts,
        covering_proof=covering_proof,
        covering_ok=covering_ok,
        astgrep_ok=_astgrep_receipt_complete(covering_proof),
        callable_trials=callable_trials,
        oracle_arm=_trusted_codeql_oracle_arm(covering_proof),
        planted_misses=planted_misses,
    )


def _harvest_measure_failures(
    measure: RegisteredMeasure,
    block: Any,
    ctx: MeasureContext,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if measure.collect_failures and block is not None:
        harvest = measure.harvest_failures or _default_harvest
        rows.extend(harvest(block, ctx))
    if measure.extra_failures is not None:
        rows.extend(measure.extra_failures(block, ctx))
    return rows


def _run_one_measure(
    measure: RegisteredMeasure,
    ctx: MeasureContext,
    measured: MeasuredRates,
) -> None:
    block = measure.run(ctx)
    measured.blocks[measure.key] = block
    measured.rates[measure.key] = measure.project(block, ctx)
    measured.failures.extend(_harvest_measure_failures(measure, block, ctx))


def run_rate_registry(ctx: MeasureContext) -> MeasuredRates:
    """Execute every registered measure; harvest primary + extra failures."""
    measured = MeasuredRates()
    for measure in RATE_REGISTRY:
        _run_one_measure(measure, ctx, measured)
    return measured


def _fold_uncertainty(fragments: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Merge measure fragments into the closed U_w kwarg surface (formula SoR)."""
    merged = dict(_UNCERTAINTY_DEFAULTS)
    for fragment in fragments:
        merged.update(fragment)
    return compute_uncertainty(
        merged["r_coll"],
        merged["r_join"],
        merged["r_lin_mean"],
        merged["r_code_dep"],
        callable_absence=int(merged["callable_absence"]),
        unproven=int(merged["unproven"]),
    )


def assemble_gap_views(ctx: MeasureContext) -> GapViews:
    """Run registry then fold uncertainty / design_reopen via measure hooks."""
    measured = run_rate_registry(ctx)
    uncertainty_fragments: List[Mapping[str, Any]] = []
    design_reopen: Dict[str, Any] = {}
    for measure in RATE_REGISTRY:
        block = measured.blocks[measure.key]
        if measure.uncertainty_inputs is not None:
            uncertainty_fragments.append(measure.uncertainty_inputs(block, ctx))
        if measure.design_reopen is not None:
            design_reopen.update(measure.design_reopen(block, ctx))
    uncertainty = _fold_uncertainty(uncertainty_fragments)
    design_reopen["vacuous_uncertainty"] = (
        uncertainty.get("claim") == UncertaintyClaim.VACUOUS_NO_SUPPORT
    )
    return GapViews(
        measured=measured,
        uncertainty=uncertainty,
        design_reopen=design_reopen,
    )
