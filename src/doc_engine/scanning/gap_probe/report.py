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
    SCORING_ENV_CALLABLE,
    SCORING_ENV_POOLED,
    CoveringPreconditionError,
    _load_facts_jsonl,
    _load_json,
    _maps_to,
)
from .failures import apply_failure_budget, sort_failures
from .registry import assemble_gap_views, prepare_measure_context


def _delta_rate(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return a - b


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
    if not covering_ok:
        raise CoveringPreconditionError(
            f"S1 covering proof failed; refusing S2 rates: {covering_why or 'unknown'}"
        )

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
    rates_proj = views.measured.rates
    uncertainty = views.uncertainty
    failures = sort_failures(list(views.measured.failures))
    kept, truncation = apply_failure_budget(failures, failure_budget, must_keep)

    # Scoring-env contrast is R_lin-specific (identity rates invariant elsewhere).
    lin = rates_proj["R_lin"]
    lin_pooled = lin["pooled_contrast"]
    delta_r = {
        "scoring_env_from": SCORING_ENV_POOLED,
        "scoring_env_to": SCORING_ENV_CALLABLE,
        "R_lin_mean": _delta_rate(lin["mean_rate"], lin_pooled["mean_rate"]),
        "R_lin_denominator_callable": lin["denominator"],
        "R_lin_denominator_pooled": lin_pooled["denominator"],
        "R_sym": 0.0,
        "R_coll": 0.0,
        "R_join": 0.0,
        "note": "Identity rates invariant under scoring-env; only lineage mean/denom move.",
    }

    entity_map = signals.get("entity_table_map") or {}
    absence = rates_proj["R_absence"]
    recall = rates_proj["R_recall"]
    rates: Dict[str, Any] = dict(rates_proj)
    rates["oracle"] = {
        "trusted_codeql_arm": ctx.oracle_arm,
        "planted_recall_miss_count": ctx.planted_misses,
        "astgrep_receipt_complete": ctx.astgrep_ok,
    }

    design_reopen = dict(views.design_reopen)
    design_reopen["truncation_alarm"] = truncation["truncation_alarm"]

    report = {
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
        "counts": {
            "entity_table_map": len(entity_map) if isinstance(entity_map, Mapping) else 0,
            "maps_to": len(_maps_to(facts)),
            "raw_queries": len((signals.get("evidence") or {}).get("raw_queries") or [])
            if isinstance(signals.get("evidence"), Mapping)
            else 0,
            "absence": absence["callable_absence"],
            "unproven": absence["unproven"],
            "recall_miss": 0 if recall.get("omitted") else recall.get("denominator", 0),
        },
        "rates": rates,
        "uncertainty": uncertainty,
        "measurement": {
            "residuals": uncertainty["residuals"],
            "comparison_index": {
                "U": uncertainty["U"],
                "claim": uncertainty.get("claim"),
                "slot": "comparison_index",
            },
            "delta_r_scoring_env": delta_r,
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
    with failures_path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in failures:
            fh.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
            fh.write("\n")


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
    proof, ok, why = load_and_verify_covering(
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
        covering_ok=ok,
        covering_why=why,
    )
    write_gap_report(out_dir, report, failures)
    return report
