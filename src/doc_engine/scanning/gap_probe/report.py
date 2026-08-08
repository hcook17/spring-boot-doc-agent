"""Assemble gap_report.json / gap_failures.jsonl from Stage-0 rate measures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from doc_engine.pipeline.artifacts import FACTS_LEDGER_SCHEMA_VERSION
from doc_engine.scanning.absence import count_callable_trials
from doc_engine.scanning.covering import COVERING_PROOF_SCHEMA_VERSION

from .absence_recall import _astgrep_receipt_complete, load_and_verify_covering
from .common import (
    GAP_PROBE_SCHEMA_VERSION,
    CoveringPreconditionError,
    RateKey,
    ScoringEnv,
    _load_facts_jsonl,
    _load_json,
    _maps_to,
)
from .failures import apply_failure_budget, sort_failures
from .registry import GapViews, assemble_gap_views, prepare_measure_context


def _delta_rate(left: Optional[float], right: Optional[float]) -> Optional[float]:
    if left is None or right is None:
        return None
    return left - right


def _require_covering_ok(*, covering_ok: bool, covering_why: str) -> None:
    if not covering_ok:
        raise CoveringPreconditionError(
            f"S1 covering proof failed; refusing S2 rates: {covering_why or 'unknown'}"
        )


def _scoring_env_delta(lineage_rate: Mapping[str, Any]) -> Dict[str, Any]:
    """Contrast callable vs pooled R_lin; identity rates stay invariant."""
    pooled = lineage_rate["pooled_contrast"]
    return {
        "scoring_env_from": ScoringEnv.POOLED,
        "scoring_env_to": ScoringEnv.CALLABLE,
        "R_lin_mean": _delta_rate(lineage_rate["mean_rate"], pooled["mean_rate"]),
        "R_lin_denominator_callable": lineage_rate["denominator"],
        "R_lin_denominator_pooled": pooled["denominator"],
        RateKey.SYM: 0.0,
        RateKey.COLL: 0.0,
        RateKey.JOIN: 0.0,
        "note": (
            "Identity rates invariant under scoring-env; only lineage mean/denom move."
        ),
    }


def _report_counts(
    signals: Mapping[str, Any],
    facts: Sequence[Mapping[str, Any]],
    *,
    absence_rate: Mapping[str, Any],
    recall_rate: Mapping[str, Any],
) -> Dict[str, Any]:
    entity_map = signals.get("entity_table_map") or {}
    evidence = signals.get("evidence")
    raw_queries = (
        (evidence or {}).get("raw_queries") or []
        if isinstance(evidence, Mapping)
        else []
    )
    recall_miss = (
        0 if recall_rate.get("omitted") else recall_rate.get("denominator", 0)
    )
    return {
        "entity_table_map": (
            len(entity_map) if isinstance(entity_map, Mapping) else 0
        ),
        "maps_to": len(_maps_to(facts)),
        "raw_queries": len(raw_queries),
        "absence": absence_rate["callable_absence"],
        "unproven": absence_rate["unproven"],
        "recall_miss": recall_miss,
    }


def _assemble_report_document(
    *,
    signals: Mapping[str, Any],
    facts: Sequence[Mapping[str, Any]],
    views: GapViews,
    kept_rates: Dict[str, Any],
    design_reopen: Dict[str, Any],
    truncation: Mapping[str, Any],
    signals_path: Optional[str],
    facts_path: Optional[str],
    covering_proof: Optional[Mapping[str, Any]],
    covering_ok: bool,
) -> Dict[str, Any]:
    uncertainty = views.uncertainty
    return {
        "schema_version": GAP_PROBE_SCHEMA_VERSION,
        "gap_probe_schema_version": GAP_PROBE_SCHEMA_VERSION,
        "facts_ledger_schema_version": FACTS_LEDGER_SCHEMA_VERSION,
        "signals_schema_version": signals.get("schema_version"),
        "scanner_version": signals.get("scanner_version"),
        "covering_proof_schema_version": COVERING_PROOF_SCHEMA_VERSION,
        "s1_covering": {
            # covering_ok alone is not proof — rate math may proceed, but
            # verified requires an actual covering_proof object (anti-lie).
            "verified": bool(covering_ok and covering_proof),
            "proof_present": bool(covering_proof),
            "inventory_root": (covering_proof or {}).get("inventory_root"),
        },
        "inputs": {
            "signals_path": signals_path,
            "facts_path": facts_path,
        },
        "counts": _report_counts(
            signals,
            facts,
            absence_rate=kept_rates[RateKey.ABSENCE],
            recall_rate=kept_rates[RateKey.RECALL],
        ),
        "rates": kept_rates,
        "uncertainty": uncertainty,
        "measurement": {
            "residuals": uncertainty["residuals"],
            "comparison_index": {
                "U": uncertainty["U"],
                "claim": uncertainty.get("claim"),
                "slot": "comparison_index",
            },
            "delta_r_scoring_env": _scoring_env_delta(kept_rates[RateKey.LIN]),
            "truncation": truncation,
            "note_U": (
                "U_w is a comparison index over Path A residuals — not Stage-0 "
                "completeness / covering proof. Vacuous dens ⇒ U null "
                "(claim=vacuous_no_support). Read uncertainty.callable_absence "
                "and uncertainty.unproven; they are not folded into U."
            ),
        },
        "design_reopen": design_reopen,
        "memo": "claude/research/aet-measurement-2026-07-30.md",
        "memo_rates": "claude/research/gap-probe-measurement-design-2026-07-30.md",
        "memo_covering": "claude/research/stage0-covering-absence-recall-2026-07-30.md",
    }


def build_gap_report(
    signals: Mapping[str, Any],
    facts: Sequence[Mapping[str, Any]],
    *,
    signals_path: Optional[str] = None,
    facts_path: Optional[str] = None,
    failure_budget: Optional[int] = None,
    must_keep: Optional[Sequence[str]] = None,
    covering_proof: Optional[Mapping[str, Any]] = None,
    covering_ok: bool = False,
    covering_why: str = "",
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    _require_covering_ok(covering_ok=covering_ok, covering_why=covering_why)

    # Pre-compute callable trial mass for R_absence (needs covering receipts).
    astgrep_ok = _astgrep_receipt_complete(covering_proof)
    callable_trials = count_callable_trials(
        signals,
        covering_ok=covering_ok,
        astgrep_receipt_complete=astgrep_ok,
    )
    ctx = prepare_measure_context(
        signals,
        facts,
        covering_proof=covering_proof,
        covering_ok=covering_ok,
        callable_trials=callable_trials,
    )

    views = assemble_gap_views(ctx)
    failures = sort_failures(list(views.measured.failures))
    kept, truncation = apply_failure_budget(failures, failure_budget, must_keep)

    rates: Dict[str, Any] = dict(views.measured.rates)
    rates["oracle"] = {
        "trusted_codeql_arm": ctx.oracle_arm,
        "planted_recall_miss_count": ctx.planted_misses,
        "astgrep_receipt_complete": ctx.astgrep_ok,
    }
    design_reopen = dict(views.design_reopen)
    design_reopen["truncation_alarm"] = truncation["truncation_alarm"]

    report = _assemble_report_document(
        signals=signals,
        facts=facts,
        views=views,
        kept_rates=rates,
        design_reopen=design_reopen,
        truncation=truncation,
        signals_path=signals_path,
        facts_path=facts_path,
        covering_proof=covering_proof,
        covering_ok=covering_ok,
    )
    return report, kept


def write_gap_report(
    out_dir: Path, report: Mapping[str, Any], failures: Sequence[Mapping[str, Any]]
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "gap_report.json"
    failures_path = out_dir / "gap_failures.jsonl"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with failures_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in failures:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def run_gap_probe(
    signals_path: Path,
    facts_path: Path,
    out_dir: Path,
    *,
    failure_budget: Optional[int] = None,
    must_keep: Optional[Sequence[str]] = None,
    covering_path: Optional[Path] = None,
) -> Dict[str, Any]:
    signals = _load_json(signals_path)
    facts = _load_facts_jsonl(facts_path)
    if not isinstance(signals, Mapping):
        raise ValueError("signals root must be a JSON object")
    proof, covering_ok, covering_why = load_and_verify_covering(
        signals,
        signals_path=signals_path,
        covering_path=covering_path,
    )
    report, failures = build_gap_report(
        signals,
        facts,
        signals_path=str(signals_path),
        facts_path=str(facts_path),
        failure_budget=failure_budget,
        must_keep=must_keep,
        covering_proof=proof,
        covering_ok=covering_ok,
        covering_why=covering_why,
    )
    write_gap_report(out_dir, report, failures)
    return report
