---
pr: 8
title: Add structural tests for the four LLM pipeline stages
state: MERGED
branch: testability-pipeline-stages -> main
merge_commit: a0acc7669ac056cbd57dafd22f89a0dcba8dbf51
head_commit: 3eb1551fbc893d04004132f60f8d344b5a9ef22c
---

# PR #8 — Add structural tests for the four LLM pipeline stages

## Summary

Adds `scripts/test_pipeline_stages.py`, a mechanical (not LLM-judge) structural test suite for the four previously-untested LLM stages — `file-summarizer`, `architect-segment`/`architect-merge`, `gap-analyzer`, `doc-writer`. Validates the exact five-form tag grammar, `[Evidenced — path:line]` citation resolution against real files, `file-summarizer`/`gap-analyzer` JSON output shapes, and architecture-node traceability, by default against synthetic sample data (no LLM calls). Reuses the existing `scripts/test_fixtures/spring_signals/` fixture rather than building a second one. Adds an opt-in `PIPELINE_ARTIFACTS_DIR` pass to validate a real completed run's output. Resolves `claude/steering-prompts/01-testability-research-prompt.md`.

Merged via `a0acc76` (parents `bfcb324` and head commit `3eb1551`) — a true merge, not a squash/rebase: `a0acc76`'s tree is identical to `3eb1551`'s (`git rev-parse a0acc76^{tree} 3eb1551^{tree}` both resolve to `d821253b`). Commands below are pinned to the merge commit `a0acc76`, superseding this file's earlier note that they'd need to be repinned once the PR merged — that repinning is done here.

## Deterministic verification

Pinned to `a0acc76`:

1. **Claim: 17 tests, 1 correctly skipped by default.**
   `git worktree add /tmp/pr8-check a0acc76 && cd /tmp/pr8-check && python3 scripts/test_pipeline_stages.py -v 2>&1 | tail -5; cd - && git worktree remove /tmp/pr8-check`
   Expect: `Ran 17 tests ... OK (skipped=1)`.

2. **Claim: no new runtime dependency was introduced — stdlib only.**
   `git show a0acc76:scripts/test_pipeline_stages.py | grep -n "^import\|^from"`
   Expect: only `json`, `os`, `re`, `unittest` (all stdlib) — no `import requests`, no third-party package.

3. **Claim: the existing `scripts/test_fixtures/spring_signals/` fixture is reused, not duplicated.**
   `git show --stat --format="" a0acc76 | grep -i fixture`
   Expect: no output — no new fixture files under `scripts/test_fixtures/` (use `--format=""` to exclude the commit message itself, which mentions "fixture" in prose and would otherwise false-positive this check).
   `git show a0acc76:scripts/test_pipeline_stages.py | grep -n "FIXTURE_DIR ="`
   Expect: it resolves to `test_fixtures/spring_signals` (the pre-existing directory), not a new one.

4. **Claim: the opt-in real-artifacts pass is gated by `PIPELINE_ARTIFACTS_DIR` and skips cleanly when unset, matching `test_partition_repo_real_world.py`'s pattern.**
   `git show a0acc76:scripts/test_pipeline_stages.py | grep -n "PIPELINE_ARTIFACTS_DIR\|SkipTest"`
   Expect: the env var read in `setUpClass`, raising `unittest.SkipTest` when absent.

5. **Claim: existing suites still pass — no regression.**
   `git worktree add /tmp/pr8-check2 a0acc76 && cd /tmp/pr8-check2 && python3 scripts/test_partition_repo.py 2>&1 | tail -3 && python3 scripts/test_spring_signal_scan.py 2>&1 | tail -3; cd - && git worktree remove /tmp/pr8-check2`
   Expect: `OK` for both (13 and 32 tests respectively).

6. **Claim: `SKILL.md` and `README.md` document how to run the new suite.**
   `git show a0acc76:skills/document-spring-repo/SKILL.md | grep -n "test_pipeline_stages"`
   `git show a0acc76:README.md | grep -n "test_pipeline_stages"`
   Expect: at least one match in each.
