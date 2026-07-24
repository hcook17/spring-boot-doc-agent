---
category: Scaffold this repo's first CI job, plus a meta-verification script for claude/llms/ (not a research prompt — implementation task)
status: not started
related: CONSTRAINTS.md ("Integration gaps" item 2 "no CI/CD" and item 4 "claude/llms/ meta-drift", "Enterprise-readiness gaps" item 6), claude/llms/README.md, IMPLEMENTATION_HANDOFF.md (style precedent for this task's level of detail)
---

# Task prompt: scaffold this repo's first CI job, plus a meta-verification script for claude/llms/

Self-contained — read this without assuming any other conversation's context.

Context: `spring-boot-doc-agent` is a Claude Code plugin (this repo) with real Python test suites — `test_spring_signal_scan.py`, `test_partition_repo.py`, `test_spring_drift_check.py` (needs the `ast-grep` binary on `PATH`), and `test_pipeline_stages.py` (stdlib only, no `ast-grep` needed) — run entirely by hand today. There is no `.github/workflows/` directory and no CI of any kind, confirmed absent (`CONSTRAINTS.md`'s "Integration gaps" item 2 and "Enterprise-readiness gaps" item 6).

Separately, `claude/llms/pr-1.md` through `pr-8.md` (see `claude/llms/README.md`) each contain a set of `git show`/`grep`/`git worktree` commands, hand-verified correct against the commit they're pinned to at write-time, that let a reader confirm a PR's claims without re-reading the diff. Nothing re-runs those commands automatically, so a later rename/refactor elsewhere in the repo can make one silently stop matching (or start matching something else) with no signal to a reader (`CONSTRAINTS.md`'s "Integration gaps" item 4 — found via a 2026-07-23 principal-engineer review of PR #9's GitHub page: `Checks: 0`, `No reviews`, `1 participant`, still rendered "Ready to merge").

This task closes both gaps in one pass: a script that mechanically re-verifies `claude/llms/`'s own commands, wired — alongside the existing test suites — into this repo's first CI workflow.

## Do this

1. **`scripts/verify_llms_docs.py`** — stdlib-only, matching this repo's existing scripts' dependency discipline (no new package). For each `claude/llms/pr-*.md` file:
   - Parse out each command. **Read `claude/llms/pr-1.md` directly first to confirm the real current format before writing a parser against it** — don't assume a rigid fenced-code-block shape; as of this prompt being written the eight files use inline single-backtick commands under numbered claims, but that's exactly the kind of detail worth re-checking live rather than trusting this paragraph.
   - Distinguish commands safe to auto-run (`git show`, `grep`, plain read-only git plumbing) from ones with real side effects (`git worktree add`/`remove`). Decide deliberately whether to auto-run the worktree-based checks in CI (a fresh checkout per job avoids `/tmp` path collisions, but confirm that reasoning rather than assuming it) or skip them with an explicit, printed reason — don't silently drop them.
   - Report pass/fail **per command**, not per file — one file with five checks and one failure should say which one broke, the way this repo's other suites already report per-test-case, not per-file.
   - Exit non-zero if anything fails, so CI can gate on it.
   - Not a full shell parser — mechanical and narrowly scoped, matching `test_pipeline_stages.py`'s own docstring precedent ("mechanical wherever possible, don't over-engineer"). If a command is too complex to safely auto-parse and re-run, skip it explicitly with a `"not auto-verified: <reason>"` line rather than crashing or silently ignoring it.

2. **`.github/workflows/` — this repo's first-ever CI file.** Needs:
   - Checkout, Python setup — confirm the actual Python version this repo's scripts target (`python3 --version` locally, and check for any version hints already in the repo) rather than assuming 3.10.
   - `ast-grep` on `PATH` — `cargo install ast-grep` is slow in CI; check `ast-grep`'s own repo/docs for a CI-friendly install path (a published GitHub Action, a prebuilt binary release, or `npm install -g @ast-grep/cli`) before picking one, the same "verify, don't assume" standard the rest of this repo holds itself to.
   - Run, in order: `test_spring_signal_scan.py`, `test_partition_repo.py`, `test_spring_drift_check.py`, `test_pipeline_stages.py` (confirm this file actually exists on `main` by the time you do this work — it shipped on the `testability-pipeline-stages` branch and may or may not have merged yet; check, don't assume), and the new `verify_llms_docs.py`.
   - Install the soft dependencies too (`pip install sqllineage pathspec`) so CI exercises full coverage rather than silently skipping soft-dependency-gated tests.
   - Trigger on `pull_request` targeting `main` at minimum; `push` to `main` is a reasonable addition.

3. **Do not touch branch protection or required reviews as a side effect of this task.** That's a repo-admin action with real blast radius (a misconfigured rule can lock the repo owner out of their own pushes) — out of scope for a code-only PR. Once the workflow has landed and gone green at least once, leave a clear note — in the PR description and in `CONSTRAINTS.md`'s "Enterprise-readiness gaps" item 6 — that branch protection requiring this new check plus at least one review is the natural next step, including the exact `gh api` command a repo admin would run to enable it. Don't run that command yourself.

4. **Update `CONSTRAINTS.md` and `STATUS.md`** once this lands: mark the "no CI/CD wiring" and "`claude/llms/` meta-drift" items resolved (or explicitly partially-resolved, if branch protection is deliberately left as the follow-up per item 3), and update `STATUS.md`'s Done/Pending/Next-concrete-action sections to match.

5. **Append a `claude/session-log.md` entry** per `CLAUDE.md`'s convention — this touches `scripts/` directly, so it qualifies without needing to weigh whether it's "relevant enough."

6. Commit on a new branch off `main` — this repo's usual one-branch-per-concern convention. **Confirm the Actions run is actually green on GitHub after pushing, not just that the YAML is syntactically plausible** — this repo's own standing rule from `IMPLEMENTATION_HANDOFF.md`, "verify by running, not by reading," applies here as much as anywhere else in this codebase. Open a PR, report back the PR URL and the Actions run URL.

## What NOT to do here

- Don't build a general-purpose CI framework — one workflow file plus one narrowly-scoped verification script, sized to what's actually missing, per `claude/steering-prompts/00-shared-research-standards.md`'s "what scaffold and implement means" (no new infrastructure beyond what's already assumed).
- Don't touch branch protection settings (see item 3) — document the follow-up, don't perform it.
- Don't retrofit `run_manifest.json` (`claude/steering-prompts/04-analytics-logging-research-prompt.md`'s still-open item) into this task — a different, separately-tracked gap.
