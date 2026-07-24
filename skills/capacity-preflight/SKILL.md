---
name: capacity-preflight
description: Run before the document-spring-repo pipeline against a large or unfamiliar target repo to estimate cost and surface scale risk before committing to a full run — estimated group count and total subagent fan-out across all five stages, estimated size of the repo-wide references bucket attached to every Stage-1 dispatch, and warnings if any of these cross reasonable thresholds. Reuses partition_repo.py's and spring_signal_scan.py's own output rather than re-estimating from scratch. Use whenever pointing document-spring-repo at a repo you haven't run it against before, or one you suspect is large (monorepo, hundreds of files) — the full pipeline has no built-in warning today if group count or fan-out is large enough to hit practical concurrency or context limits.
---

# Capacity preflight

## Why this exists

`CONSTRAINTS.md` and `skills/document-spring-repo/SKILL.md` already name several scale assumptions nobody has load-tested against a real large repo: token counts are a chars/N heuristic, not Claude's real tokenizer; `build_groups()` picks a planning-target group count, not a hard cap; and the repo-wide `references` bucket is attached, in full, to *every* Stage-1 dispatch — SKILL.md's own text calls this "worth confirming against a real repo's actual size rather than just assumed." This skill turns those from prose warnings into a concrete number for *this specific* target repo, before you commit to a full five-stage run.

## Step 1 — run Stage 0's own scripts

This skill does not duplicate `document-spring-repo`'s Stage 0 logic — it reads that stage's own output. If you don't already have `spring_signals.json`/`groups.json` for this repo, run them exactly as `skills/document-spring-repo/SKILL.md`'s Stage 0 documents:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/spring_signal_scan.py" <repo_path> --out spring_signals.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/partition_repo.py" <repo_path> --max-tokens 120000 --out groups.json
```

If you already have both from a prior run of this same repo, skip straight to Step 2 and pass them in — a preflight should be fast, not a second full scan every time.

## Step 2 — derive the numbers

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/capacity_preflight.py" <repo_path> \
    --groups-file groups.json --signals-file spring_signals.json \
    --out capacity_preflight_report.json
```

(Omit `--groups-file`/`--signals-file` to have it run Stage 0's scripts itself.) This script only *imports* `partition_repo.py`'s `build_groups`/`estimate_tokens`/`dfs_file_list` and `spring_signal_scan.py`'s `scan()` — it does not re-derive their arithmetic. It reports:

- **group count** — `groups.json`'s own `num_groups`
- **total subagent fan-out** across all five stages: Stage 1 (`file-summarizer`, one per group) + Stage 2 (`architect-segment` one per group, plus `architect-merge` always 1) + Stage 3 (`gap-analyzer`, always exactly 1 — the interview itself is the orchestrating thread, not a subagent dispatch, so it isn't counted) + Stage 4 (`doc-writer`, always exactly 14) = `2*num_groups + 16`
- **references-bucket cost**: the size of `spring_signals.json`'s `references` bucket, estimated in tokens via `partition_repo.py`'s own chars/N estimator, multiplied by `num_groups` — the concrete number for "total tokens spent repo-wide across all Stage-1 dispatches just for this one shared bucket."

## Step 3 — threshold checks

The script warns (does not block) if any of the following, all **stated, tunable heuristic guesses pending real-world calibration**, are crossed:

- group count exceeds `--group-warn-threshold` (default 15) — rationale: untested territory for practical Task-tool dispatch concurrency in a single turn
- total fan-out exceeds `--fanout-warn-threshold` (default 40) — same rationale, compounded across stages
- references-bucket-tokens-times-groups exceeds `--references-tokens-warn-threshold` (default 500,000) — the specific number SKILL.md flags as unverified

Every threshold is a CLI flag, not a hidden constant — override any of them if you have better information about this specific repo or environment.

## Output

The script prints a short summary and, if `--out` was given, writes the same data as JSON. Present it to the user as a question, not a verdict: *"this repo would produce N groups and M total subagent dispatches, with an estimated K tokens on the shared references bucket alone — proceed with the full run, split the repo with a smaller `--max-tokens`, or adjust thresholds?"* This skill has no authority to refuse the user's own request — it surfaces the number, it doesn't gate the run.

## What this deliberately does not do

- Does not change `partition_repo.py`'s own behavior, thresholds, or grouping logic.
- Does not run any LLM stage itself — no `file-summarizer`/`architect-segment`/`gap-analyzer`/`doc-writer` dispatch happens here.
- Does not validate whether the chars/N token heuristic matches Claude's real tokenizer — that calibration gap is named in `CONSTRAINTS.md` and stays open; this skill measures against the same heuristic, not a corrected one.
- Does not cap or gate the actual pipeline run — it warns, once, before you decide.
