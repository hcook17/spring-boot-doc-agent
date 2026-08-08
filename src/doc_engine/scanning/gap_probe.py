"""Stage-0 gap measurement probe (AET / DDIA rates with closed denominators).

See claude/research/aet-measurement-2026-07-30.md
and claude/research/gap-probe-measurement-design-2026-07-30.md.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from doc_engine.pipeline.artifacts import FACTS_LEDGER_SCHEMA_VERSION
from doc_engine.scanning.absence import count_callable_trials
from doc_engine.scanning.covering import (
    COVERING_PROOF_SCHEMA_VERSION,
    covering_proof_path_for_signals_out,
    verify_covering_proof,
)
from doc_engine.scanning.symbol import SymbolError, parse


class CoveringPreconditionError(RuntimeError):
    """Raised when gap_probe cannot verify S1 covering before scoring S2."""

GAP_PROBE_SCHEMA_VERSION = 3

# Fixed uncertainty weights (policy) — do not tune per narrative.
WEIGHT_COLLISION = 0.30
WEIGHT_JOIN = 0.25
WEIGHT_LINEAGE = 0.30
WEIGHT_CODE_DEP = 0.15

SCORING_ENV_CALLABLE = "callable"
SCORING_ENV_POOLED = "pooled"

# Deployment / outbound match text → family for R_code|dep.
_DEP_FAMILY_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("redis", re.compile(r"redis", re.I)),
    ("actuator", re.compile(r"actuator", re.I)),
    ("feign", re.compile(r"feign|openfeign", re.I)),
    ("aws_secrets", re.compile(r"secretsmanager|aws.secrets", re.I)),
    ("messaging", re.compile(r"kafka|rabbit|amqp|jms", re.I)),
)

_CODE_BUCKET_BY_FAMILY: Dict[str, Tuple[str, ...]] = {
    "redis": ("observability", "configuration", "outbound_clients"),
    "actuator": ("observability", "configuration"),
    "feign": ("outbound_clients",),
    "aws_secrets": ("configuration", "security"),
    "messaging": ("messaging",),
}


def _rate(num: int, den: int) -> Optional[float]:
    if den <= 0:
        return None
    return num / den


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_facts_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _maps_to(facts: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return [f for f in facts if f.get("predicate") == "MAPS_TO"]


def _rate_block(num: int, den: int, **extra: Any) -> Dict[str, Any]:
    block: Dict[str, Any] = {
        "numerator": num,
        "denominator": den,
        "callable_denominator": den,
        "rate": _rate(num, den),
    }
    block.update(extra)
    return block


def measure_r_sym(facts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    maps = _maps_to(facts)
    ok = 0
    failures: List[Dict[str, Any]] = []
    for f in maps:
        subject = f.get("subject")
        try:
            parsed = parse(str(subject))
            if parsed.kind != "type":
                raise SymbolError(f"kind={parsed.kind}")
            ok += 1
        except SymbolError as exc:
            failures.append(
                {
                    "layer": "facts",
                    "stratum": "maps_to_symbol",
                    "reason_class": "unparseable_or_non_type",
                    "subject": subject,
                    "file": f.get("file"),
                    "detail": str(exc),
                }
            )
    den = len(maps)
    out = _rate_block(ok, den)
    out["failures"] = failures
    return out


def measure_r_coll(signals: Mapping[str, Any]) -> Dict[str, Any]:
    entity_map = signals.get("entity_table_map") or {}
    if not isinstance(entity_map, Mapping):
        entity_map = {}
    contested = 0
    failures: List[Dict[str, Any]] = []
    for name, entry in entity_map.items():
        if not isinstance(entry, Mapping):
            continue
        if entry.get("status") == "contested":
            contested += 1
            failures.append(
                {
                    "layer": "path_a",
                    "stratum": "collision",
                    "reason_class": "contested",
                    "simple_name": name,
                    "file": entry.get("file"),
                    "candidates": len(entry.get("candidates") or []),
                }
            )
    den = len(entity_map)
    out = _rate_block(contested, den)
    out["failures"] = failures
    return out


def _fact_identity_keys(fact: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    quals = fact.get("qualifiers") or {}
    if not isinstance(quals, Mapping):
        return keys
    fqcn = quals.get("fqcn")
    if fqcn:
        keys.add(f"fqcn:{fqcn}")
    display = quals.get("display_name")
    package = None
    try:
        parsed = parse(str(fact.get("subject")))
        package = ".".join(parsed.namespaces) if parsed.namespaces else None
        if display:
            keys.add(f"simple:{display}")
        if package and display:
            keys.add(f"pkg_simple:{package}|{display}")
    except SymbolError:
        if display:
            keys.add(f"simple:{display}")
    return keys


def measure_r_join(
    signals: Mapping[str, Any],
    facts: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    entity_map = signals.get("entity_table_map") or {}
    if not isinstance(entity_map, Mapping):
        entity_map = {}
    fact_keys: set[str] = set()
    for f in _maps_to(facts):
        fact_keys |= _fact_identity_keys(f)

    matched = 0
    failures: List[Dict[str, Any]] = []
    for name, entry in entity_map.items():
        if not isinstance(entry, Mapping):
            continue
        candidates = entry.get("candidates") if entry.get("status") == "contested" else None
        sources: List[Mapping[str, Any]] = (
            [c for c in candidates if isinstance(c, Mapping)]
            if isinstance(candidates, list) and candidates
            else [entry]
        )
        hit = False
        for src in sources:
            fqcn = src.get("fqcn") or entry.get("fqcn")
            package = src.get("package") or entry.get("package")
            keys = {f"simple:{name}"}
            if fqcn:
                keys.add(f"fqcn:{fqcn}")
            if package:
                keys.add(f"pkg_simple:{package}|{name}")
            if keys & fact_keys:
                hit = True
                break
        if hit:
            matched += 1
        else:
            failures.append(
                {
                    "layer": "join",
                    "stratum": "path_a_to_facts",
                    "reason_class": "unmatched",
                    "simple_name": name,
                    "file": entry.get("file"),
                }
            )
    den = len(entity_map)
    out = _rate_block(matched, den)
    out["failures"] = failures
    return out


def _lineage_reason_class(reason: Optional[str]) -> str:
    if not reason:
        return "unavailable_unknown"
    if "InvalidSyntaxException" in reason or "unparsable" in reason.lower():
        return "dialect_or_syntax"
    if "contested" in reason.lower():
        return "contested_refuse"
    if "not found" in reason.lower() or "no entity" in reason.lower():
        return "entity_lookup"
    return "unavailable_other"


def measure_r_lin(
    signals: Mapping[str, Any],
    *,
    scoring_env: str = SCORING_ENV_CALLABLE,
) -> Dict[str, Any]:
    """Lineage rates under scoring environment `callable` (normative) or `pooled`."""
    if scoring_env not in {SCORING_ENV_CALLABLE, SCORING_ENV_POOLED}:
        raise ValueError(f"unknown scoring_env: {scoring_env}")

    evidence = signals.get("evidence") or {}
    rows = evidence.get("raw_queries") if isinstance(evidence, Mapping) else None
    if not isinstance(rows, list):
        rows = []

    strata: Dict[str, Dict[str, int]] = {}
    failures: List[Dict[str, Any]] = []
    taxonomy: Counter[str] = Counter()

    def bump(stratum: str, available: bool) -> None:
        slot = strata.setdefault(stratum, {"available": 0, "total": 0})
        slot["total"] += 1
        if available:
            slot["available"] += 1

    for row in rows:
        if not isinstance(row, Mapping):
            continue
        query = row.get("query")
        kind = str(row.get("query_kind") or "other")
        lineage = row.get("lineage") if isinstance(row.get("lineage"), Mapping) else {}
        available = bool(lineage.get("available"))

        if query is None:
            taxonomy["null_query"] += 1
            failures.append(
                {
                    "layer": "lineage",
                    "stratum": "null_query",
                    "reason_class": "null_query",
                    "file": row.get("file"),
                    "line": row.get("line"),
                    "query_kind": kind,
                }
            )
            if scoring_env == SCORING_ENV_POOLED:
                # Fold uncallable rows into native as failed trials (contrast estimator).
                bump("native", False)
            else:
                bump("null_query", False)
            continue

        stratum = kind if kind in {"native", "jpql"} else "other"
        bump(stratum, available)
        if not available:
            rc = _lineage_reason_class(
                lineage.get("reason") if isinstance(lineage, Mapping) else None
            )
            taxonomy[rc] += 1
            failures.append(
                {
                    "layer": "lineage",
                    "stratum": stratum,
                    "reason_class": rc,
                    "file": row.get("file"),
                    "line": row.get("line"),
                    "query_kind": kind,
                    "reason": (lineage.get("reason") if isinstance(lineage, Mapping) else None),
                }
            )

    rates: Dict[str, Any] = {}
    for name, slot in sorted(strata.items()):
        rates[name] = _rate_block(slot["available"], slot["total"])

    # Under callable, exclude null_query stratum from mean.
    if scoring_env == SCORING_ENV_CALLABLE:
        mean_slots = {k: v for k, v in strata.items() if k != "null_query"}
    else:
        mean_slots = strata
    weighted_num = sum(s["available"] for s in mean_slots.values())
    weighted_den = sum(s["total"] for s in mean_slots.values())

    return {
        "scoring_env": scoring_env,
        "strata": rates,
        "mean_rate": _rate(weighted_num, weighted_den),
        "numerator": weighted_num,
        "denominator": weighted_den,
        "callable_denominator": weighted_den,
        "failure_taxonomy": dict(sorted(taxonomy.items())),
        "failures": failures,
    }


def measure_r_absence(
    facts: Sequence[Mapping[str, Any]],
    *,
    callable_trials: Optional[int] = None,
) -> Dict[str, Any]:
    """ABSENCE failure mass over callable trials; UNPROVEN is out-of-stratum.

    ``rate`` = |ABSENCE| / callable_trials when ``callable_trials`` is supplied
    (failure mass; ideal 0). Without ``callable_trials``, dens fall back to
    |ABSENCE| only for back-compat unit calls — prefer always passing trials.
    """
    absence = 0
    unproven = 0
    failures: List[Dict[str, Any]] = []
    for f in facts:
        pred = f.get("predicate")
        quals = f.get("qualifiers") if isinstance(f.get("qualifiers"), Mapping) else {}
        trial = quals.get("trial")
        if pred == "ABSENCE":
            if trial != "callable":
                continue
            absence += 1
            failures.append(
                {
                    "layer": "absence",
                    "stratum": str(quals.get("family") or f.get("subject")),
                    "reason_class": "ABSENCE",
                    "subject": f.get("subject"),
                    "file": f.get("file"),
                    "trial": trial,
                }
            )
        elif pred == "UNPROVEN":
            unproven += 1
    if callable_trials is not None:
        den = int(callable_trials)
        out = _rate_block(absence, den) if den > 0 else _rate_block(0, 0)
    else:
        den = absence
        out = _rate_block(absence, den) if den else _rate_block(0, 0)
    out["callable_absence"] = absence
    out["callable_trials"] = callable_trials
    out["unproven"] = unproven
    out["polarity"] = "failure_mass"
    out["note"] = (
        "R_absence is failure mass |ABSENCE|/callable_trials (ideal 0). "
        "UNPROVEN is reported but excluded from the denominator."
    )
    out["failures"] = failures
    return out


def measure_r_recall(
    facts: Sequence[Mapping[str, Any]],
    *,
    oracle_arm_present: bool = False,
) -> Optional[Dict[str, Any]]:
    """RECALL_MISS rates when trusted oracle arm present; else None.

    Planted RECALL_MISS without an oracle arm must not invent measured recall —
    callers stamp ``untrusted_planted``.
    """
    if not oracle_arm_present:
        return None
    misses = [f for f in facts if f.get("predicate") == "RECALL_MISS"]
    structural = 0
    evidentiary = 0
    failures: List[Dict[str, Any]] = []
    for f in misses:
        quals = f.get("qualifiers") if isinstance(f.get("qualifiers"), Mapping) else {}
        verdict = str(quals.get("verdict") or "STRUCTURAL")
        if verdict == "EVIDENTIARY":
            evidentiary += 1
        else:
            structural += 1
        failures.append(
            {
                "layer": "recall",
                "stratum": verdict,
                "reason_class": "RECALL_MISS",
                "subject": f.get("subject"),
                "file": f.get("file"),
                "oracle_arm": quals.get("oracle_arm"),
            }
        )
    den = len(misses)
    out = _rate_block(structural, den) if den else _rate_block(0, 0)
    out["structural"] = structural
    out["evidentiary"] = evidentiary
    out["oracle_arm_present"] = True
    out["failures"] = failures
    return out


def _trusted_codeql_oracle_arm(covering_proof: Optional[Mapping[str, Any]]) -> bool:
    """True only for a complete CodeQL receipt with matching subset roots."""
    for receipt in (covering_proof or {}).get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        if receipt.get("scanner") != "codeql":
            continue
        if receipt.get("status") != "complete":
            continue
        expected = receipt.get("expected_subset_root")
        acked = receipt.get("acked_subset_root")
        if expected and acked and expected == acked:
            return True
    return False


def _astgrep_receipt_complete(covering_proof: Optional[Mapping[str, Any]]) -> bool:
    for receipt in (covering_proof or {}).get("receipts") or []:
        if not isinstance(receipt, Mapping):
            continue
        if receipt.get("scanner") != "ast-grep":
            continue
        if receipt.get("status") != "complete":
            continue
        expected = receipt.get("expected_subset_root")
        acked = receipt.get("acked_subset_root")
        if expected and acked and expected == acked:
            return True
    return False


def load_and_verify_covering(
    signals: Mapping[str, Any],
    *,
    signals_path: Optional[Path] = None,
    covering_path: Optional[Path] = None,
) -> Tuple[Dict[str, Any], bool, str]:
    """Load covering_proof sibling and verify against signals inventory."""
    path = covering_path
    if path is None and signals_path is not None:
        path = covering_proof_path_for_signals_out(signals_path)
    if path is None or not path.is_file():
        return {}, False, f"covering_proof.json missing (expected {path})"
    proof = _load_json(path)
    if not isinstance(proof, Mapping):
        return {}, False, "covering_proof root must be a JSON object"
    sigs = signals.get("file_signatures") or {}
    if not isinstance(sigs, Mapping):
        return dict(proof), False, "signals.file_signatures missing"
    scanner_version = signals.get("scanner_version")
    if not scanner_version:
        return dict(proof), False, "signals.scanner_version missing"
    ok, why = verify_covering_proof(
        proof,
        file_signatures=sigs,
        scanner_version=str(scanner_version),
    )
    return dict(proof), ok, why


def measure_r_code_dep(signals: Mapping[str, Any]) -> Dict[str, Any]:
    evidence = signals.get("evidence") or {}
    if not isinstance(evidence, Mapping):
        evidence = {}
    deployment = evidence.get("deployment") or []
    if not isinstance(deployment, list):
        deployment = []

    dep_counts: Counter[str] = Counter()
    for row in deployment:
        if not isinstance(row, Mapping):
            continue
        text = " ".join(str(row.get(k) or "") for k in ("match", "rule_id", "file"))
        for family, pat in _DEP_FAMILY_PATTERNS:
            if pat.search(text):
                dep_counts[family] += 1

    code_hits = 0
    dep_total = 0
    per_family: Dict[str, Any] = {}
    failures: List[Dict[str, Any]] = []

    patterns = {family: pat for family, pat in _DEP_FAMILY_PATTERNS}
    for family, dep_n in sorted(dep_counts.items()):
        buckets = _CODE_BUCKET_BY_FAMILY.get(family, ())
        hits = 0
        pat = patterns[family]
        for b in buckets:
            rows = evidence.get(b) or []
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                blob = " ".join(str(row.get(k) or "") for k in ("match", "rule_id"))
                if pat.search(blob):
                    hits += 1
        dep_total += dep_n
        covered = dep_n if hits > 0 else 0
        code_hits += covered
        per_family[family] = {
            "dep_signals": dep_n,
            "code_keyword_hits": hits,
            "covered_dep_weight": covered,
        }
        if hits == 0:
            failures.append(
                {
                    "layer": "dep_code",
                    "stratum": family,
                    "reason_class": "dep_without_code_keyword",
                    "dep_signals": dep_n,
                }
            )

    out = _rate_block(code_hits, dep_total)
    out["per_family"] = per_family
    out["failures"] = failures
    return out


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


def failure_locator(row: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("layer") or ""),
            str(row.get("stratum") or ""),
            str(row.get("reason_class") or ""),
            str(row.get("file") or ""),
            str(row.get("line") if row.get("line") is not None else ""),
            str(row.get("simple_name") or row.get("subject") or ""),
        ]
    )


def sort_failures(failures: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows = [dict(f) for f in failures]
    rows.sort(
        key=lambda f: (
            str(f.get("layer") or ""),
            str(f.get("stratum") or ""),
            str(f.get("reason_class") or ""),
            str(f.get("file") or ""),
            str(f.get("simple_name") or f.get("subject") or ""),
        )
    )
    return rows


def apply_failure_budget(
    failures: Sequence[Mapping[str, Any]],
    budget: Optional[int],
    must_keep: Optional[Sequence[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Pi_B on sorted failures; L(B) vs must-keep locator set."""
    ordered = sort_failures(failures)
    if budget is None or budget < 0:
        kept = ordered
        b_val: Any = None
    else:
        kept = ordered[:budget]
        b_val = budget

    kept_locs = {failure_locator(f) for f in kept}
    star = list(must_keep or [])
    if not star:
        loss = 0.0
        missed: List[str] = []
    else:
        missed = [loc for loc in star if loc not in kept_locs]
        loss = len(missed) / len(star)

    truncation = {
        "slot": "truncation_loss",
        "B": b_val if b_val is not None else len(ordered),
        "B_infinite": budget is None,
        "failures_total": len(ordered),
        "failures_kept": len(kept),
        "must_keep_count": len(star),
        "must_keep_missed": missed,
        "L": loss,
        "truncation_alarm": bool(star) and loss > 0.0,
    }
    return kept, truncation


