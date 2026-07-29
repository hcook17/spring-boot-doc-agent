---
category: Wire spring_drift_check.py into the workflow (not a research prompt — implementation task)
status: resolved (2026-07-23, PR #3) — steps 3–4 landed: `spring_drift_check.py` is documented as an optional pre-flight check in `skills/document-spring-repo/SKILL.md` ("Optional pre-flight: checking for drift before a full re-run") and in `README.md`'s "On drift detection" section. Still standalone and not CI-triggered — CI runs `test_spring_drift_check.py`, not the tool itself — which both files state explicitly, and which is deliberate scope rather than a gap. See `STATUS.md`.
related: 03-constraints-research-prompt.md (Integration gap item), 04-analytics-logging-research-prompt.md (re-scoped item 1)
note: this field read `not started` from PR #3 until 2026-07-24 — stale for the whole of that window, and flagged three separate times in `claude/session-log.md` before anyone corrected it. Both copies (repo and Claude project) carried the stale value.
verify:
  - contains:skills/document-spring-repo/SKILL.md:doc_engine.tools.spring_drift_check
  - contains:README.md:doc_engine.tools.spring_drift_check
---

# Task prompt: document and wire in the existing drift-check tool

Self-contained — read this without assuming any other conversation's context.

Context: spring-boot-doc-agent is a Claude Code plugin (this repo) that scans a Spring Boot repo and generates 14 docs across a five-stage pipeline, documented in `skills/document-spring-repo/SKILL.md`. `scripts/spring_drift_check.py` already exists — a real, working two-tier drift detector (Tier 1: whole-repo file-signature hashing against a prior scan's `file_signatures` map; Tier 2: for files that changed, targeted per-citation re-verification via `ast-grep`, re-deriving the same identity `spring_signal_scan.py` itself extracts per rule type). It has a real test suite (`scripts/test_spring_drift_check.py`). Its own module docstring says plainly: "Standalone tool... not wired into the document-spring-repo pipeline, not triggered by CI." `README.md` doesn't mention it at all.

Do this:

1. Read `scripts/spring_drift_check.py`'s module docstring and CLI argument handling in full first — don't guess at its interface. Confirm exactly what inputs it takes (a repo path, a prior `spring_signals.json`) and what it outputs, directly from the code, not from this prompt's description of it.

2. Read `scripts/test_spring_drift_check.py` to see how it's actually invoked in practice — that's the most concrete evidence of correct usage.

3. Add a documented way to run it in `skills/document-spring-repo/SKILL.md`, framed as an optional pre-flight check: before committing to a full five-stage re-run against a repo you've already scanned once, run `spring_drift_check.py` against the prior `spring_signals.json` to see what's actually drifted, and use that to decide whether a full re-run is warranted or whether only specific files/claims need attention. Match `SKILL.md`'s existing prose style (see how Stage 0 documents `spring_signal_scan.py` and `partition_repo.py` for the pattern to follow) — don't invent a new formatting convention for this section.

4. Add a paragraph to `README.md` describing what it does and how to run it — same section style as the existing "On the deterministic scan" section, which is a good model: what it does, why it exists, how to invoke it, and current limitations (it's standalone, not CI-triggered, that's a deliberate current scope, not a bug).

5. Run the existing test suite (`scripts/test_spring_drift_check.py -v`) to confirm nothing about this documentation change touched behavior — it shouldn't, since you're only adding docs/plumbing, not changing the script itself. Report the pass count.

6. Per `CLAUDE.md`'s convention: this change plausibly affects two steering prompts — `claude/steering-prompts/03-constraints-research-prompt.md` (its "Integration gap, not a scope cut" item, which specifically names this exact task) and `claude/steering-prompts/04-analytics-logging-research-prompt.md` (its re-scoped "what to scaffold" item 1). Read both files' current text, and if this work actually closes what they describe as open, append an entry to `claude/session-log.md` following the format in `CLAUDE.md` exactly — including the literal bracket tags (`[Resolved — ...]` / `[Still accurate]` / `[New info — ...]`) on each assumption line. Don't paraphrase past the tag itself the way the last entry did.

7. Commit on a new branch off `main` (this is documentation/plumbing, not the six-item handoff work, so it deserves its own branch/PR per the same reasoning used for the steering-prompt convention itself). Open a PR, report the URL back.

8. Report back: what you found `spring_drift_check.py`'s actual interface to be (confirm or correct this prompt's description of it), the test pass count, and the PR URL.
