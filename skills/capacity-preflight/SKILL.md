---
name: capacity-preflight
description: Run before the document-spring-repo pipeline against a large or unfamiliar target repo to estimate cost and surface scale risk before committing to a full run — estimated group count and total subagent fan-out across all five stages, estimated size of the per-group `cross_group_edges.json` slice each Stage-1 dispatch carries, and warnings if any of these cross reasonable thresholds. Reuses partition_repo.py's, spring_signal_scan.py's and build_cross_group_edges.py's own output rather than re-estimating from scratch. Use whenever pointing document-spring-repo at a repo you haven't run it against before, or one you suspect is large (monorepo, hundreds of files) — the full pipeline has no built-in warning today if group count or fan-out is large enough to hit practical concurrency or context limits.
---

# Capacity preflight

## Why this exists

`CONSTRAINTS.md` and `skills/document-spring-repo/SKILL.md` already name several scale assumptions nobody has load-tested against a real large repo: token counts are a chars/N heuristic, not Claude's real tokenizer; `build_groups()` picks a planning-target group count, not a hard cap; and each Stage-1 dispatch carries its group's slice of `cross_group_edges.json` on top of the group's own files. (Through 2026-07-24 this last one read "the repo-wide `references` bucket is attached, in full, to *every* Stage-1 dispatch" — true until commit `abd3ade` replaced the broadcast with a partitioned join, after which this skill kept measuring a cost the pipeline no longer paid, overstating it ~21x on the first real repo it was pointed at.) This skill turns those from prose warnings into a concrete number for *this specific* target repo, before you commit to a full five-stage run.

## Step 1 — run Stage 0 via the orchestrator

This skill does not duplicate `document-spring-repo`'s Stage 0 logic — it reads that stage's own output. If you don't already have `spring_signals.json`/`groups.json` for this repo:

```bash
doc-engine pipeline run <repo_path> \
  --compliance-profile deterministic_only \
  --out-dir <run_dir>
```

Use `<run_dir>/spring_signals.json` and `<run_dir>/groups.json`. If you already have both from a prior run, skip straight to Step 2.

**Do not** invoke deterministic tools via the plugin install tree (no `scripts/` under the marketplace plugin root).

## Step 2 — derive the numbers

Capacity preflight still lives as a product-repo tool. Prefer running it from a product checkout (or after `pip install -e .`) via Stage 0's own `capacity_preflight` stage — it is already part of `deterministic_only` / certified Stage 0 (`build_stage_specs()` name `capacity_preflight`). Re-use `<run_dir>/capacity_preflight_report.json` when present.

If you must recompute only the report against existing artifacts:

```bash
python -m doc_engine.tools.capacity_preflight <repo_path> \
    --groups-file <run_dir>/groups.json --signals-file <run_dir>/spring_signals.json \
    --out <run_dir>/capacity_preflight_report.json
```

(Omit `--groups-file`/`--signals-file` to have it run Stage 0's logic itself.) This script only *imports* `partition_repo`'s `build_groups`/`estimate_tokens`/`dfs_file_list` and `spring_signal_scan`'s `scan()` — it does not re-derive their arithmetic. It reports:

- **group count** — `groups.json`'s own `num_groups`
- **total subagent fan-out** across all five stages: Stage 1 (`file-summarizer`, one per group) + Stage 2 (`architect-segment` one per group, plus `architect-merge` always 1) + Stage 3 (`gap-analyzer` + `software-architect-and-testing`, fixed) + Stage 4 (`doc-writer`, `len(VALID_DOC_FILES)` — not a magic 14) = `2*num_groups + 3 + len(VALID_DOC_FILES)`
- **Stage-1 slice cost**: per-group `cross_group_edges.json` slice size (chars/N). Report `max` / `mean` / `total` — **max** bounds context risk.
- **Stage-4 shared-pool `partial_proxy_pre_stage4`**: Stage 0 cannot see summaries or `interview_answers` yet. The report sums group `est_tokens` (source-token *proxy* for future summaries) + optional signals, sets `stage4_omitted_not_estimated` (includes `interview_answers`, architecture beyond that proxy, return payloads), and may set `stage4_signals_omitted`. Numeric `*_upper_bound_*` field names are warn-threshold numbers only — **not** a claim that Stage-4 capacity risk is closed. Quiet Stage-1 ≠ quiet Stage 4; quiet proxy ≠ closed L2.

## Step 3 — threshold checks

The script warns (does not block) if any of the following, all **stated, tunable heuristic guesses pending real-world calibration**, are crossed:

- group count exceeds `--group-warn-threshold` (default 15) — rationale: untested territory for practical Task-tool dispatch concurrency in a single turn
- total fan-out exceeds `--fanout-warn-threshold` (default 40) — same rationale, compounded across stages
- the *largest single* Stage-1 slice exceeds `--slice-tokens-warn-threshold` (default 30,000 — a quarter of the default 120,000 per-group budget, and a stated guess with one real-repo data point behind it, not a calibrated ceiling)
- Stage-4 shared-pool **partial_proxy** exceeds `--stage4-shared-tokens-warn-threshold` (default 80,000 — stated guess; omits interview/returns)

Every threshold is a CLI flag, not a hidden constant — override any of them if you have better information about this specific repo or environment.

## Output

The script prints a short summary and, if `--out` was given, writes the same data as JSON. Present it to the user as a question, not a verdict: *"this repo would produce N groups and M total subagent dispatches, with a largest single Stage-1 edge slice of ~K tokens and a Stage-4 partial_proxy of ~P tokens (interview/returns not estimated) — proceed with the full run, split the repo with a smaller `--max-tokens`, or adjust thresholds?"* This skill has no authority to refuse the user's own request — it surfaces the number, it doesn't gate the run.

## What this deliberately does not do

- Does not change `partition_repo.py`'s own behavior, thresholds, or grouping logic.
- Does not run any LLM stage itself — no `file-summarizer`/`architect-segment`/`gap-analyzer`/`doc-writer` dispatch happens here.
- Does not validate whether the chars/N token heuristic matches Claude's real tokenizer — that calibration gap is named in `CONSTRAINTS.md` and stays open; this skill measures against the same heuristic, not a corrected one.
- Does not estimate Stage-4 **return** payloads or post-Stage-1 summary/interview sizes — that is adoption-queue **L2b**, after those artifacts exist.
- Does not cap or gate the actual pipeline run — it warns, once, before you decide.
- Does not claim Stage-4 capacity risk is closed.
