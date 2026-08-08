"""context_packet composer — ranked, budgeted views over Stage-0 providers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from doc_engine.core.walk import compute_file_signature, is_path_inside_root
from doc_engine.query.freshness import (
    AssumeIndexed,
    DriftReportFreshness,
    SignatureFreshness,
    label_item_path,
    stale_paths_from_drift_report,
)
from doc_engine.query.load import QueryError, QueryMissingError, QueryPathError, load_json, load_jsonl
from doc_engine.query.providers import DEFAULT_PROVIDERS
from doc_engine.query.rank import (
    keep_highest_scoring_items_within_token_budget,
    score_context_item_for_request,
    split_budget_into_primary_finding_and_risk_shares,
)
from doc_engine.query.schema_check import validate_envelope

CONTEXT_PACKET_SCHEMA_VERSION = 1
DEFAULT_BUDGET_TOKENS = 4000
MAX_BUDGET_TOKENS = 20_000
PRIMARY_COUNT = 5

_DEFAULT_HINTS = [
    "doc-engine query evidence --signals <run>/spring_signals.json --bucket security --limit 25",
    "doc-engine query entity --signals <run>/spring_signals.json --class <Name>",
    "doc-engine query route-trace --signals <run>/spring_signals.json --path-contains /api/",
    "doc-engine query facts --facts <run>/facts.jsonl --predicate MAPS_TO",
    "ast-grep run -l java -p '@Name' <path>  # and @Name($$$) for live structural gaps",
]


def _clamp_budget(budget_tokens: int | None) -> int:
    if budget_tokens is None:
        return DEFAULT_BUDGET_TOKENS
    b = int(budget_tokens)
    if b < 0:
        b = 0
    if b > MAX_BUDGET_TOKENS:
        b = MAX_BUDGET_TOKENS
    return b


def _score_raw(request: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    contested = bool(raw.get("contested"))
    return {
        "provider": raw.get("provider"),
        "path": raw.get("path"),
        "line": raw.get("line"),
        "match": raw.get("match"),
        "bucket": raw.get("bucket"),
        "reason": raw.get("reason"),
        "payload": raw.get("payload") or {},
        "score": score_context_item_for_request(
            request=request,
            path=raw.get("path") if isinstance(raw.get("path"), str) else None,
            text=raw.get("match") if isinstance(raw.get("match"), str) else None,
            bucket=raw.get("bucket") if isinstance(raw.get("bucket"), str) else None,
            contested=contested,
        ),
    }


def _resolve_run_under_root(
    run_dir: Path | str,
    root: Path | str | None,
) -> tuple[Path, Path]:
    run = Path(run_dir)
    if not run.is_dir():
        raise QueryMissingError(f"missing run dir: {run}")
    root_path = Path(root) if root is not None else run
    try:
        run_resolved = run.resolve()
        root_resolved = root_path.resolve()
    except OSError as exc:
        raise QueryPathError(f"cannot resolve run_dir/root: {exc}") from exc
    if not is_path_inside_root(str(run_resolved), str(root_resolved)):
        raise QueryPathError(f"run_dir escapes root: {run}")
    return run, root_path


def _load_run_artifacts(
    run: Path,
    root_path: Path,
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    signals = load_json(run / "spring_signals.json", root=root_path)
    if not isinstance(signals, Mapping):
        raise QueryError("spring_signals.json must be an object")
    facts_path = run / "facts.jsonl"
    facts_rows: list[Mapping[str, Any]] = []
    if facts_path.is_file():
        facts_rows = load_jsonl(facts_path, root=root_path)
    return signals, facts_rows


def _collect_scored_items(
    request: str,
    *,
    providers: Sequence[Any],
    signals: Mapping[str, Any],
    facts_rows: list[Mapping[str, Any]],
    run: Path,
    limit_per_provider: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    used: list[str] = []
    raw_items: list[dict[str, Any]] = []
    for p in providers:
        name = getattr(p, "name", p.__class__.__name__)
        used.append(str(name))
        batch = p.provide(
            request,
            signals=signals,
            facts_rows=facts_rows,
            run_dir=run,
            limit=limit_per_provider,
        )
        for row in batch:
            raw_items.append(_score_raw(request, row))
    return raw_items, used


def _provider_section(provider: Any) -> str:
    if provider == "facts":
        return "findings"
    if provider == "redaction":
        return "risks"
    return "rest"


def _partition_by_provider(
    raw_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    buckets = {"findings": findings, "risks": risks, "rest": rest}
    for item in raw_items:
        buckets[_provider_section(item.get("provider"))].append(item)
    return findings, risks, rest


def _trim_packet_sections(
    findings: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    rest: list[dict[str, Any]],
    budget: int,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    bool,
    int,
]:
    primary_budget, finding_budget, risk_budget = split_budget_into_primary_finding_and_risk_shares(
        budget
    )
    scored_rest, trunc_rest, used_rest = keep_highest_scoring_items_within_token_budget(
        rest, primary_budget
    )
    primary = scored_rest[:PRIMARY_COUNT]
    related = scored_rest[PRIMARY_COUNT:]
    findings_kept, trunc_f, used_f = keep_highest_scoring_items_within_token_budget(
        findings, finding_budget
    )
    risks_kept, trunc_r, used_r = keep_highest_scoring_items_within_token_budget(
        risks, risk_budget
    )
    tokens_used = used_rest + used_f + used_r
    truncated = trunc_rest or trunc_f or trunc_r
    return primary, related, findings_kept, risks_kept, truncated, tokens_used


def _normalized_rel_path(rel: str) -> str:
    return rel.replace("\\", "/")


def _file_signature_matches(full: Path, expected: Any) -> bool:
    if expected is None:
        return False
    try:
        actual = compute_file_signature(str(full))
    except OSError:
        return False
    return actual == expected


def _rel_path_is_live(
    repo_resolved: Path, sigs: Mapping[str, Any], rel: str
) -> bool:
    full = (repo_resolved / rel).resolve()
    if not is_path_inside_root(str(full), str(repo_resolved)):
        return False
    if not full.is_file():
        return False
    return _file_signature_matches(full, sigs.get(_normalized_rel_path(rel)))


def _live_paths_matching_signatures(
    repo: Path,
    sigs: Mapping[str, Any],
    candidate_paths: set[str],
) -> set[str]:
    live_ok: set[str] = set()
    repo_resolved = repo.resolve()
    for rel in candidate_paths:
        if _rel_path_is_live(repo_resolved, sigs, rel):
            live_ok.add(_normalized_rel_path(rel))
    return live_ok


def _wrap_freshness_with_drift_report(
    sig_policy: SignatureFreshness,
    drift_report_path: Path | str | None,
    root_path: Path,
) -> Any:
    if drift_report_path is None:
        return sig_policy
    report = load_json(drift_report_path, root=root_path)
    if not isinstance(report, Mapping):
        return sig_policy
    return DriftReportFreshness(
        stale_paths=stale_paths_from_drift_report(report),
        inner=sig_policy,
    )


def _build_freshness_policy(
    *,
    repo_path: Path | str | None,
    signals: Mapping[str, Any],
    primary: list[dict[str, Any]],
    drift_report_path: Path | str | None,
    root_path: Path,
) -> Any:
    if repo_path is None:
        return AssumeIndexed()
    repo = Path(repo_path)
    sigs = signals.get("file_signatures") or {}
    if not isinstance(sigs, Mapping):
        sigs = {}
    live = {str(i.get("path")) for i in primary if i.get("path")}
    live_ok = _live_paths_matching_signatures(repo, sigs, live)
    sig_policy = SignatureFreshness(repo_root=repo, signatures=sigs, live_paths=live_ok)
    return _wrap_freshness_with_drift_report(sig_policy, drift_report_path, root_path)


def _label_items(policy: Any, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in items:
        labeled = dict(it)
        labeled["freshness"] = label_item_path(
            policy, labeled.get("path") if isinstance(labeled.get("path"), str) else None
        )
        out.append(labeled)
    return out


def _assemble_packet(
    *,
    request: str,
    budget: int,
    tokens_used: int,
    truncated: bool,
    primary: list[dict[str, Any]],
    related: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    providers_used: list[str],
) -> dict[str, Any]:
    empty = not (primary or related or findings or risks)
    return {
        "schema_version": CONTEXT_PACKET_SCHEMA_VERSION,
        "kind": "context-packet",
        "request": request,
        "budgetTokens": budget,
        "tokensUsed": tokens_used,
        "truncated": truncated,
        "empty": empty,
        "primaryContext": primary,
        "relatedContext": related,
        "activeFindings": findings,
        "risks": risks,
        "providersUsed": providers_used,
        "_hints": list(_DEFAULT_HINTS),
    }


def run_context_packet(
    request: str,
    *,
    run_dir: Path | str,
    budget_tokens: int | None = None,
    root: Path | str | None = None,
    repo_path: Path | str | None = None,
    drift_report_path: Path | str | None = None,
    providers: Sequence[Any] | None = None,
    limit_per_provider: int = 40,
) -> dict[str, Any]:
    """Compose a Mako-class context packet from a Stage-0 run directory.

    ``root`` defaults to ``run_dir`` (library/CLI). MCP always passes the
    server-derived root and pins ``run_dir`` under it before calling here.
    """
    run, root_path = _resolve_run_under_root(run_dir, root)
    signals, facts_rows = _load_run_artifacts(run, root_path)
    provs = list(providers) if providers is not None else list(DEFAULT_PROVIDERS)
    raw_items, used = _collect_scored_items(
        request,
        providers=provs,
        signals=signals,
        facts_rows=facts_rows,
        run=run,
        limit_per_provider=limit_per_provider,
    )
    findings, risks, rest = _partition_by_provider(raw_items)
    budget = _clamp_budget(budget_tokens)
    primary, related, findings_kept, risks_kept, truncated, tokens_used = _trim_packet_sections(
        findings, risks, rest, budget
    )
    policy = _build_freshness_policy(
        repo_path=repo_path,
        signals=signals,
        primary=primary,
        drift_report_path=drift_report_path,
        root_path=root_path,
    )
    packet = _assemble_packet(
        request=request,
        budget=budget,
        tokens_used=tokens_used,
        truncated=truncated,
        primary=_label_items(policy, primary),
        related=_label_items(policy, related),
        findings=_label_items(policy, findings_kept),
        risks=_label_items(policy, risks_kept),
        providers_used=used,
    )
    validate_envelope("context_packet", packet)
    return packet
