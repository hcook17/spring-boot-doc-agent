"""Closed registry of Stage-0 gap rate measures (OCP extension point).

Add a new rate by appending a ``RegisteredMeasure`` here and implementing the
callable in its domain module — ``report.build_gap_report`` stays closed to
unrelated churn. Schema keys (``R_sym``, …) remain the encoding SoR.

Optional hooks let a measure contribute uncertainty inputs, ``design_reopen``
flags, and post-harvest failures without teaching ``build_gap_report`` each
``R_*`` block shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .absence_recall import (
    _astgrep_receipt_complete,
    _planted_recall_failures,
    _trusted_codeql_oracle_arm,
    measure_r_absence,
    measure_r_recall,
)
from .code_dep import measure_r_code_dep
from .common import SCORING_ENV_CALLABLE, SCORING_ENV_POOLED
from .join import measure_r_join
from .lineage import _dominant_failure_stratum, measure_r_lin
from .symbol_collision import measure_r_coll, measure_r_sym
from .uncertainty import compute_uncertainty


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

    key: str
    run: MeasureRunner
    project: RateProjector
    collect_failures: bool = True
    harvest_failures: Optional[FailureHook] = None
    uncertainty_inputs: Optional[UncertaintyInputs] = None
    design_reopen: Optional[DesignReopenHook] = None
    extra_failures: Optional[FailureHook] = None


def _project_rate_block(block: Mapping[str, Any], *_a: Any) -> Dict[str, Any]:
    return {
        "numerator": block["numerator"],
        "denominator": block["denominator"],
        "callable_denominator": block["callable_denominator"],
        "rate": block["rate"],
    }


def _default_harvest(block: Any, *_a: Any) -> List[Dict[str, Any]]:
    if isinstance(block, Mapping):
        return list(block.get("failures") or [])
    return []


def _run_sym(ctx: MeasureContext) -> Dict[str, Any]:
    return measure_r_sym(ctx.facts)


def _run_coll(ctx: MeasureContext) -> Dict[str, Any]:
    return measure_r_coll(ctx.signals)


def _uncertainty_coll(block: Mapping[str, Any], *_a: Any) -> Mapping[str, Any]:
    return {"r_coll": block["rate"]}


def _reopen_coll(block: Mapping[str, Any], *_a: Any) -> Mapping[str, Any]:
    return {"path_a_to_symbols": (block["rate"] or 0) > 0}


def _run_join(ctx: MeasureContext) -> Dict[str, Any]:
    return measure_r_join(ctx.signals, ctx.facts)


def _uncertainty_join(block: Mapping[str, Any], *_a: Any) -> Mapping[str, Any]:
    return {"r_join": block["rate"]}


def _reopen_join(block: Mapping[str, Any], *_a: Any) -> Mapping[str, Any]:
    return {"join_incomplete": block["rate"] is None or block["rate"] < 1.0}


def _run_lin(ctx: MeasureContext) -> Dict[str, Any]:
    return {
        "callable": measure_r_lin(ctx.signals, scoring_env=SCORING_ENV_CALLABLE),
        "pooled": measure_r_lin(ctx.signals, scoring_env=SCORING_ENV_POOLED),
    }


def _project_lin(bundle: Mapping[str, Any], *_a: Any) -> Dict[str, Any]:
    lin = bundle["callable"]
    lin_pooled = bundle["pooled"]
    return {
        "scoring_env": SCORING_ENV_CALLABLE,
        "mean_rate": lin["mean_rate"],
        "numerator": lin["numerator"],
        "denominator": lin["denominator"],
        "callable_denominator": lin["callable_denominator"],
        "strata": lin["strata"],
        "failure_taxonomy": lin["failure_taxonomy"],
        "pooled_contrast": {
            "scoring_env": SCORING_ENV_POOLED,
            "mean_rate": lin_pooled["mean_rate"],
            "numerator": lin_pooled["numerator"],
            "denominator": lin_pooled["denominator"],
            "callable_denominator": lin_pooled["callable_denominator"],
            "strata": lin_pooled["strata"],
        },
    }


def _harvest_lin(bundle: Mapping[str, Any], *_a: Any) -> List[Dict[str, Any]]:
    # Failures live on the normative callable stratum only.
    return list((bundle.get("callable") or {}).get("failures") or [])


def _uncertainty_lin(bundle: Mapping[str, Any], *_a: Any) -> Mapping[str, Any]:
    return {"r_lin_mean": bundle["callable"]["mean_rate"]}


def _reopen_lin(bundle: Mapping[str, Any], *_a: Any) -> Mapping[str, Any]:
    return {"lineage_dominant_stratum": _dominant_failure_stratum(bundle["callable"])}


def _run_code_dep(ctx: MeasureContext) -> Dict[str, Any]:
    return measure_r_code_dep(ctx.signals)


def _project_code_dep(block: Mapping[str, Any], *_a: Any) -> Dict[str, Any]:
    out = _project_rate_block(block)
    out["per_family"] = block["per_family"]
    return out


def _uncertainty_code_dep(block: Mapping[str, Any], *_a: Any) -> Mapping[str, Any]:
    return {"r_code_dep": block["rate"]}


def _run_absence(ctx: MeasureContext) -> Dict[str, Any]:
    return measure_r_absence(ctx.facts, callable_trials=ctx.callable_trials)


def _project_absence(block: Mapping[str, Any], ctx: MeasureContext) -> Dict[str, Any]:
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


def _uncertainty_absence(block: Mapping[str, Any], *_a: Any) -> Mapping[str, Any]:
    return {
        "callable_absence": int(block["callable_absence"]),
        "unproven": int(block["unproven"]),
    }


def _reopen_absence(block: Mapping[str, Any], *_a: Any) -> Mapping[str, Any]:
    return {
        "unproven_present": bool(block["unproven"]),
        "absence_present": bool(block["callable_absence"]),
        "r_absence_failure_mass": block.get("rate"),
    }


def _run_recall(ctx: MeasureContext) -> Optional[Dict[str, Any]]:
    return measure_r_recall(ctx.facts, oracle_arm_present=ctx.oracle_arm)


def _project_recall(
    block: Optional[Mapping[str, Any]], ctx: MeasureContext
) -> Dict[str, Any]:
    if block is not None:
        return {
            "numerator": block["numerator"],
            "denominator": block["denominator"],
            "callable_denominator": block["callable_denominator"],
            "rate": block["rate"],
            "structural": block["structural"],
            "evidentiary": block["evidentiary"],
            "omitted": False,
            "claim": "measured",
        }
    if ctx.planted_misses > 0:
        return {
            "numerator": 0,
            "denominator": 0,
            "callable_denominator": 0,
            "rate": None,
            "omitted": True,
            "claim": "untrusted_planted",
            "note": (
                "Planted RECALL_MISS stamps are not an oracle. "
                "R_recall stays omitted until a trusted CodeQL receipt is present."
            ),
        }
    return {
        "numerator": 0,
        "denominator": 0,
        "callable_denominator": 0,
        "rate": None,
        "omitted": True,
        "claim": "omitted_without_oracle",
        "note": "R_recall requires a trusted CodeQL covering receipt",
    }


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
    RegisteredMeasure("R_sym", _run_sym, _project_rate_block),
    RegisteredMeasure(
        "R_coll",
        _run_coll,
        _project_rate_block,
        uncertainty_inputs=_uncertainty_coll,
        design_reopen=_reopen_coll,
    ),
    RegisteredMeasure(
        "R_join",
        _run_join,
        _project_rate_block,
        uncertainty_inputs=_uncertainty_join,
        design_reopen=_reopen_join,
    ),
    RegisteredMeasure(
        "R_lin",
        _run_lin,
        _project_lin,
        harvest_failures=_harvest_lin,
        uncertainty_inputs=_uncertainty_lin,
        design_reopen=_reopen_lin,
    ),
    RegisteredMeasure(
        "R_code_dep",
        _run_code_dep,
        _project_code_dep,
        uncertainty_inputs=_uncertainty_code_dep,
    ),
    RegisteredMeasure(
        "R_absence",
        _run_absence,
        _project_absence,
        uncertainty_inputs=_uncertainty_absence,
        design_reopen=_reopen_absence,
    ),
    RegisteredMeasure(
        "R_recall",
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


_U_DEFAULTS: Dict[str, Any] = {
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
    planted = sum(1 for fact in facts if fact.get("predicate") == "RECALL_MISS")
    return MeasureContext(
        signals=signals,
        facts=facts,
        covering_proof=covering_proof,
        covering_ok=covering_ok,
        astgrep_ok=_astgrep_receipt_complete(covering_proof),
        callable_trials=callable_trials,
        oracle_arm=_trusted_codeql_oracle_arm(covering_proof),
        planted_misses=planted,
    )


def run_rate_registry(ctx: MeasureContext) -> MeasuredRates:
    """Execute every registered measure; harvest primary + extra failures."""
    out = MeasuredRates()
    for spec in RATE_REGISTRY:
        block = spec.run(ctx)
        out.blocks[spec.key] = block
        out.rates[spec.key] = spec.project(block, ctx)
        if spec.collect_failures and block is not None:
            harvest = spec.harvest_failures or _default_harvest
            out.failures.extend(harvest(block, ctx))
        if spec.extra_failures is not None:
            out.failures.extend(spec.extra_failures(block, ctx))
    return out


def _fold_uncertainty(fragments: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Merge measure fragments into the closed U_w kwarg surface (formula SoR)."""
    merged = dict(_U_DEFAULTS)
    for frag in fragments:
        merged.update(frag)
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
    u_frags: List[Mapping[str, Any]] = []
    reopen: Dict[str, Any] = {}
    for spec in RATE_REGISTRY:
        block = measured.blocks[spec.key]
        if spec.uncertainty_inputs is not None:
            u_frags.append(spec.uncertainty_inputs(block, ctx))
        if spec.design_reopen is not None:
            reopen.update(spec.design_reopen(block, ctx))
    uncertainty = _fold_uncertainty(u_frags)
    reopen["vacuous_uncertainty"] = uncertainty.get("claim") == "vacuous_no_support"
    return GapViews(measured=measured, uncertainty=uncertainty, design_reopen=reopen)
