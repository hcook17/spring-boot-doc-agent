"""context_packet composer — ranked, budgeted views over Stage-0 providers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from doc_engine.core.walk import is_path_inside_root
from doc_engine.query.freshness import (
    AssumeIndexed,
    DriftReportFreshness,
    SignatureFreshness,
    label_item_path,
    stale_paths_from_drift_report,
)
from doc_engine.query.load import QueryMissingError, QueryPathError, load_json, load_jsonl
from doc_engine.query.providers import DEFAULT_PROVIDERS
from doc_engine.query.rank import (
    keep_highest_scoring_items_within_token_budget,
    score_context_item_for_request,
    split_budget_into_primary_finding_and_risk_shares,
)

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
    item = {
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
    return item


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

    signals_path = run / "spring_signals.json"
    facts_path = run / "facts.jsonl"
    signals = load_json(signals_path, root=root_path)
    if not isinstance(signals, Mapping):
        from doc_engine.query.load import QueryError

        raise QueryError("spring_signals.json must be an object")
    facts_rows: list[Mapping[str, Any]] = []
    if facts_path.is_file():
        facts_rows = load_jsonl(facts_path, root=root_path)

    provs = list(providers) if providers is not None else list(DEFAULT_PROVIDERS)
    used: list[str] = []
    raw_items: list[dict[str, Any]] = []
    for p in provs:
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

    findings = [i for i in raw_items if i.get("provider") == "facts"]
    risks = [i for i in raw_items if i.get("provider") == "redaction"]
    rest = [i for i in raw_items if i.get("provider") not in ("facts", "redaction")]

    budget = _clamp_budget(budget_tokens)
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

    policy: Any = AssumeIndexed()
    if repo_path is not None:
        repo = Path(repo_path)
        sigs = signals.get("file_signatures") or {}
        if not isinstance(sigs, Mapping):
            sigs = {}
        live = {str(i.get("path")) for i in primary if i.get("path")}
        sig_policy = SignatureFreshness(repo_root=repo, signatures=sigs, live_paths=set())
        live_ok: set[str] = set()
        from doc_engine.core.walk import compute_file_signature

        for rel in live:
            full = (repo.resolve() / rel).resolve()
            if not is_path_inside_root(str(full), str(repo.resolve())):
                continue
            if not full.is_file():
                continue
            expected = sigs.get(rel.replace("\\", "/")) if isinstance(sigs, Mapping) else None
            try:
                actual = compute_file_signature(str(full))
            except OSError:
                continue
            if expected is not None and actual == expected:
                live_ok.add(rel.replace("\\", "/"))
        sig_policy = SignatureFreshness(repo_root=repo, signatures=sigs, live_paths=live_ok)
        policy = sig_policy
        if drift_report_path is not None:
            report = load_json(drift_report_path, root=root_path)
            if isinstance(report, Mapping):
                policy = DriftReportFreshness(
                    stale_paths=stale_paths_from_drift_report(report),
                    inner=sig_policy,
                )

    def _label(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for it in items:
            labeled = dict(it)
            labeled["freshness"] = label_item_path(
                policy, labeled.get("path") if isinstance(labeled.get("path"), str) else None
            )
            out.append(labeled)
        return out

    primary_l = _label(primary)
    related_l = _label(related)
    findings_l = _label(findings_kept)
    risks_l = _label(risks_kept)

    tokens_used = used_rest + used_f + used_r
    truncated = trunc_rest or trunc_f or trunc_r
    empty = not (primary_l or related_l or findings_l or risks_l)

    packet = {
        "schema_version": CONTEXT_PACKET_SCHEMA_VERSION,
        "kind": "context-packet",
        "request": request,
        "budgetTokens": budget,
        "tokensUsed": tokens_used,
        "truncated": truncated,
        "empty": empty,
        "primaryContext": primary_l,
        "relatedContext": related_l,
        "activeFindings": findings_l,
        "risks": risks_l,
        "providersUsed": used,
        "_hints": list(_DEFAULT_HINTS),
    }
    from doc_engine.query.schema_check import validate_envelope

    validate_envelope("context_packet", packet)
    return packet
