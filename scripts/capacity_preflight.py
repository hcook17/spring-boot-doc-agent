#!/usr/bin/env python3
"""
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
  Stage 4 (doc-writer):              14 (fixed, one per output file)
  -----------------------------------------------------------
  total = 2*num_groups + 16

Every threshold below is a stated, tunable guess pending real-world
calibration (documented as such, not hidden) — this script surfaces
numbers and warns; it never blocks or refuses to run the actual pipeline.

Usage:
    python3 capacity_preflight.py <repo_path> [--max-tokens 120000]
        [--overlap 0.10] [--groups-file groups.json]
        [--signals-file spring_signals.json]
        [--edges-file cross_group_edges.json]
        [--group-warn-threshold 15] [--fanout-warn-threshold 40]
        [--slice-tokens-warn-threshold 30000]
        [--out capacity_preflight_report.json]
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import build_cross_group_edges  # noqa: E402
import partition_repo  # noqa: E402
import spring_signal_scan  # noqa: E402

STAGE3_FIXED_FANOUT = 1   # gap-analyzer, always exactly one dispatch
STAGE4_FIXED_FANOUT = 14  # doc-writer, one per output file, always fixed


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
        signals_data = spring_signal_scan.scan(repo_path)
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


def compute_preflight(repo_path, max_tokens=120000, overlap=0.10,
                       groups_data=None, edges=None,
                       group_warn_threshold=15, fanout_warn_threshold=40,
                       slice_tokens_warn_threshold=30_000):
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
        "stage4_doc_writer": STAGE4_FIXED_FANOUT,
    }
    total_fanout = sum(stage_fanout.values())

    slice_tokens = estimate_stage1_slice_tokens(edges)
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

    return {
        "repo_path": groups_data.get("repo_path", repo_path),
        "num_groups": num_groups,
        "max_tokens_per_group": groups_data.get("max_tokens_per_group", max_tokens),
        "stage_fanout": stage_fanout,
        "total_fanout": total_fanout,
        "stage1_slice_est_tokens_max": slice_tokens["max"],
        "stage1_slice_est_tokens_mean": slice_tokens["mean"],
        "stage1_slice_est_tokens_total": slice_tokens["total"],
        "stage1_slice_est_tokens_per_group": slice_tokens["per_group"],
        # Reported straight from the join rather than re-derived here, so the
        # broadcast-vs-shipped comparison has exactly one implementation.
        "edge_join_stats": edge_stats,
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
                     help="Existing groups.json to read instead of re-running partition_repo.py's own grouping")
    ap.add_argument("--signals-file", default=None,
                     help="Existing spring_signals.json to join against instead of re-scanning")
    ap.add_argument("--edges-file", default=None,
                     help="Existing cross_group_edges.json to read instead of re-running the join (Stage 0 already writes this)")
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
    ap.add_argument("--out", default=None, help="Optional path to write the report as JSON")
    args = ap.parse_args()

    repo_path = os.path.abspath(args.repo_path)
    if not os.path.isdir(repo_path):
        print(f"error: not a directory: {repo_path}", file=sys.stderr)
        sys.exit(1)

    groups_data = _load_or_build_groups(repo_path, args.max_tokens, args.overlap, args.groups_file)
    try:
        # Order matters here in a way it did not before: the join consumes
        # the partition, so groups_data must be built first.
        edges = _load_or_build_edges(repo_path, args.signals_file, groups_data, args.edges_file)
    except spring_signal_scan.AstGrepError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    report = compute_preflight(
        repo_path, max_tokens=args.max_tokens, overlap=args.overlap,
        groups_data=groups_data, edges=edges,
        group_warn_threshold=args.group_warn_threshold,
        fanout_warn_threshold=args.fanout_warn_threshold,
        slice_tokens_warn_threshold=args.slice_tokens_warn_threshold,
    )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    reduction = report["edge_join_stats"].get("reduction_factor")
    reduction_note = f", {reduction}x smaller than broadcasting" if reduction else ""
    print(f"capacity-preflight: {report['num_groups']} groups, "
          f"{report['total_fanout']} total subagent dispatches, "
          f"largest Stage-1 edge slice ~{report['stage1_slice_est_tokens_max']} est. tokens "
          f"(~{report['stage1_slice_est_tokens_total']} across all groups{reduction_note}).")
    if report["warnings"]:
        print(f"{len(report['warnings'])} warning(s):")
        for w in report["warnings"]:
            print(f"  - [{w['dimension']}] {w['message']}")
    else:
        print("No thresholds crossed.")


if __name__ == "__main__":
    main()
