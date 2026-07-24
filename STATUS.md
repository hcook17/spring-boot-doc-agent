# Status

Current-state snapshot of `spring-boot-doc-agent`, edited in place — this file states what's true *right now*, not a history of how it got there. For the append-only history of individual commits and which `claude/steering-prompts/` assumptions they affect, see `claude/session-log.md`. The two are cross-linked, not duplicates: this file answers "where do things stand"; the log answers "what changed and when."

Last updated: 2026-07-23.

## Done, confirmed delivered

- **This repo's first CI workflow** (`.github/workflows/ci.yml`) — runs on every `pull_request`/`push` to `main`: all four existing test suites (`test_spring_signal_scan.py`, `test_partition_repo.py`, `test_spring_drift_check.py`, `test_pipeline_stages.py`) plus the two new items below, against a full-history checkout with `ast-grep` installed via `pip install ast-grep-cli` (avoids a slow `cargo install` build). Resolves `claude/steering-prompts/07-ci-scaffold-task-prompt.md` and `CONSTRAINTS.md`'s "Integration gaps" item 2. Branch protection requiring this check to pass is a deliberately separate, not-yet-taken next step — see `CONSTRAINTS.md`'s "Enterprise-readiness gaps" item 6 for the exact `gh api` command.
- **`scripts/verify_llms_docs.py` + `scripts/test_verify_llms_docs.py`** — mechanically re-runs every documented `git`/`gh` command across `claude/llms/pr-*.md` on each CI run, so a stale or drifted verification command fails the build instead of going unnoticed. Resolves `CONSTRAINTS.md`'s "Integration gaps" item 4. Found and fixed one real instance of the exact drift it now guards against while building it: `claude/llms/pr-8.md`/`README.md` still said PR #8 was open well after it had actually merged (`a0acc76`) — repinned to the merge commit and re-verified.
- **Secret/credential-redaction heuristic** (`scripts/_secret_heuristics.py`) — `spring_signal_scan.py` now flags `redaction_zones` (file/line/heuristic, never the value) for configuration/deployment files; `agents/file-summarizer.md`, `agents/doc-writer.md`, and `doc-taxonomy.md`'s configuration.md notes now all say not to transcribe a flagged line's value. `scripts/check_no_secrets_leaked.py` re-applies the same heuristics to a completed run's own output as a deterministic defense-in-depth check (documented in `SKILL.md` as an optional post-run step). Resolves `CONSTRAINTS.md`'s "Secret/credential leakage" gap, heuristically — stated residual scope, not a guarantee (see that file's entry).
- **Six-item implementation handoff** (`IMPLEMENTATION_HANDOFF.md`) — all six items landed: orphaned `doc-taxonomy.md` copy removed, shared exclude-dir module, opt-in `--respect-gitignore`, doc-writer/doc-taxonomy tag-rule dedup, `build_groups()` strict-mode swap, repo-wide import/package reference index closing the file-summarizer group-boundary seam. Confirmed via git history (PR #1) and passing test suites, not by trusting the handoff doc's own claims.
- **`CONSTRAINTS.md`** — added at plugin root, covering runtime prerequisites, integration gaps, precision tradeoffs, confidentiality rules, and enterprise-readiness gaps. Cross-linked from `README.md` and `SKILL.md`. Resolves `claude/steering-prompts/03-constraints-research-prompt.md`.
- **`spring_drift_check.py` wired into docs** — documented as an optional Stage 0 pre-flight check in `SKILL.md`, and in `README.md`'s "On drift detection" section. Still standalone (not CI-triggered), which both files say explicitly. Resolves `claude/steering-prompts/06-wiredrift-check-task-prompt.md` and the re-scoped item 1 of `04-analytics-logging-research-prompt.md`.
- **Write-then-verify rule + this status doc** — `CONTRIBUTING.md` now states the write-then-verify rule explicitly (see that file for the two incidents that motivated it and the research behind it); this file is the "single current-state doc" half of `claude/steering-prompts/05-clarity-delivery-trust-research-prompt.md`'s ask.

## Pending

- **`claude/steering-prompts/01-testability-research-prompt.md`** — not started. No test coverage exists for the four LLM pipeline stages (`file-summarizer`, `architect-segment`/`architect-merge`, `gap-analyzer`, `doc-writer`); only the two deterministic scripts are tested.
- **`claude/steering-prompts/02-pluggability-research-prompt.md`** — marked "partially resolved" in its own frontmatter (`references/` already moved as of 2026-07-23); not fully closed out.
- **`claude/steering-prompts/04-analytics-logging-research-prompt.md`** — item 1 (drift-check wiring) resolved; item 2, a `run_manifest.json` emitting per-stage timing/pass-fail and evidence-tag counts, is not built. Also listed as an open gap in `CONSTRAINTS.md`'s "Integration gaps" section.
- **`claude/steering-prompts/05-clarity-delivery-trust-research-prompt.md`** — this file and `CONTRIBUTING.md`'s rule cover scaffold items 1 and 2. Item 3's "genuinely useful small write-verification helper" was researched and found not to exist as an on-point, well-maintained GitHub project (see `CONTRIBUTING.md`'s research note) — codified as a checklist rule instead, per the prompt's own fallback instruction. A `PostToolUse` hook automating the re-read step is documented as a viable mechanism in `CONTRIBUTING.md` but not implemented; picking that up is the concrete next action for this prompt if automation (not just a documented checklist step) is wanted.
- **Enterprise-readiness gaps** (`CONSTRAINTS.md`'s own list, highest-priority first): license still `"UNLICENSED"`, no audit trail / run manifest, dependencies unpinned, no RBAC or multi-repo support, and branch protection still not configured on `main` even though a required-check candidate (the new CI workflow) now exists (see `CONSTRAINTS.md` item 6 for the exact `gh api` command a repo admin would run).
## Next concrete action

`claude/steering-prompts/01-testability-research-prompt.md` (LLM-stage testability — `test_pipeline_stages.py` covers structural regression, but the deeper research prompt isn't closed out) is the next open steering prompt, or `CONSTRAINTS.md`'s remaining close-out order if enterprise rollout is the goal: license → branch protection + required reviews (CI wiring itself is now done; confidentiality/secret-redaction is now done too, heuristically) → dependency pinning → audit trail / run manifest → RBAC / multi-repo.

## Cross-links

- `claude/session-log.md` — append-only commit history for steering-prompt-affecting changes.
- `CONTRIBUTING.md` — write-then-verify rule and the research behind it.
- `CONSTRAINTS.md` — the plugin's standing constraints, a different axis from this file's done/pending tracking.
- `IMPLEMENTATION_HANDOFF.md` — the six-item handoff this file's "Done" section summarizes.

