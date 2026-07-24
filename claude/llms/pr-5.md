---
pr: 5
title: Fix README.md merge artifact from PR #3/#4
state: MERGED
branch: fix-readme-merge-artifact -> main
merge_commit: 79e0b7d05124be9832811620aa3096ac14e07d23
---

# PR #5 — Fix README.md merge artifact from PR #3/#4

## Summary

Combining PR #3 (drift-check docs) and PR #4 (CONSTRAINTS.md) into `main` left the "Constraints" and "On drift detection" sections of `README.md` adjacent with no blank line between them, and in the wrong logical order (Constraints referencing content that appeared below it). Reordered so "On drift detection" precedes "Constraints," restored the missing blank line. No content changes — formatting only, one file.

## Deterministic verification

Pinned to `79e0b7d`:

1. **Claim: only `README.md` changed, no content rewritten — pure reorder/whitespace.**
   `git show --stat 79e0b7d^1..79e0b7d`
   Expect: exactly 1 file changed (`README.md`), 4 insertions, 3 deletions — small enough to be a reorder, not a rewrite.

2. **Claim: "On drift detection" now precedes "Constraints" in reading order.**
   `git show 79e0b7d:README.md | grep -n "^## On drift detection\|^## Constraints"`
   Expect: the "On drift detection" line number is smaller (comes first).

3. **Claim: the actual diff is a section swap, not new prose.**
   `git diff 79e0b7d^1 79e0b7d -- README.md`
   Expect: the diff shows the same two section bodies present both before and after, just reordered — no new sentences introduced.
