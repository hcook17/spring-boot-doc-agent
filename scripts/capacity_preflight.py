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
  3. The repo-wide `references` bucket from spring_signal_scan.py is
     attached, in full, to *every* Stage-1 file-summarizer dispatch —
     SKILL.md's own text says this "should be inexpensive... but worth
     confirming against a real repo's actual size rather than just
     assumed."

This script does not re-derive any of that logic — it imports
partition_repo.py's build_groups()/estimate_tokens()/dfs_file_list() and
spring_signal_scan.py's scan() directly (sibling import, same pattern
spring_drift_check.py already uses for spring_signal_scan) and just reads
their output. No new dependency, no second implementation of the
chars/N-token estimator or the DFS walk to drift out of sync with the
original.

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
        [--group-warn-threshold 15] [--fanout-warn-threshold 40]
        [--references-tokens-warn-threshold 500000]
        [--out capacity_preflight_report.json]
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

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
        rel = os.path.relpath(full, repo_path)
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


def _load_or_scan_references(repo_path, signals_file):
    """Read an existing spring_signals.json's `references` bucket if given,
    otherwise run spring_signal_scan.py's own scan() against repo_path.
    Returns the references list (each entry a small file/line/text triple,
    per spring_signal_scan.py's own documented shape — not full source).

    scan()'s own return shape (and spring_signal_scan.py main()'s on-disk
    JSON, which mirrors it exactly) nests every evidence bucket, including
    `references`, under a top-level `evidence` key — not at the document
    root — so both branches below read `data["evidence"]["references"]`."""
    if signals_file:
        with open(signals_file, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = spring_signal_scan.scan(repo_path)
    return data.get("evidence", {}).get("references", [])


def estimate_references_bucket_tokens(references):
    """Serialize the references bucket the same way it will actually be
    handed to every Stage-1 dispatch (as JSON text) and estimate its token
    cost with the same chars/N heuristic partition_repo.py uses for
    everything else, so this number is directly comparable to a group's own
    est_tokens rather than a differently-calibrated guess."""
    serialized = json.dumps(references)
    return max(1, len(serialized) // partition_repo.CHARS_PER_TOKEN_DEFAULT)


def compute_preflight(repo_path, max_tokens=120000, overlap=0.10,
                       groups_data=None, references=None,
                       group_warn_threshold=15, fanout_warn_threshold=40,
                       references_tokens_warn_threshold=500_000):
    """Pure function over already-loaded groups_data/references (or repo_path
    to derive them) — kept separate from CLI/file-IO so it's directly unit
    testable against synthetic data without touching disk."""
    if groups_data is None:
        groups_data = _load_or_build_groups(repo_path, max_tokens, overlap, None)
    if references is None:
        references = _load_or_scan_references(repo_path, None)

    num_groups = groups_data["num_groups"]
    stage_fanout = {
        "stage1_file_summarizer": num_groups,
        "stage2_architect_segment": num_groups,
        "stage2_architect_merge": 1,
        "stage3_gap_analyzer": STAGE3_FIXED_FANOUT,
        "stage4_doc_writer": STAGE4_FIXED_FANOUT,
    }
    total_fanout = sum(stage_fanout.values())

    references_bucket_tokens = estimate_references_bucket_tokens(references)
    references_bucket_total_across_groups_est_tokens = references_bucket_tokens * num_groups

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
    if references_bucket_total_across_groups_est_tokens > references_tokens_warn_threshold:
        warnings.append({
            "dimension": "references_bucket_total_across_groups_est_tokens",
            "value": references_bucket_total_across_groups_est_tokens,
            "threshold": references_tokens_warn_threshold,
            "message": (
                f"The repo-wide references bucket (~{references_bucket_tokens} est. "
                f"tokens) is attached in full to every one of {num_groups} Stage-1 "
                f"dispatches, for an estimated {references_bucket_total_across_groups_est_tokens} "
                f"tokens spent repo-wide on that one shared bucket alone — SKILL.md "
                f"names this cost as 'worth confirming,' not yet verified at scale."
            ),
        })

    return {
        "repo_path": groups_data.get("repo_path", repo_path),
        "num_groups": num_groups,
        "max_tokens_per_group": groups_data.get("max_tokens_per_group", max_tokens),
        "stage_fanout": stage_fanout,
        "total_fanout": total_fanout,
        "references_bucket_entry_count": len(references),
        "references_bucket_est_tokens": references_bucket_tokens,
        "references_bucket_total_across_groups_est_tokens": references_bucket_total_across_groups_est_tokens,
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
                     help="Existing spring_signals.json to read `references` from instead of re-scanning")
    ap.add_argument("--group-warn-threshold", type=int, default=15,
                     help="Warn if num_groups exceeds this (default: 15, a stated heuristic guess)")
    ap.add_argument("--fanout-warn-threshold", type=int, default=40,
                     help="Warn if total subagent fan-out exceeds this (default: 40, a stated heuristic guess)")
    ap.add_argument("--references-tokens-warn-threshold", type=int, default=500_000,
                     help="Warn if references-bucket-tokens-times-groups exceeds this (default: 500000, a stated heuristic guess)")
    ap.add_argument("--out", default=None, help="Optional path to write the report as JSON")
    args = ap.parse_args()

    repo_path = os.path.abspath(args.repo_path)
    if not os.path.isdir(repo_path):
        print(f"error: not a directory: {repo_path}", file=sys.stderr)
        sys.exit(1)

    groups_data = _load_or_build_groups(repo_path, args.max_tokens, args.overlap, args.groups_file)
    references = _load_or_scan_references(repo_path, args.signals_file)

    report = compute_preflight(
        repo_path, max_tokens=args.max_tokens, overlap=args.overlap,
        groups_data=groups_data, references=references,
        group_warn_threshold=args.group_warn_threshold,
        fanout_warn_threshold=args.fanout_warn_threshold,
        references_tokens_warn_threshold=args.references_tokens_warn_threshold,
    )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    print(f"capacity-preflight: {report['num_groups']} groups, "
          f"{report['total_fanout']} total subagent dispatches, "
          f"~{report['references_bucket_total_across_groups_est_tokens']} est. tokens "
          f"spent repo-wide on the shared references bucket.")
    if report["warnings"]:
        print(f"{len(report['warnings'])} warning(s):")
        for w in report["warnings"]:
            print(f"  - [{w['dimension']}] {w['message']}")
    else:
        print("No thresholds crossed.")


if __name__ == "__main__":
    main()
