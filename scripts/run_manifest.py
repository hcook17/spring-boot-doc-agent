#!/usr/bin/env python3
"""
run_manifest.py — per-run telemetry for one document-spring-repo pipeline
invocation: target repo identity, per-stage timing/pass-fail state,
evidence-tag counts per generated file, and the interview's
answered/skipped breakdown.

Implements the schema proposed in
claude/analytics-logging-research-2026-07-24.md, itself researched against
MLflow's RunInfo, ML Metadata's Execution lineage record, in-toto's Link
predicate, and DVC's dvc.lock — see that file for the prior-art comparison.
Closes the still-open half of claude/steering-prompts/04-analytics-logging-research-prompt.md
(item 2); item 1 (drift detection) is already handled by
spring_drift_check.py.

WHY THIS IS A CLI INVOKED MANY TIMES, NOT ONE LONG-LIVED PROCESS
document-spring-repo has no single Python process spanning all five
stages — skills/document-spring-repo/SKILL.md is a prose script the
orchestrating Claude Code thread follows by hand, dispatching subagents via
the Task tool and shelling out to Stage-0 scripts via Bash. There is no
in-process object this module could hand the orchestrator to call at real
stage boundaries. So instead this is a small stdlib CLI, invoked once per
stage-start/stage-end event (plus once for `init` and once for `finalize`),
each invocation reading the current run_manifest.json, updating it, and
writing it back — the same "small script invoked via Bash from SKILL.md"
pattern spring_signal_scan.py/partition_repo.py/spring_drift_check.py
already use, just invoked repeatedly across one run instead of once.

CONCURRENCY CONTRACT (see SKILL.md's own bolded note, restated here since
it's load-bearing for correctness, not just documentation): `start-stage`
and `end-stage` must be called exactly once per named stage, by the
orchestrating thread only — never from inside a subagent, and never once
per individual parallel dispatch within a stage (e.g. not once per
file-summarizer group). Concurrent read-modify-write calls against the
same manifest file from multiple processes racing each other is not
supported by this module and will lose updates.

WHY WRITES ARE ATOMIC (temp file + os.replace), UNLIKE ANY OTHER SCRIPT
HERE
Every other script in this plugin (spring_signal_scan.py, partition_repo.py,
spring_drift_check.py) writes its output exactly once, at the very end of a
single run — an interrupted write just means "no output file yet," not
"corrupted output file." This module reads-modifies-writes the *same* file
repeatedly across a whole pipeline run; an interrupted write here would
otherwise leave run_manifest.json half-written, breaking every subsequent
stage call's `json.load()`. So every write here goes through
_write_json_atomic(): write to a temp file in the same directory, then
os.replace() (atomic on both POSIX and Windows). This is new territory for
this codebase, not an existing convention being borrowed.

WHAT HAPPENS IF THE ORCHESTRATING SESSION DIES MID-RUN
`finalize` auto-marks any stage still `status: "running"` as `canceled`
(with an explanatory `error`) and sets the overall run `status` to
`"partial"` rather than pretending the run cleanly completed or failed.
But if the orchestrating session dies *before finalize is ever invoked at
all*, there is no background process here to notice and no automatic
recovery — the manifest simply sits on disk forever at
`status: "running"`. That's a real, stated limitation of the
"CLI invoked from a prose script" design, not a bug being silently
tolerated: a human (or a future session) can still run
`run_manifest.py finalize` by hand against that file at any later point to
close it out.

Usage:
    python3 run_manifest.py init <repo_path> --out run_manifest.json
    python3 run_manifest.py start-stage run_manifest.json signal_scan
    python3 run_manifest.py end-stage run_manifest.json signal_scan --status complete
    ... (repeat start-stage/end-stage per stage) ...
    python3 run_manifest.py finalize run_manifest.json \\
        --signals-file spring_signals.json --docs-dir docs/ \\
        --interview-file interview_answers.json \\
        --preflight-file capacity_preflight_report.json
    python3 run_manifest.py summary run_manifest.json
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import doc_tag_utils  # noqa: E402
import spring_signal_scan  # noqa: E402

# ML Metadata's Execution.last_known_state enum vocabulary, reused verbatim
# rather than inventing a bespoke one (see the research doc's design notes).
# "new" is accepted as a stage status for forward-compatibility but nothing
# in this module currently produces it.
STAGE_STATUSES = frozenset({"new", "running", "complete", "failed", "cached", "canceled"})
END_STAGE_STATUSES = sorted(STAGE_STATUSES - {"new", "running"})

# capacity_preflight.py's stage_fanout dict uses a different, independently
# evolved key vocabulary (confirmed by direct read of that file, not
# assumed) — stage1_file_summarizer / stage2_architect_segment /
# stage2_architect_merge / stage3_gap_analyzer / stage4_doc_writer — which
# does not match this module's own stage names below. This mapping is the
# only thing that lets finalize's --preflight-file tie-in diff predicted
# vs. actual fan-out without silently producing nothing for every key.
# stage2_architect_segment and stage2_architect_merge both fold into this
# module's single combined "architect" stage (their predicted counts are
# summed); capacity_preflight.py has no entries at all for signal_scan or
# partition, since Stage 0 has no subagent fan-out to predict.
PREFLIGHT_TO_MANIFEST_STAGE = {
    "stage1_file_summarizer": "file_summarize",
    "stage2_architect_segment": "architect",
    "stage2_architect_merge": "architect",
    "stage3_gap_analyzer": "gap_analysis_interview",
    "stage4_doc_writer": "doc_writer",
}

_TAG_KEY_MAP = {
    "evidenced": "Evidenced",
    "confirmed": "Confirmed",
    "unknown": "Unknown",
    "per_existing_docs": "PerExistingDocs",
}


def _now_ms(override=None):
    return int(override) if override is not None else int(time.time() * 1000)


def _iso8601(now_ms):
    return datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json_atomic(path, data):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _run_git(repo_path, args, label):
    try:
        result = subprocess.run(
            ["git", "-C", repo_path] + args,
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"warning: could not run 'git {label}' for '{repo_path}': {e}", file=sys.stderr)
        return None
    if result.returncode != 0:
        print(f"warning: 'git {label}' failed for '{repo_path}': {result.stderr.strip()}", file=sys.stderr)
        return None
    return result.stdout


def git_commit_hash(repo_path):
    """None (with a stderr warning) if repo_path isn't a git repo or `git`
    isn't on PATH — not an abort, same graceful-degrade posture
    spring_signal_scan.py's compute_file_signature() uses for one
    unreadable file."""
    out = _run_git(repo_path, ["rev-parse", "HEAD"], "rev-parse HEAD")
    return out.strip() if out is not None else None


def git_is_dirty(repo_path):
    """True if `git status --porcelain` reports anything, False if clean,
    None (with a stderr warning) if it couldn't be determined. Recorded
    alongside commit_hash for the same reason spring_signal_scan.py hashes
    on-disk content instead of a git blob SHA: a commit hash alone implies
    'this identifies the exact scanned state,' which is false if the tree
    was dirty when the scan ran."""
    out = _run_git(repo_path, ["status", "--porcelain"], "status --porcelain")
    return bool(out.strip()) if out is not None else None


def make_run_id(now_ms):
    """Uniqueness suffix only — not a git hash, not otherwise meaningful."""
    return f"{_iso8601(now_ms)}-{os.urandom(4).hex()}"


def build_init_manifest(repo_path, now_ms=None):
    now_ms = _now_ms(now_ms)
    abspath = os.path.abspath(repo_path)
    return {
        "schema_version": 1,
        "run_id": make_run_id(now_ms),
        "target_repo": {
            "path": abspath,
            "commit_hash": git_commit_hash(abspath),
            "dirty": git_is_dirty(abspath),
        },
        "timestamp_start": _iso8601(now_ms),
        "timestamp_end": None,
        "status": "running",
        "stages": [],
        "file_signatures": {},
        "evidence_tag_counts": {},
        "interview": None,
        "capacity_preflight": None,
    }


def start_stage(manifest, name, fanout=None, now_ms=None):
    now_ms = _now_ms(now_ms)
    manifest.setdefault("stages", []).append({
        "name": name,
        "status": "running",
        "start_time_ms": now_ms,
        "end_time_ms": None,
        "duration_ms": None,
        "error": None,
        "actual_fanout": fanout,
    })
    return manifest


def end_stage(manifest, name, status, error=None, now_ms=None):
    if status not in END_STAGE_STATUSES:
        raise ValueError(f"unknown end-stage status {status!r}, must be one of {END_STAGE_STATUSES}")
    now_ms = _now_ms(now_ms)
    # Search from the end: this is what makes the retry case (a stage that
    # failed and was retried — two start/end pairs, same name) resolve
    # correctly. Each end-stage call matches its own immediately-preceding
    # still-running start-stage entry, not an earlier, already-ended one.
    for stage in reversed(manifest.get("stages", [])):
        if stage["name"] == name and stage["status"] == "running":
            stage["end_time_ms"] = now_ms
            stage["duration_ms"] = now_ms - stage["start_time_ms"]
            stage["status"] = status
            stage["error"] = error
            return manifest
    raise ValueError(
        f"no running stage named {name!r} to end — start-stage was never called for it, "
        f"or it was already ended"
    )


def load_file_signatures(signals_file=None, repo_path=None):
    """Reuse spring_signals.json's file_signatures if given (Stage 0
    already computed it — don't re-hash). Otherwise compute fresh via the
    exact same dfs_walk()/compute_file_signature() spring_signal_scan.py
    itself uses (no ast-grep needed for this — a plain re-walk-and-hash)."""
    if signals_file:
        return _read_json(signals_file).get("file_signatures", {})
    if not repo_path:
        return {}
    sigs = {}
    for full in spring_signal_scan.dfs_walk(repo_path):
        rel = os.path.relpath(full, repo_path).replace("\\", "/")
        try:
            sigs[rel] = spring_signal_scan.compute_file_signature(full)
        except OSError as e:
            print(f"warning: could not read '{rel}' to compute its content signature: {e}", file=sys.stderr)
    return sigs


def compute_evidence_tag_counts(docs_dir):
    """For each of the fourteen doc-writer output files present under
    docs_dir, count tags via doc_tag_utils.count_tags_by_kind() — the exact
    same tag grammar test_pipeline_stages.py enforces, imported rather than
    reimplemented — remapped from its lowercase keys to the schema's
    capitalized ones."""
    result = {}
    for stem in sorted(doc_tag_utils.VALID_DOC_FILES):
        path = os.path.join(docs_dir, f"{stem}.md")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        counts = doc_tag_utils.count_tags_by_kind(text)
        result[f"{stem}.md"] = {_TAG_KEY_MAP[k]: v for k, v in counts.items()}
    return result


def parse_interview_file(path):
    """interview_answers.json's documented shape (see SKILL.md Stage 3): a
    JSON list of {id, question, status, answer, date} objects, status one
    of "answered"/"skipped". Malformed input never crashes this tool — it's
    reported to stderr and recorded as all-zero counts, the same defensive
    posture spring_signal_scan.py uses for an unreadable file."""
    empty = {"asked": 0, "answered": 0, "skipped": 0, "questions": []}
    try:
        data = _read_json(path)
    except (OSError, json.JSONDecodeError) as e:
        print(f"warning: could not read/parse interview file '{path}': {e}", file=sys.stderr)
        return empty
    if not isinstance(data, list):
        print(f"warning: interview file '{path}' is not a JSON list as documented in SKILL.md "
              f"Stage 3, recording zeros", file=sys.stderr)
        return empty

    questions, answered, skipped = [], 0, 0
    for entry in data:
        if not isinstance(entry, dict) or "id" not in entry or "status" not in entry:
            print(f"warning: interview file entry missing required 'id'/'status' keys, skipping: {entry!r}",
                  file=sys.stderr)
            continue
        status = entry["status"]
        if status == "answered":
            answered += 1
        elif status == "skipped":
            skipped += 1
        else:
            print(f"warning: interview entry {entry.get('id')!r} has unrecognized status {status!r}",
                  file=sys.stderr)
        questions.append({"id": entry["id"], "status": status})
    return {"asked": len(questions), "answered": answered, "skipped": skipped, "questions": questions}


def compute_capacity_preflight_tie_in(preflight_path):
    """Translate capacity_preflight_report.json's stage_fanout keys through
    PREFLIGHT_TO_MANIFEST_STAGE. Any key with no mapping entry is recorded
    in unmapped_preflight_keys AND triggers a stderr warning — never a
    silent no-op, since a naive same-name diff against this module's own
    stage names would otherwise match nothing at all (see module-level
    comment on PREFLIGHT_TO_MANIFEST_STAGE)."""
    try:
        data = _read_json(preflight_path)
    except (OSError, json.JSONDecodeError) as e:
        print(f"warning: could not read/parse capacity preflight file '{preflight_path}': {e}", file=sys.stderr)
        return None

    stage_fanout = data.get("stage_fanout", {})
    predicted_by_manifest_stage = {}
    unmapped = []
    for key, value in stage_fanout.items():
        manifest_stage = PREFLIGHT_TO_MANIFEST_STAGE.get(key)
        if manifest_stage is None:
            unmapped.append(key)
            print(f"warning: capacity_preflight stage key '{key}' has no known mapping to a "
                  f"run_manifest stage name, skipping", file=sys.stderr)
            continue
        predicted_by_manifest_stage[manifest_stage] = predicted_by_manifest_stage.get(manifest_stage, 0) + value

    return {
        "source_file": preflight_path,
        "total_predicted_fanout": data.get("total_fanout", sum(stage_fanout.values())),
        "predicted_fanout_by_manifest_stage": predicted_by_manifest_stage,
        "unmapped_preflight_keys": unmapped,
    }


def finalize_manifest(manifest, status=None, file_signatures=None, evidence_tag_counts=None,
                       interview=None, capacity_preflight=None, now_ms=None):
    now_ms = _now_ms(now_ms)
    warnings = []

    for stage in manifest.get("stages", []):
        if stage["status"] == "running":
            stage["end_time_ms"] = now_ms
            stage["duration_ms"] = now_ms - stage["start_time_ms"]
            stage["status"] = "canceled"
            stage["error"] = ("stage never ended before finalize — orchestrating session may have "
                               "crashed or skipped end-stage")
            warnings.append(f"stage '{stage['name']}' was still running at finalize; marked canceled")

    if status is None:
        statuses = {s["status"] for s in manifest.get("stages", [])}
        if "failed" in statuses:
            status = "failed"
        elif "canceled" in statuses:
            status = "partial"
        else:
            status = "complete"

    manifest["timestamp_end"] = _iso8601(now_ms)
    manifest["status"] = status
    if file_signatures is not None:
        manifest["file_signatures"] = file_signatures
    if evidence_tag_counts is not None:
        manifest["evidence_tag_counts"] = evidence_tag_counts
    if interview is not None:
        manifest["interview"] = interview
    if capacity_preflight is not None:
        manifest["capacity_preflight"] = capacity_preflight

    return manifest, warnings


def format_summary(manifest):
    lines = [f"run_manifest: run_id={manifest.get('run_id')} status={manifest.get('status')}"]

    stages = manifest.get("stages", [])
    for s in stages:
        dur = s.get("duration_ms")
        dur_str = f"{dur / 1000:.1f}s" if dur is not None else "?"
        fanout_str = f", fanout={s['actual_fanout']}" if s.get("actual_fanout") is not None else ""
        error_str = f" — {s['error']}" if s.get("error") else ""
        lines.append(f"  - {s['name']}: {s['status']} ({dur_str}{fanout_str}){error_str}")

    ts_start, ts_end = manifest.get("timestamp_start"), manifest.get("timestamp_end")
    if ts_start and ts_end:
        lines.append(f"  total: {ts_start} -> {ts_end}")

    tag_counts = manifest.get("evidence_tag_counts") or {}
    if tag_counts:
        totals = {"Evidenced": 0, "Confirmed": 0, "Unknown": 0, "PerExistingDocs": 0}
        for counts in tag_counts.values():
            for k in totals:
                totals[k] += counts.get(k, 0)
        lines.append(f"  evidence tags across {len(tag_counts)} file(s): "
                     f"Evidenced={totals['Evidenced']}, Confirmed={totals['Confirmed']}, "
                     f"Unknown={totals['Unknown']}, PerExistingDocs={totals['PerExistingDocs']}")

    interview = manifest.get("interview")
    if interview:
        lines.append(f"  interview: asked={interview['asked']} answered={interview['answered']} "
                     f"skipped={interview['skipped']}")

    preflight = manifest.get("capacity_preflight")
    if preflight:
        if preflight["unmapped_preflight_keys"]:
            lines.append(f"  capacity_preflight: {len(preflight['unmapped_preflight_keys'])} "
                         f"unmapped stage key(s): {preflight['unmapped_preflight_keys']}")
        for stage_name, predicted in preflight["predicted_fanout_by_manifest_stage"].items():
            actual = sum(s.get("actual_fanout") or 0 for s in stages if s["name"] == stage_name)
            lines.append(f"  fanout[{stage_name}]: predicted={predicted}, actual={actual}")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create a new run_manifest.json for a pipeline run")
    p_init.add_argument("repo_path")
    p_init.add_argument("--out", default="run_manifest.json")
    p_init.add_argument("--now-ms", type=int, default=None, help=argparse.SUPPRESS)

    p_start = sub.add_parser("start-stage", help="Record a stage's start")
    p_start.add_argument("manifest_path")
    p_start.add_argument("stage_name")
    p_start.add_argument("--fanout", type=int, default=None,
                          help="Actual subagent dispatch count for this stage, if applicable")
    p_start.add_argument("--now-ms", type=int, default=None, help=argparse.SUPPRESS)

    p_end = sub.add_parser("end-stage", help="Record a stage's end")
    p_end.add_argument("manifest_path")
    p_end.add_argument("stage_name")
    p_end.add_argument("--status", required=True, choices=END_STAGE_STATUSES)
    p_end.add_argument("--error", default=None)
    p_end.add_argument("--now-ms", type=int, default=None, help=argparse.SUPPRESS)

    p_fin = sub.add_parser("finalize", help="Close out a run_manifest.json at the end of a pipeline run")
    p_fin.add_argument("manifest_path")
    p_fin.add_argument("--status", choices=["complete", "failed", "partial"], default=None,
                        help="Override the inferred overall status (default: inferred from stage outcomes)")
    p_fin.add_argument("--signals-file", default=None,
                        help="Reuse an existing spring_signals.json's file_signatures instead of re-hashing")
    p_fin.add_argument("--docs-dir", default=None,
                        help="Directory containing the fourteen generated doc-writer output files")
    p_fin.add_argument("--interview-file", default=None, help="Path to interview_answers.json")
    p_fin.add_argument("--preflight-file", default=None, help="Path to a capacity_preflight_report.json")
    p_fin.add_argument("--now-ms", type=int, default=None, help=argparse.SUPPRESS)

    p_sum = sub.add_parser("summary", help="Print a human-readable summary of an existing manifest")
    p_sum.add_argument("manifest_path")

    args = ap.parse_args()

    if args.command == "init":
        if not os.path.isdir(args.repo_path):
            print(f"error: not a directory: {args.repo_path}", file=sys.stderr)
            sys.exit(1)
        manifest = build_init_manifest(args.repo_path, now_ms=args.now_ms)
        _write_json_atomic(args.out, manifest)
        tr = manifest["target_repo"]
        print(f"Wrote {args.out}. run_id={manifest['run_id']} target_repo={tr['path']} "
              f"commit_hash={tr['commit_hash']} dirty={tr['dirty']}")

    elif args.command == "start-stage":
        manifest = _read_json(args.manifest_path)
        start_stage(manifest, args.stage_name, fanout=args.fanout, now_ms=args.now_ms)
        _write_json_atomic(args.manifest_path, manifest)
        print(f"stage '{args.stage_name}' started")

    elif args.command == "end-stage":
        manifest = _read_json(args.manifest_path)
        try:
            end_stage(manifest, args.stage_name, args.status, error=args.error, now_ms=args.now_ms)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)
        _write_json_atomic(args.manifest_path, manifest)
        print(f"stage '{args.stage_name}' ended: {args.status}")

    elif args.command == "finalize":
        manifest = _read_json(args.manifest_path)

        if args.signals_file:
            file_signatures = load_file_signatures(signals_file=args.signals_file)
        else:
            file_signatures = load_file_signatures(repo_path=manifest.get("target_repo", {}).get("path"))
        evidence_tag_counts = compute_evidence_tag_counts(args.docs_dir) if args.docs_dir else None
        interview = parse_interview_file(args.interview_file) if args.interview_file else None
        capacity_preflight = (
            compute_capacity_preflight_tie_in(args.preflight_file) if args.preflight_file else None
        )

        manifest, warnings = finalize_manifest(
            manifest, status=args.status, file_signatures=file_signatures,
            evidence_tag_counts=evidence_tag_counts, interview=interview,
            capacity_preflight=capacity_preflight, now_ms=args.now_ms,
        )
        _write_json_atomic(args.manifest_path, manifest)
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        print(format_summary(manifest))

    elif args.command == "summary":
        manifest = _read_json(args.manifest_path)
        print(format_summary(manifest))


if __name__ == "__main__":
    main()
