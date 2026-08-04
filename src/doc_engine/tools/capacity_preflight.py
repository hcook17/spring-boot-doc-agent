#!/usr/bin/env python3
"""

Run with: python -m doc_engine.tools.capacity_preflight

capacity_preflight.py — turn document-spring-repo's stated-but-unverified
scale assumptions into a concrete number for one specific target repo,
before committing to a full five-stage run.

CONSTRAINTS.md and skills/document-spring-repo/SKILL.md already name three
assumptions nobody has load-tested against a real large repo:
  1. Token counts are a chars/N heuristic (see partition_repo.py's
     CHARS_PER_TOKEN_DEFAULT/DENSE), not Claude's real tokenizer.
  2. build_groups() picks a planning-target group count, not a hard cap —
     a lopsided repo can end up with more groups than planned.
  3. Each Stage-1 file-summarizer dispatch carries its group's slice of
     `cross_group_edges.json` — the resolved arcs on that group's own
     boundary — on top of the group's own files.

     [Corrected 2026-07-24] Assumption 3 previously read: "the repo-wide
     `references` bucket is attached, in full, to *every* Stage-1
     dispatch." That was true when this script was written and stopped
     being true at commit abd3ade, which replaced the broadcast with a
     partitioned join in Stage 0; SKILL.md now says "Do not go back to
     broadcasting the bucket." This script kept measuring the broadcast
     anyway, and the first real-repo run measured the gap: 7,627,230 est.
     tokens reported against 358,645 actually shipped, a ~21x
     overstatement, in the direction of alarm. SKILL.md's original
     "worth confirming against a real repo" note is therefore discharged —
     it was confirmed, and the finding was that the cost was real enough
     to engineer away.

This script does not re-derive any of that logic — it imports
partition_repo.py's build_groups()/estimate_tokens()/dfs_file_list(),
spring_signal_scan.py's scan(), and build_cross_group_edges.py's
build_report() directly (sibling import, same pattern spring_drift_check.py
already uses for spring_signal_scan) and just reads their output. No new
dependency, no second implementation of the chars/N-token estimator, the DFS
walk, or the package/import join to drift out of sync with the original.

Note this measures only what is sent *in*. Nothing here estimates Stage-1
return payloads, so a run can pass preflight cleanly and still exhaust the
orchestrator on the way back — see SKILL.md's Stage 1 note on that ceiling.

Total subagent fan-out across all five pipeline stages, given num_groups
groups (see skills/document-spring-repo/SKILL.md's per-stage dispatch
description):
  Stage 1 (file-summarizer):        num_groups
  Stage 2 (architect-segment):      num_groups
  Stage 2 (architect-merge):        1  (always, serial)
  Stage 3 (gap-analyzer):           1  (always; the interview itself is
                                        the orchestrating thread, not a
                                        subagent dispatch, so it isn't
                                        counted here)
  Stage 3 (software-architect-and-testing): 1  (always; dispatched in the
                                        same turn as gap-analyzer, its own
                                        manifest stage, no interview)
  Stage 4 (doc-writer):              len(VALID_DOC_FILES)  (one per taxonomy file)
  -----------------------------------------------------------
  total = 2*num_groups + 3 + len(VALID_DOC_FILES)

[L2 / post–cross-group-edges] Stage-1 cost is the *partitioned* edge slice
(measured below). Stage-4 doc-writers still receive a merged evidence pool
(summaries, spring_signals, interview_answers — see pipeline stages.py
doc_writer input_artifacts) on *each* of the taxonomy writers. Measuring
only Stage-1 therefore under-states Stage-4 input load.

This script runs at **Stage 0**, before summaries/interview exist. It
reports a **partial_proxy_pre_stage4** for shared-pool size: sum of group
`est_tokens` (source-token *proxy* for future summaries; overlap can
inflate) plus optional signals chars/N. It does **not** estimate
interview_answers, architecture/merge text beyond that proxy, or Stage-4
return payloads. Field names keep `*_upper_bound_*` for the numeric warn
threshold; `stage4_metric_kind` is the honesty label — do not treat a
quiet proxy as closed Stage-4 capacity risk. Cite north-star domain
`07-partitioning-and-skew`, `rel-partition-bounds-fanout`,
`claims-and-status-drift`.

Every threshold below is a stated, tunable guess pending real-world
calibration (documented as such, not hidden) — this script surfaces
numbers and warns; it never blocks or refuses to run the actual pipeline.

Usage:
    python -m doc_engine.tools.capacity_preflight <repo_path> [--max-tokens 120000]
        [--overlap 0.10] [--groups-file groups.json]
        [--signals-file spring_signals.json]
        [--edges-file cross_group_edges.json]
        [--group-warn-threshold 15] [--fanout-warn-threshold 40]
        [--slice-tokens-warn-threshold 30000]
        [--stage4-shared-tokens-warn-threshold 80000]
        [--summaries-file summaries.json]
        [--interview-answers-file interview_answers.json]
        [--stage0-preflight-report capacity_preflight_report.json]
        [--out capacity_preflight_report.json]

L2b — when --summaries-file is set, run post-artifact Stage-4 *measurement*
(metric_kind measured_stage4_inputs) against on-disk summaries / optional
interview_answers / optional signals. Stage-0 partial_proxy_pre_stage4 is
unchanged for pre-run estimates. Do not invent interview sizes at Stage 0;
do not change the default --stage4-shared-tokens-warn-threshold without a
documented mid-size run. Cite rel-partition-bounds-fanout.
"""

