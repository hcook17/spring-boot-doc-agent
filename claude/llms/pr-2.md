---
pr: 2
title: New prompts and skill update
state: MERGED
branch: prompt-and-plugin-additions -> main
merge_commit: bcd339b082ee50e56cfc86806644ab935dc199c4
---

# PR #2 — New prompts and skill update

## Summary

No PR body was written for this one (confirmed absent via `gh pr view 2 --json body`) — this summary is reconstructed from the single commit's actual diff, not from PR prose. Touches five files: bumps `.claude-plugin/plugin.json`'s version, updates a `baseline-reference/` copy of `SKILL.md`, and revises the wording/scope of three steering prompts (`02-pluggability`, `03-constraints`, `04-analytics-logging`).

## Deterministic verification

Pinned to `bcd339b` (single commit `c65d89e` inside the merge):

1. **Claim: exactly five files changed, matching the summary above.**
   `git show --stat bcd339b^1..bcd339b`
   Expect: `.claude-plugin/plugin.json`, `baseline-reference/skills/document-spring-repo/SKILL.md`, and the three named steering prompts — 5 files, 52 insertions, 29 deletions.

2. **Claim: no PR body exists (this summary is diff-reconstructed, not PR-prose-derived).**
   `gh pr view 2 --json body --jq '.body'`
   Expect: empty output.

3. **Claim: the three steering prompts were revised, not newly created (they predate this PR).**
   `git log --follow --format='%H %s' -- claude/steering-prompts/03-constraints-research-prompt.md | tail -5`
   Expect: an earlier commit than `c65d89e` that first added the file (from PR #1), confirming this PR edited existing content rather than introducing it.
