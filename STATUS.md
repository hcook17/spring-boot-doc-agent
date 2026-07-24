# Status

Current-state snapshot of `spring-boot-doc-agent`, edited in place — this file states what's true *right now*, not a history of how it got there. For the append-only history of individual commits and which `claude/steering-prompts/` assumptions they affect, see `claude/session-log.md`. The two are cross-linked, not duplicates: this file answers "where do things stand"; the log answers "what changed and when."

Last updated: 2026-07-23.

## Done, confirmed delivered

- **`scripts/test_pipeline_stages.py`** — mechanical structural test suite for the four previously-untested LLM stages (file-summarizer, architect-segment/architect-merge, gap-analyzer, doc-writer): tag-grammar validation, `[Evidenced — path:line]` citation resolution against real files, JSON output-shape validation, and architecture-node traceability. 17/17 passing, plus an opt-in real-artifacts pass gated behind `PIPELINE_ARTIFACTS_DIR`. Documented in `SKILL.md` and `README.md`. Resolves `claude/steering-prompts/01-testability-research-prompt.md`.

- **Six-item implementation handoff** (`IMPLEMENTATION_HANDOFF.md`) — all six items landed: orphaned `doc-taxonomy.md` copy removed, shared exclude-dir module, opt-in `--respect-gitignore`, doc-writer/doc-taxonomy tag-rule dedup, `build_groups()` strict-mode swap, repo-wide import/package reference index closing the file-summarizer group-boundary seam. Confirmed via git history (PR #1) and passing test suites, not by trusting the handoff doc's own claims.
- **`CONSTRAINTS.md`** — added at plugin root, covering runtime prerequisites, integration gaps, precision tradeoffs, confidentiality rules, and enterprise-readiness gaps. Cross-linked from `README.md` and `SKILL.md`. Resolves `claude/steering-prompts/03-constraints-research-prompt.md`.
- **`spring_drift_check.py` wired into docs** — documented as an optional Stage 0 pre-flight check in `SKILL.md`, and in `README.md`'s "On drift detection" section. Still standalone (not CI-triggered), which both files say explicitly. Resolves `claude/steering-prompts/06-wiredrift-check-task-prompt.md` and the re-scoped item 1 of `04-analytics-logging-research-prompt.md`.
- **Write-then-verify rule + this status doc** — `CONTRIBUTING.md` now states the write-then-verify rule explicitly (see that file for the two incidents that motivated it and the research behind it); this file is the "single current-state doc" half of `claude/steering-prompts/05-clarity-delivery-trust-research-prompt.md`'s ask.

## Pending

- **`claude/steering-prompts/02-pluggability-research-prompt.md`** — marked "partially resolved" in its own frontmatter (`references/` already moved as of 2026-07-23); not fully closed out.
- **`claude/steering-prompts/04-analytics-logging-research-prompt.md`** — item 1 (drift-check wiring) resolved; item 2, a `run_manifest.json` emitting per-stage timing/pass-fail and evidence-tag counts, is not built. Also listed as an open gap in `CONSTRAINTS.md`'s "Integration gaps" section.
- **`claude/steering-prompts/05-clarity-delivery-trust-research-prompt.md`** — this file and `CONTRIBUTING.md`'s rule cover scaffold items 1 and 2. Item 3's "genuinely useful small write-verification helper" was researched and found not to exist as an on-point, well-maintained GitHub project (see `CONTRIBUTING.md`'s research note) — codified as a checklist rule instead, per the prompt's own fallback instruction. A `PostToolUse` hook automating the re-read step is documented as a viable mechanism in `CONTRIBUTING.md` but not implemented; picking that up is the concrete next action for this prompt if automation (not just a documented checklist step) is wanted.
- **Enterprise-readiness gaps** (`CONSTRAINTS.md`'s own list, highest-priority first): license still `"UNLICENSED"`, no CI/CD wiring, no audit trail / run manifest, dependencies unpinned, no RBAC or multi-repo support.
- **Confidentiality gap** (`CONSTRAINTS.md`): no redaction guidance for real secret values a `file-summarizer` subagent might read directly out of a target repo's `application.yml`/`.properties` files. Open, unmitigated as of this writing.

## Next concrete action

If enterprise rollout is the near-term goal, start `CONSTRAINTS.md`'s stated close-out order: license → confidentiality/secret-redaction → CI wiring → dependency pinning → audit trail / run manifest → RBAC / multi-repo. Otherwise, `claude/steering-prompts/02-pluggability-research-prompt.md` (marked only "partially resolved") is the next open steering prompt.

## Cross-links

- `claude/session-log.md` — append-only commit history for steering-prompt-affecting changes.
- `claude/llms/README.md` — one file per PR, pairing that PR's summary with deterministic `git`/`grep` commands a reader can run to verify each claim directly, rather than trusting this file's or the session log's prose.
- `CONTRIBUTING.md` — write-then-verify rule and the research behind it.
- `CONSTRAINTS.md` — the plugin's standing constraints, a different axis from this file's done/pending tracking.
- `IMPLEMENTATION_HANDOFF.md` — the six-item handoff this file's "Done" section summarizes.