import argparse
import json
import os
import sys

from doc_engine.tools import (
    build_cross_group_edges,  # noqa: E402
    partition_repo,  # noqa: E402
    spring_signal_scan,  # noqa: E402
)
from doc_engine.tools.doc_tag_utils import VALID_DOC_FILES

STAGE3_FIXED_FANOUT = 1   # gap-analyzer, always exactly one dispatch
STAGE3_ARCH_TEST_REVIEW_FANOUT = 1  # software-architect-and-testing, always one
# SoR: taxonomy file set — not a magic literal that can drift from doc-writer.
STAGE4_FIXED_FANOUT = len(VALID_DOC_FILES)

# Wire version for capacity_preflight_report.json (slice-5 thin operator schema).
# Bump only on breaking changes; additive fields keep the same version per
# rel-schema-outlives-writers. Stamped on both Stage-0 compute_preflight and
# L2b compute_stage4_calibration return paths.
CAPACITY_PREFLIGHT_REPORT_SCHEMA_VERSION = 1

# Pipeline SoR: doc_writer input_artifacts in doc_engine.pipeline.stages —
# what Stage-4 actually receives once those artifacts exist. Stage-0 proxy
# can only include a subset.
STAGE4_PROXY_INCLUDED = (
    "group_est_tokens_proxy_for_summaries",
    "spring_signals_optional",
)
STAGE4_PROXY_OMITTED = (
    "interview_answers",
    "architecture_merge_beyond_summary_proxy",
    "stage4_return_payloads",
)

# L2b measured mode: SoR = on-disk Stage-4 inputs. Returns stay omitted.
STAGE4_MEASURED_ALWAYS_OMITTED = (
    "stage4_return_payloads",
)


def _load_or_build_groups(repo_path, max_tokens, overlap, groups_file):
    """Read an existing groups.json if given, otherwise run
    partition_repo.py's own dfs_file_list()/estimate_tokens()/build_groups()
    against repo_path — never a re-implementation of that arithmetic."""
    if groups_file:
        with open(groups_file, encoding="utf-8") as f:
            return json.load(f)

    all_files = partition_repo.dfs_file_list(
        repo_path,
        partition_repo.DEFAULT_EXCLUDED_DIRS,
        partition_repo.DEFAULT_EXCLUDED_EXTS,
        partition_repo.DEFAULT_EXCLUDED_FILES,
    )
    file_tokens = []
    for full in all_files:
        # Via partition_repo's shared helper, not an inline .replace(). This
        # was the third site of the same bug -- partition_repo.relpath_posix()
        # carries the full history -- and it became load-bearing when this
        # function started feeding its groups to build_report(), which joins
        # them by path against spring_signals.json's forward-slash paths. On
        # Windows that join matched nothing and the preflight silently
        # under-reported the fan-out it exists to estimate.
        rel = partition_repo.relpath_posix(full, repo_path)
        tokens, reason = partition_repo.estimate_tokens(full, 2_000_000)
        if reason:
            continue
        file_tokens.append((rel, tokens))

    groups_raw = partition_repo.build_groups(file_tokens, max_tokens, overlap)
    return {
        "repo_path": os.path.abspath(repo_path),
        "max_tokens_per_group": max_tokens,
        "overlap": overlap,
        "total_files_considered": len(file_tokens),
        "num_groups": len(groups_raw),
        "groups": [
            {"id": idx, "files": [f for f, _ in g], "est_tokens": sum(t for _, t in g)}
            for idx, g in enumerate(groups_raw)
        ],
    }