def _dominant_failure_stratum(lin: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    tax = {k: v for k, v in (lin.get("failure_taxonomy") or {}).items() if k != "null_query"}
    if not tax:
        tax = lin.get("failure_taxonomy") or {}
    if not tax:
        return None
    reason, count = max(tax.items(), key=lambda kv: kv[1])
    return {"reason_class": reason, "count": count}


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

    sym = measure_r_sym(facts)
    coll = measure_r_coll(signals)
    join = measure_r_join(signals, facts)
    lin = measure_r_lin(signals, scoring_env=SCORING_ENV_CALLABLE)
    lin_pooled = measure_r_lin(signals, scoring_env=SCORING_ENV_POOLED)
    code_dep = measure_r_code_dep(signals)

    # R_absence: failure mass over callable Stage-0 trials (not identity |A|/|A|).
    astgrep_ok = _astgrep_receipt_complete(covering_proof)
    callable_trials = count_callable_trials(
        signals,
        covering_ok=covering_ok,
        astgrep_receipt_complete=astgrep_ok,
    )
    absence = measure_r_absence(facts, callable_trials=callable_trials)

    # Trusted oracle = complete CodeQL receipt with matching subset roots.
    # Planted RECALL_MISS alone is never a substitute arm.
    oracle_arm = _trusted_codeql_oracle_arm(covering_proof)
    planted_misses = sum(1 for f in facts if f.get("predicate") == "RECALL_MISS")
    recall = measure_r_recall(facts, oracle_arm_present=oracle_arm)

    uncertainty = compute_uncertainty(
        coll["rate"],
        join["rate"],
        lin["mean_rate"],
        code_dep["rate"],
        callable_absence=int(absence["callable_absence"]),
        unproven=int(absence["unproven"]),
    )

    failures: List[Dict[str, Any]] = []
    for block in (sym, coll, join, lin, code_dep, absence):
        failures.extend(block.get("failures") or [])
    if recall is not None:
        failures.extend(recall.get("failures") or [])
    elif planted_misses > 0:
        for f in facts:
            if f.get("predicate") != "RECALL_MISS":
                continue
            quals = f.get("qualifiers") if isinstance(f.get("qualifiers"), Mapping) else {}
            failures.append(
                {
                    "layer": "recall",
                    "stratum": "untrusted_planted",
                    "reason_class": "RECALL_MISS_WITHOUT_ORACLE",
                    "subject": f.get("subject"),
                    "file": f.get("file"),
                    "oracle_arm": quals.get("oracle_arm"),
                }
            )
    failures = sort_failures(failures)
    kept, truncation = apply_failure_budget(failures, failure_budget, must_keep)

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
    rates: Dict[str, Any] = {
        "R_sym": {
            "numerator": sym["numerator"],
            "denominator": sym["denominator"],
            "callable_denominator": sym["callable_denominator"],
            "rate": sym["rate"],
        },
        "R_coll": {
            "numerator": coll["numerator"],
            "denominator": coll["denominator"],
            "callable_denominator": coll["callable_denominator"],
            "rate": coll["rate"],
        },
        "R_join": {
            "numerator": join["numerator"],
            "denominator": join["denominator"],
            "callable_denominator": join["callable_denominator"],
            "rate": join["rate"],
        },
        "R_lin": {
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
        },
        "R_code_dep": {
            "numerator": code_dep["numerator"],
            "denominator": code_dep["denominator"],
            "callable_denominator": code_dep["callable_denominator"],
            "rate": code_dep["rate"],
            "per_family": code_dep["per_family"],
        },
        "R_absence": {
            "numerator": absence["numerator"],
            "denominator": absence["denominator"],
            "callable_denominator": absence["callable_denominator"],
            "rate": absence["rate"],
            "callable_absence": absence["callable_absence"],
            "callable_trials": callable_trials,
            "unproven": absence["unproven"],
            "polarity": "failure_mass",
            "omitted": absence["rate"] is None,
            "note": absence["note"],
        },
        "oracle": {
            "trusted_codeql_arm": oracle_arm,
            "planted_recall_miss_count": planted_misses,
            "astgrep_receipt_complete": astgrep_ok,
        },
    }
    if recall is not None:
        rates["R_recall"] = {
            "numerator": recall["numerator"],
            "denominator": recall["denominator"],
            "callable_denominator": recall["callable_denominator"],
            "rate": recall["rate"],
            "structural": recall["structural"],
            "evidentiary": recall["evidentiary"],
            "omitted": False,
            "claim": "measured",
        }
    elif planted_misses > 0:
        rates["R_recall"] = {
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
    else:
        rates["R_recall"] = {
            "numerator": 0,
            "denominator": 0,
            "callable_denominator": 0,
            "rate": None,
            "omitted": True,
            "claim": "omitted_without_oracle",
            "note": "R_recall requires a trusted CodeQL covering receipt",
        }

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
            "recall_miss": (recall or {}).get("denominator", 0) if recall else 0,
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
        "design_reopen": {
            "path_a_to_symbols": (coll["rate"] or 0) > 0,
            "join_incomplete": join["rate"] is None or join["rate"] < 1.0,
            "lineage_dominant_stratum": _dominant_failure_stratum(lin),
            "truncation_alarm": truncation["truncation_alarm"],
            "structural_recall_misses": bool(recall and recall.get("structural")),
            "unproven_present": bool(absence["unproven"]),
            "absence_present": bool(absence["callable_absence"]),
            "vacuous_uncertainty": uncertainty.get("claim") == "vacuous_no_support",
            "untrusted_planted_recall": bool(planted_misses and not oracle_arm),
            "r_absence_failure_mass": absence.get("rate"),
        },
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
