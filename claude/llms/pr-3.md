---
pr: 3
title: Document and wire spring_drift_check.py into pipeline docs
state: MERGED
branch: wire-in-drift-check -> main
merge_commit: 274c6d3d10af26386cce43ec45b5961f19aadd4e
---

# PR #3 — Document and wire spring_drift_check.py into pipeline docs

## Summary

`spring_drift_check.py` (a real, tested two-tier drift detector) existed but was undocumented and unwired. Adds it to `SKILL.md` as an optional Stage 0 pre-flight check and to `README.md` as an "On drift detection" section. Fixes a real Windows path-separator bug in `tier1_scan()` (`os.path.relpath()` not normalized to forward slashes, which made every file falsely read as "deleted" on Windows) and a stale test assertion whose expected count predated the `references` bucket being cited as evidence. Also adds `LICENSE` (MIT) and `claude/steering-prompts/06-wiredrift-check-task-prompt.md`.

## Deterministic verification

Pinned to `274c6d3`:

1. **Claim: `SKILL.md` documents drift-check as an optional Stage 0 pre-flight step.**
   `git show 274c6d3:skills/document-spring-repo/SKILL.md | grep -n "spring_drift_check\|pre-flight"`
   Expect: multiple matches, including a `### Optional pre-flight` heading.

2. **Claim: `README.md` gained an "On drift detection" section.**
   `git show 274c6d3:README.md | grep -n "^## On drift detection"`
   Expect: one match.

3. **Claim: the Windows path-separator bug was fixed by normalizing to forward slashes, matching `spring_signal_scan.py`'s existing convention.**
   `git show 274c6d3:scripts/spring_drift_check.py | grep -n 'relpath(full, repo_path).replace'`
   Expect: one match, `.replace("\\\\", "/")` immediately after the `relpath()` call.
   Cross-check the convention it's matching: `git show 274c6d3:scripts/spring_signal_scan.py | grep -n 'relpath.*replace'`
   Expect: the same pattern already present there.

4. **Claim: a stale test assertion was corrected — 8 citations (1 drift, 7 confirm), not 5/4.**
   `git show 274c6d3:scripts/test_spring_drift_check.py | grep -n "def test_single_mapping_change_does_not_flag_sibling_citations" -A 20`
   Expect: assertions referencing 8 total citations, not the old 4/5.

5. **Claim: LICENSE (MIT) was added in this PR.**
   `git show 274c6d3:LICENSE | head -3`
   Expect: MIT License boilerplate text.

6. **Claim: 12/12 and 32/32 tests passing at merge time.**
   `git worktree add /tmp/pr3-check 274c6d3 && cd /tmp/pr3-check && python3 scripts/test_spring_drift_check.py -v && python3 scripts/test_spring_signal_scan.py -v; cd - && git worktree remove /tmp/pr3-check`
   Expect: `OK` with 12 and 32 tests respectively.