def _load_or_build_edges(repo_path, signals_file, groups_data, edges_file):
    """Read an existing cross_group_edges.json if given, otherwise build it
    via build_cross_group_edges.build_report() — never a re-implementation
    of that join.

    Unlike the groups/references pair this replaced, this one is *order
    dependent*: the join takes both the partition and the signals, so
    groups_data must already exist before this is called. SKILL.md's Stage 0
    writes this file, so --edges-file is the common path on a real run and
    the scan below is the fallback.

    scan()'s return shape (and spring_signal_scan.py main()'s on-disk JSON,
    which mirrors it exactly) nests every evidence bucket under a top-level
    `evidence` key rather than at the document root; build_report() knows
    that and reads it itself."""
    if edges_file:
        with open(edges_file, encoding="utf-8") as f:
            return json.load(f)

    if signals_file:
        with open(signals_file, encoding="utf-8") as f:
            signals_data = json.load(f)
    else:
        signals_data = spring_signal_scan.scan(
            repo_path, scanners=["filesystem", "ast-grep"],
        )
    return build_cross_group_edges.build_report(groups_data, signals_data)


def estimate_stage1_slice_tokens(edges):
    """Estimate the per-group Stage-1 edge slice, serialized the way it will
    actually be handed to the dispatch (as JSON text), with the same chars/N
    heuristic partition_repo.py uses for everything else — so the number is
    directly comparable to a group's own est_tokens.

    Returns a distribution rather than a scalar, because the broadcast model
    this replaced had only one meaningful number and the partitioned one has
    two. `total` is what the old references-times-groups product was trying
    to approximate: whole-run cost. `max` is the one that actually bounds
    risk — it is the largest single Stage-1 dispatch, and a context limit is
    breached by one dispatch, not by a sum."""
    per_group = {
        gid: max(1, len(json.dumps(slice_)) // partition_repo.CHARS_PER_TOKEN_DEFAULT)
        for gid, slice_ in edges.get("groups", {}).items()
    }
    values = list(per_group.values()) or [0]
    return {
        "per_group": per_group,
        "max": max(values),
        "mean": sum(values) // len(values),
        "total": sum(values),
    }


def _json_est_tokens(obj):
    """Same chars/N heuristic as Stage-1 slices / Stage-0 signals."""
    if obj is None:
        return 0
    return max(1, len(json.dumps(obj)) // partition_repo.CHARS_PER_TOKEN_DEFAULT)


def estimate_stage4_shared_pool_tokens(groups_data, signals_data=None):
    """Partial Stage-0 *proxy* for Stage-4 shared-pool input — not a full bound.

    SoR for dispatch count is ``VALID_DOC_FILES``. Stage-4's real inputs are
    summaries + interview_answers + spring_signals (pipeline stages.py). At
    Stage 0 those summaries/interview do not exist yet, so we proxy merged
    summary size as the sum of per-group ``est_tokens`` (overlap can inflate)
    and optionally add signals chars/N.

    ``metric_kind`` is ``partial_proxy_pre_stage4``. Numeric fields keep the
    ``*_upper_bound_*`` names for the warn threshold only — they are **not**
    an upper bound on full Stage-4 input while omissions are non-empty.
    """
    groups = groups_data.get("groups") or []
    summaries_est = sum(int(g.get("est_tokens") or 0) for g in groups)
    signals_omitted = signals_data is None
    signals_est = _json_est_tokens(signals_data) if signals_data is not None else 0
    shared = summaries_est + signals_est
    return {
        "metric_kind": "partial_proxy_pre_stage4",
        "included_now": list(STAGE4_PROXY_INCLUDED),
        "omitted_not_estimated": list(STAGE4_PROXY_OMITTED),
        "summaries_est_tokens": summaries_est,
        "interview_answers_est_tokens": 0,
        "interview_answers_omitted": True,
        "signals_est_tokens": signals_est,
        "signals_omitted": signals_omitted,
        "shared_pool_upper_bound_est_tokens": shared,
        "aggregate_input_upper_bound_est_tokens": shared * STAGE4_FIXED_FANOUT,
        "return_payloads_estimated": False,
        "note": (
            "partial_proxy_pre_stage4: group est_tokens proxy for future "
            "summaries (overlap can inflate) + optional signals; omitted "
            "interview_answers / architecture_merge_beyond_summary_proxy / "
            "stage4_return_payloads; not a full Stage-4 upper_bound"
        ),
    }


def measure_stage4_shared_pool_tokens(
    summaries_data, interview_answers=None, signals_data=None,
):
    """L2b: measure Stage-4 shared-pool input from on-disk artifacts.

    SoR = summaries.json (+ optional interview_answers.json / spring_signals.json).
    ``metric_kind`` is ``measured_stage4_inputs``. Return payloads are never
    estimated. Missing interview/signals are listed in omissions — do not invent
    sizes. Numeric ``*_upper_bound_*`` names remain warn-threshold fields only.
    """
    if summaries_data is None:
        raise ValueError("summaries_data is required for measured_stage4_inputs")
    summaries_est = _json_est_tokens(summaries_data)
    interview_omitted = interview_answers is None
    interview_est = (
        0 if interview_omitted else _json_est_tokens(interview_answers)
    )
    signals_omitted = signals_data is None
    signals_est = 0 if signals_omitted else _json_est_tokens(signals_data)
    shared = summaries_est + interview_est + signals_est

    included = ["summaries"]
    omitted = []
    if interview_omitted:
        omitted.append("interview_answers")
    else:
        included.append("interview_answers")
    if signals_omitted:
        omitted.append("spring_signals")
    else:
        included.append("spring_signals")
    omitted.extend(STAGE4_MEASURED_ALWAYS_OMITTED)

    return {
        "metric_kind": "measured_stage4_inputs",
        "included_now": included,
        "omitted_not_estimated": omitted,
        "summaries_est_tokens": summaries_est,
        "interview_answers_est_tokens": interview_est,
        "interview_answers_omitted": interview_omitted,
        "signals_est_tokens": signals_est,
        "signals_omitted": signals_omitted,
        "shared_pool_upper_bound_est_tokens": shared,
        "aggregate_input_upper_bound_est_tokens": shared * STAGE4_FIXED_FANOUT,
        "return_payloads_estimated": False,
        "note": (
            "measured_stage4_inputs: chars/N of on-disk summaries"
            f"{'' if interview_omitted else ' + interview_answers'}"
            f"{'' if signals_omitted else ' + spring_signals'}; "
            "omitted stage4_return_payloads"
            f"{' / interview_answers' if interview_omitted else ''}"
            f"{' / spring_signals' if signals_omitted else ''}; "
            "not a claim that Stage-4 capacity risk is closed"
        ),
    }


def compare_stage4_proxy_to_measured(proxy_pool, measured_pool):
    """Derived view: Stage-0 proxy vs measured on-disk inputs (not a second SoR)."""
    proxy_shared = int(proxy_pool.get("shared_pool_upper_bound_est_tokens") or 0)
    measured_shared = int(measured_pool.get("shared_pool_upper_bound_est_tokens") or 0)
    ratio = (
        (measured_shared / proxy_shared) if proxy_shared > 0 else None
    )
    return {
        "proxy_metric_kind": proxy_pool.get("metric_kind"),
        "measured_metric_kind": measured_pool.get("metric_kind"),
        "stage0_proxy_shared_est_tokens": proxy_shared,
        "measured_shared_est_tokens": measured_shared,
        "measured_over_proxy_ratio": ratio,
        "proxy_summaries_est_tokens": proxy_pool.get("summaries_est_tokens"),
        "measured_summaries_est_tokens": measured_pool.get("summaries_est_tokens"),
        "measured_interview_answers_est_tokens": measured_pool.get(
            "interview_answers_est_tokens"
        ),
        "note": (
            "derived comparison only; measured SoR is on-disk Stage-4 inputs; "
            "proxy SoR is group est_tokens + optional signals at Stage 0"
        ),
    }


def _stage4_pool_fields(stage4_pool):
    """Flatten a Stage-4 pool dict into report keys (proxy or measured)."""
    return {
        "stage4_metric_kind": stage4_pool["metric_kind"],
        "stage4_included_now": stage4_pool["included_now"],
        "stage4_omitted_not_estimated": stage4_pool["omitted_not_estimated"],
        "stage4_shared_pool_upper_bound_est_tokens": (
            stage4_pool["shared_pool_upper_bound_est_tokens"]
        ),
        "stage4_summaries_est_tokens": stage4_pool["summaries_est_tokens"],
        "stage4_interview_answers_est_tokens": stage4_pool.get(
            "interview_answers_est_tokens", 0
        ),
        "stage4_interview_answers_omitted": stage4_pool.get(
            "interview_answers_omitted", True
        ),
        "stage4_signals_est_tokens": stage4_pool["signals_est_tokens"],
        "stage4_signals_omitted": stage4_pool["signals_omitted"],
        "stage4_aggregate_input_upper_bound_est_tokens": (
            stage4_pool["aggregate_input_upper_bound_est_tokens"]
        ),
        "stage4_return_payloads_estimated": stage4_pool["return_payloads_estimated"],
    }


def _stage4_shared_pool_warning(stage4_pool, threshold):
    if stage4_pool["shared_pool_upper_bound_est_tokens"] <= threshold:
        return None
    kind = stage4_pool["metric_kind"]
    interview_note = ""
    if stage4_pool.get("interview_answers_omitted"):
        interview_note = ", interview_omitted"
    elif stage4_pool.get("interview_answers_est_tokens"):
        interview_note = (
            f", interview≈{stage4_pool['interview_answers_est_tokens']}"
        )
    return {
        "dimension": "stage4_shared_pool_upper_bound_est_tokens",
        "value": stage4_pool["shared_pool_upper_bound_est_tokens"],
        "threshold": threshold,
        "message": (
            f"Stage-4 shared-pool {kind} is "
            f"~{stage4_pool['shared_pool_upper_bound_est_tokens']} "
            f"est. tokens (summaries≈{stage4_pool['summaries_est_tokens']}"
            f"{interview_note}, "
            f"signals≈{stage4_pool['signals_est_tokens']}"
            f"{', signals_omitted' if stage4_pool['signals_omitted'] else ''}), "
            f"and each of {STAGE4_FIXED_FANOUT} doc-writers receives a pool "
            f"(aggregate≈"
            f"{stage4_pool['aggregate_input_upper_bound_est_tokens']}). "
            f"Omitted (not estimated): "
            f"{', '.join(stage4_pool['omitted_not_estimated'])}. "
            f"Do not treat a quiet Stage-1 slice — or this metric — as "
            f"closed Stage-4 capacity risk."
        ),
    }


def compute_preflight(repo_path, max_tokens=120000, overlap=0.10,
                       groups_data=None, edges=None, signals_data=None,
                       group_warn_threshold=15, fanout_warn_threshold=40,
                       slice_tokens_warn_threshold=30_000,
                       stage4_shared_tokens_warn_threshold=80_000):
    """Pure function over already-loaded groups_data/edges (or repo_path to
    derive them) — kept separate from CLI/file-IO so it's directly unit
    testable against synthetic data without touching disk.

    The two derivation branches below are order-dependent, unlike the pair
    this replaced: the edge join consumes the partition."""
    if groups_data is None:
        groups_data = _load_or_build_groups(repo_path, max_tokens, overlap, None)
    if edges is None:
        edges = _load_or_build_edges(repo_path, None, groups_data, None)

    num_groups = groups_data["num_groups"]
    stage_fanout = {
        "stage1_file_summarizer": num_groups,
        "stage2_architect_segment": num_groups,
        "stage2_architect_merge": 1,
        "stage3_gap_analyzer": STAGE3_FIXED_FANOUT,
        "stage3_software_architect_and_testing": STAGE3_ARCH_TEST_REVIEW_FANOUT,
        "stage4_doc_writer": STAGE4_FIXED_FANOUT,
    }
    total_fanout = sum(stage_fanout.values())

    slice_tokens = estimate_stage1_slice_tokens(edges)
    stage4_pool = estimate_stage4_shared_pool_tokens(groups_data, signals_data)
    edge_stats = edges.get("stats", {})

    warnings = []
    if num_groups > group_warn_threshold:
        warnings.append({
            "dimension": "num_groups",
            "value": num_groups,
            "threshold": group_warn_threshold,
            "message": (
                f"{num_groups} groups exceeds the group-count warning threshold "
                f"({group_warn_threshold}). Practical Task-tool concurrency and "
                f"per-turn dispatch limits are untested at this scale — consider "
                f"raising --max-tokens or reviewing before a full run."
            ),
        })
    if total_fanout > fanout_warn_threshold:
        warnings.append({
            "dimension": "total_fanout",
            "value": total_fanout,
            "threshold": fanout_warn_threshold,
            "message": (
                f"{total_fanout} total subagent dispatches across all five stages "
                f"exceeds the fan-out warning threshold ({fanout_warn_threshold}). "
                f"This pipeline has no built-in cap on fan-out today — this is a "
                f"stated, tunable guess about practical concurrency limits, not a "
                f"validated ceiling."
            ),
        })
    if slice_tokens["max"] > slice_tokens_warn_threshold:
        warnings.append({
            "dimension": "stage1_slice_est_tokens_max",
            "value": slice_tokens["max"],
            "threshold": slice_tokens_warn_threshold,
            "message": (
                f"The largest single Stage-1 edge slice is ~{slice_tokens['max']} est. "
                f"tokens, on top of that group's own files (budgeted at "
                f"{groups_data.get('max_tokens_per_group', max_tokens)}). Across all "
                f"{num_groups} groups the slices total ~{slice_tokens['total']}. A "
                f"context limit is breached by one dispatch, not by the sum, so the "
                f"max is the number that matters — consider lowering --max-tokens to "
                f"cut smaller groups, which shrinks each slice."
            ),
        })
    stage4_warn = _stage4_shared_pool_warning(
        stage4_pool, stage4_shared_tokens_warn_threshold,
    )
    if stage4_warn:
        warnings.append(stage4_warn)

    report = {
        "schema_version": CAPACITY_PREFLIGHT_REPORT_SCHEMA_VERSION,
        "repo_path": groups_data.get("repo_path", repo_path),
        "num_groups": num_groups,
        "max_tokens_per_group": groups_data.get("max_tokens_per_group", max_tokens),
        "stage_fanout": stage_fanout,
        "total_fanout": total_fanout,
        "stage1_slice_est_tokens_max": slice_tokens["max"],
        "stage1_slice_est_tokens_mean": slice_tokens["mean"],
        "stage1_slice_est_tokens_total": slice_tokens["total"],
        "stage1_slice_est_tokens_per_group": slice_tokens["per_group"],
        **_stage4_pool_fields(stage4_pool),
        # Reported straight from the join rather than re-derived here, so the
        # broadcast-vs-shipped comparison has exactly one implementation.
        "edge_join_stats": edge_stats,
        "warnings": warnings,
    }
    return report


def compute_stage4_calibration(
    repo_path,
    summaries_data,
    interview_answers=None,
    signals_data=None,
    groups_data=None,
    stage0_preflight_report=None,
    stage4_shared_tokens_warn_threshold=80_000,
):
    """L2b post-artifact calibration — measured Stage-4 inputs vs optional proxy.

    Requires on-disk summaries. Interview/signals optional (listed omitted if
    absent). When ``groups_data`` or a Stage-0 preflight report is supplied,
    attach a derived proxy comparison. If **both** are supplied, the Stage-0
    report wins and a warning is emitted (groups are ignored for the ratio).
    Does not change Stage-0 defaults. Not invoked by the Stage 0 pipeline step.
    """
    measured = measure_stage4_shared_pool_tokens(
        summaries_data,
        interview_answers=interview_answers,
        signals_data=signals_data,
    )
    warnings = []
    stage4_warn = _stage4_shared_pool_warning(
        measured, stage4_shared_tokens_warn_threshold,
    )
    if stage4_warn:
        warnings.append(stage4_warn)

    proxy_comparison = None
    proxy_pool = None
    proxy_source = None
    both_proxy_sources = (
        stage0_preflight_report is not None and groups_data is not None
    )
    if stage0_preflight_report is not None:
        if both_proxy_sources:
            warnings.append({
                "dimension": "stage4_proxy_comparison_source",
                "value": "stage0_preflight_report",
                "threshold": "groups_file_ignored",
                "message": (
                    "Both a Stage-0 preflight report and groups_data were supplied "
                    "for proxy comparison; using stage0_preflight_report "
                    "(groups ignored for the measured/proxy ratio)."
                ),
            })
        # Rebuild a pool-shaped dict from a prior Stage-0 report's flat fields.
        proxy_pool = {
            "metric_kind": stage0_preflight_report.get(
                "stage4_metric_kind", "partial_proxy_pre_stage4"
            ),
            "summaries_est_tokens": stage0_preflight_report.get(
                "stage4_summaries_est_tokens", 0
            ),
            "interview_answers_est_tokens": stage0_preflight_report.get(
                "stage4_interview_answers_est_tokens", 0
            ),
            "signals_est_tokens": stage0_preflight_report.get(
                "stage4_signals_est_tokens", 0
            ),
            "shared_pool_upper_bound_est_tokens": stage0_preflight_report.get(
                "stage4_shared_pool_upper_bound_est_tokens", 0
            ),
        }
        proxy_source = "stage0_preflight_report"
    elif groups_data is not None:
        # Compare against Stage-0 proxy recomputed from groups only (no signals)
        # so the ratio highlights summary compression vs est_tokens, not a
        # shared signals term on both sides.
        proxy_pool = estimate_stage4_shared_pool_tokens(groups_data, None)
        proxy_source = "groups_est_tokens_proxy"

    if proxy_pool is not None:
        proxy_comparison = compare_stage4_proxy_to_measured(proxy_pool, measured)
        proxy_comparison["proxy_source"] = proxy_source

    return {
        "schema_version": CAPACITY_PREFLIGHT_REPORT_SCHEMA_VERSION,
        "repo_path": (
            (groups_data or {}).get("repo_path")
            or (stage0_preflight_report or {}).get("repo_path")
            or repo_path
        ),
        "mode": "stage4_calibration",
        **_stage4_pool_fields(measured),
        "stage4_proxy_comparison": proxy_comparison,
        "warnings": warnings,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo_path", help="Path to the target repository root")
    ap.add_argument("--max-tokens", type=int, default=120000,
                     help="Same meaning as partition_repo.py's --max-tokens (default: 120000)")
    ap.add_argument("--overlap", type=float, default=0.10,
                     help="Same meaning as partition_repo.py's --overlap (default: 0.10)")
    ap.add_argument("--groups-file", default=None,
                     help=("Existing groups.json (Stage 0 path: partition input; "
                           "L2b: optional proxy compare from group est_tokens — "
                           "ignored for the ratio if --stage0-preflight-report is also set)"))
    ap.add_argument("--signals-file", default=None,
                     help="Existing spring_signals.json to join against instead of re-scanning")
    ap.add_argument("--edges-file", default=None,
                     help="Existing cross_group_edges.json to read instead of re-running the join (Stage 0 already writes this)")
    ap.add_argument("--summaries-file", default=None,
                     help=("L2b: existing summaries.json — when set, run post-artifact "
                           "Stage-4 measurement (measured_stage4_inputs) instead of "
                           "Stage-0 partial_proxy_pre_stage4"))
    ap.add_argument("--interview-answers-file", default=None,
                     help="L2b: existing interview_answers.json (optional; omitted if absent)")
    ap.add_argument("--stage0-preflight-report", default=None,
                     help=("L2b: prior capacity_preflight_report.json from Stage 0 for "
                           "derived proxy-vs-measured comparison (wins over --groups-file "
                           "when both are set; emits a warning)"))
    ap.add_argument("--group-warn-threshold", type=int, default=15,
                     help="Warn if num_groups exceeds this (default: 15, a stated heuristic guess)")
    ap.add_argument("--fanout-warn-threshold", type=int, default=40,
                     help="Warn if total subagent fan-out exceeds this (default: 40, a stated heuristic guess)")
    ap.add_argument("--slice-tokens-warn-threshold", type=int, default=30_000,
                     help=("Warn if the largest single Stage-1 edge slice exceeds this "
                           "(default: 30000 — a quarter of the default 120000 per-group "
                           "budget; a stated guess with one real-repo data point behind "
                           "it, not a calibrated ceiling). Replaces the old "
                           "--references-tokens-warn-threshold, whose 500000 default "
                           "measured the removed broadcast and does not carry over."))
    ap.add_argument("--stage4-shared-tokens-warn-threshold", type=int, default=80_000,
                     help=("Warn if Stage-4 shared-pool est. tokens exceed this "
                           "(default: 80000 — stated guess pending documented mid-size "
                           "calibration; Stage-0 uses partial_proxy; L2b measured mode "
                           "warns on on-disk input sizes. Interview/returns omitted at "
                           "Stage 0; returns still omitted when measuring)."))
    ap.add_argument("--out", default=None, help="Optional path to write the report as JSON")
    args = ap.parse_args()

    repo_path = os.path.abspath(args.repo_path)
    if not os.path.isdir(repo_path):
        print(f"error: not a directory: {repo_path}", file=sys.stderr)
        sys.exit(1)

    if args.summaries_file:
        with open(args.summaries_file, encoding="utf-8") as f:
            summaries_data = json.load(f)
        interview_answers = None
        if args.interview_answers_file:
            with open(args.interview_answers_file, encoding="utf-8") as f:
                interview_answers = json.load(f)
        signals_data = None
        if args.signals_file:
            with open(args.signals_file, encoding="utf-8") as f:
                signals_data = json.load(f)
        groups_data = None
        if args.groups_file:
            groups_data = _load_or_build_groups(
                repo_path, args.max_tokens, args.overlap, args.groups_file,
            )
        stage0_report = None
        if args.stage0_preflight_report:
            with open(args.stage0_preflight_report, encoding="utf-8") as f:
                stage0_report = json.load(f)
        report = compute_stage4_calibration(
            repo_path,
            summaries_data=summaries_data,
            interview_answers=interview_answers,
            signals_data=signals_data,
            groups_data=groups_data,
            stage0_preflight_report=stage0_report,
            stage4_shared_tokens_warn_threshold=args.stage4_shared_tokens_warn_threshold,
        )
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
        cmp_ = report.get("stage4_proxy_comparison")
        cmp_note = ""
        if cmp_ and cmp_.get("measured_over_proxy_ratio") is not None:
            cmp_note = (
                f"; measured/proxy ratio≈{cmp_['measured_over_proxy_ratio']:.3f}"
            )
        print(
            f"capacity-preflight (L2b measured_stage4_inputs): shared-pool ~"
            f"{report['stage4_shared_pool_upper_bound_est_tokens']} est. tokens "
            f"(summaries≈{report['stage4_summaries_est_tokens']}, "
            f"interview≈{report['stage4_interview_answers_est_tokens']}"
            f"{' omitted' if report['stage4_interview_answers_omitted'] else ''}, "
            f"signals≈{report['stage4_signals_est_tokens']}"
            f"{' omitted' if report['stage4_signals_omitted'] else ''}; "
            f"omitted: {', '.join(report['stage4_omitted_not_estimated'])}"
            f"{cmp_note})."
        )
        if report["warnings"]:
            print(f"{len(report['warnings'])} warning(s):")
            for w in report["warnings"]:
                print(f"  - [{w['dimension']}] {w['message']}")
        else:
            print("No thresholds crossed.")
        return

    groups_data = _load_or_build_groups(repo_path, args.max_tokens, args.overlap, args.groups_file)
    signals_data = None
    if args.signals_file:
        with open(args.signals_file, encoding="utf-8") as f:
            signals_data = json.load(f)
    try:
        # Order matters here in a way it did not before: the join consumes
        # the partition, so groups_data must be built first.
        edges = _load_or_build_edges(repo_path, args.signals_file, groups_data, args.edges_file)
    except spring_signal_scan.AstGrepError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    report = compute_preflight(
        repo_path, max_tokens=args.max_tokens, overlap=args.overlap,
        groups_data=groups_data, edges=edges, signals_data=signals_data,
        group_warn_threshold=args.group_warn_threshold,
        fanout_warn_threshold=args.fanout_warn_threshold,
        slice_tokens_warn_threshold=args.slice_tokens_warn_threshold,
        stage4_shared_tokens_warn_threshold=args.stage4_shared_tokens_warn_threshold,
    )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    reduction = report["edge_join_stats"].get("reduction_factor")
    reduction_note = f", {reduction}x smaller than broadcasting" if reduction else ""
    print(f"capacity-preflight: {report['num_groups']} groups, "
          f"{report['total_fanout']} total subagent dispatches, "
          f"largest Stage-1 edge slice ~{report['stage1_slice_est_tokens_max']} est. tokens "
          f"(~{report['stage1_slice_est_tokens_total']} across all groups{reduction_note}); "
          f"Stage-4 shared-pool partial_proxy_pre_stage4 ~"
          f"{report['stage4_shared_pool_upper_bound_est_tokens']} "
          f"(omitted: {', '.join(report['stage4_omitted_not_estimated'])}"
          f"{'; signals_omitted' if report['stage4_signals_omitted'] else ''}).")
    if report["warnings"]:
        print(f"{len(report['warnings'])} warning(s):")
        for w in report["warnings"]:
            print(f"  - [{w['dimension']}] {w['message']}")
    else:
        print("No thresholds crossed.")


if __name__ == "__main__":
    main()
