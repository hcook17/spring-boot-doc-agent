---
pr: 1
title: Implement six agreed fixes from IMPLEMENTATION_HANDOFF.md
state: MERGED
branch: implement-handoff-items -> main
merge_commit: 0b7b7de1ff7c02201fb9364e3fcbeda90f757953
---

# PR #1 — Implement six agreed fixes from IMPLEMENTATION_HANDOFF.md

## Summary

Implements Step 0 (baseline reconciliation, fixing a Windows path-separator bug found while re-running the suite) plus all six agreed fixes from `IMPLEMENTATION_HANDOFF.md`: deleted the orphaned root-level `references/doc-taxonomy.md`; added `scripts/_shared_excludes.py` as the single source of truth for excluded directories (closing a gap where `vendor`/`venv`/`.venv`/`env`/`coverage` weren't excluded from `spring_signal_scan.py`); added an opt-in `--respect-gitignore` flag to both scripts; deduplicated the five-tag evidence rule between `doc-writer.md` and `doc-taxonomy.md`; swapped `build_groups()` to check-before-append ("strict") semantics; and added a generic `references__import`/`references__package` ast-grep rule closing file-summarizer's cross-group blind spot.

## Deterministic verification

Pinned to `0b7b7de`. Run from the repo root, any branch checked out:

1. **Claim: a shared exclude-dir module exists and is the single source of truth.**
   `git show 0b7b7de:scripts/_shared_excludes.py | grep -n "DEFAULT_EXCLUDED_DIRS = frozenset"`
   Expect: one match, line 16.
   `git show 0b7b7de:scripts/partition_repo.py | grep -n "from _shared_excludes import"`
   Expect: one match.

2. **Claim: `build_groups()` was swapped to check-before-append ("strict") semantics.**
   `git show 0b7b7de:scripts/partition_repo.py | grep -n "def build_groups\|check-before-append\|would_exceed_hard_cap"`
   Expect: the function definition plus the "Check-before-append" docstring language and the `would_exceed_hard_cap` guard variable.

3. **Claim: a new zero-progress-guard regression test was added.**
   `git show 0b7b7de:scripts/test_partition_repo.py | grep -n "def test_strict_mode_zero_progress_guard"`
   Expect: one match.

4. **Claim: a repo-wide `references` bucket/ast-grep rule closes the cross-group relationship blind spot.**
   `git show 0b7b7de:scripts/spring_ast_grep_rules.yml | grep -n "id: references__import\|id: references__package"`
   Expect: two matches.
   `git show 0b7b7de:agents/file-summarizer.md | grep -n "cross_group_relationships"`
   Expect: at least one match (the documented output field).

5. **Claim: 13/13 and 32/32 tests passing at merge time.**
   `git worktree add /tmp/pr1-check 0b7b7de && cd /tmp/pr1-check && python3 scripts/test_partition_repo.py -v && python3 scripts/test_spring_signal_scan.py -v; cd - && git worktree remove /tmp/pr1-check`
   Expect: `OK` with 13 and 32 tests respectively. Uses a disposable worktree rather than touching your current checkout.
