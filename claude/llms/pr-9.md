---
pr: 9
title: "Add claude/llms/: deterministic-verification index for this repo's PR history"
state: MERGED
branch: pr-verification-index -> main
merge_commit: 3454c4cf6c54be07841813a8e0231ab93c00c0a4
---

# PR #9 — Add claude/llms/: deterministic-verification index for this repo's PR history

## Summary

Adds `claude/llms/README.md` plus `pr-1.md` through `pr-8.md` — one file per PR in this repo's history so far, each pairing that PR's summary with `git show <sha>:<path> | grep ...` / `git worktree` commands pinned to the PR's actual commit(s), so a reader can confirm each claim directly instead of re-reading the full diff or trusting the summary prose. Every heuristic in every file was run against the pinned commit before being written down, not just reasoned about (the session that produced this PR caught one false positive this way: `pr-8.md`'s fixture-reuse check needed `--format=""` to exclude the commit message text from the grep, which otherwise false-matched on prose that happened to mention "fixture"). PR #8 was still open at write time, so `pr-8.md` originally pinned to its head commit rather than a merge commit (later repinned in PR #11 once #8 merged). Cross-linked from `README.md` and `STATUS.md`. Doc-only — no code touched.

Merged via `3454c4c`. This file itself is part of the later backfill (see `check_llms_coverage.py`) that closed the gap of PR #9 having no `pr-9.md` of its own.

## Deterministic verification

Pinned to `3454c4c`:

1. **Claim: adds one file per PR for PRs #1-#8 (8 files) plus the README index.**
   `git show --stat --format="" 3454c4c | grep -c "claude/llms/pr-"`
   Expect: `8`.

2. **Claim: cross-linked from README.md and STATUS.md.**
   `git show 3454c4c:README.md | grep -n "claude/llms"`
   `git show 3454c4c:STATUS.md | grep -n "claude/llms"`
   Expect: at least one match in each.

3. **Claim: documentation-only change — no code touched.**
   `git show --stat --format="" 3454c4c | grep -v "\.md"`
   Expect: only the trailing "11 files changed, 321 insertions(+), 1 deletion(-)" summary line — every individual changed-file line has a `.md` extension and is filtered out by the `-v`.
