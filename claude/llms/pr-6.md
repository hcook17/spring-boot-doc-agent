---
pr: 6
title: License and version update
state: MERGED
branch: wire-in-drift-check -> main
merge_commit: 08a588eb82c78e12e4d7c5a059e90d4a4031f618
---

# PR #6 — License and version update

## Summary

No PR body was written for this one either (confirmed absent via `gh pr view 6 --json body`) — reconstructed from the single commit's diff. Updates `.claude-plugin/plugin.json` (`version` 0.2.0 → 0.3.0, `author.name` `EHE-ECM` → `Hunter Cook`, `license` field present as `MIT`) and `.claude-plugin/marketplace.json` (`owner.name` `EHE-ECM` → `Hunter Cook`). Note this PR reuses the `wire-in-drift-check` branch name that PR #3 also used — they are two separate PRs/merges, not the same one; don't conflate them when reading `git log` output for that branch name.

## Deterministic verification

Pinned to `08a588e`:

1. **Claim: version bumped 0.2.0 → 0.3.0.**
   `git show 08a588e^1:.claude-plugin/plugin.json | grep -n '"version"'`
   `git show 08a588e:.claude-plugin/plugin.json | grep -n '"version"'`
   Expect: `0.2.0` before, `0.3.0` at this commit.

2. **Claim: author/owner name changed from `EHE-ECM` to `Hunter Cook` in both plugin files.**
   `git show 08a588e:.claude-plugin/plugin.json | grep -n '"name": "Hunter Cook"'`
   `git show 08a588e:.claude-plugin/marketplace.json | grep -n '"name": "Hunter Cook"'`
   Expect: one match each.

3. **Claim: exactly 2 files changed, 3 net insertions.**
   `git show --stat 08a588e^1..08a588e`
   Expect: `.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json` — 2 files, 3 insertions(+), 3 deletions(-).

4. **Claim: this PR reused a branch name (`wire-in-drift-check`) already used by PR #3 — verify they're distinct merges.**
   `gh pr view 3 --json headRefName,mergeCommit --jq '{branch: .headRefName, merge: .mergeCommit.oid}'`
   `gh pr view 6 --json headRefName,mergeCommit --jq '{branch: .headRefName, merge: .mergeCommit.oid}'`
   Expect: same `headRefName`, different `merge` SHAs (`274c6d3` vs `08a588e`).
