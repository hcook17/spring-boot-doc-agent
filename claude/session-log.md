# Session log — steering prompt impact

Append-only. One entry per commit that plausibly affects an assumption stated in `claude/steering-prompts/01`–`05`. See `CLAUDE.md`'s "Steering prompts and the session log" section for the format and when to write an entry (most commits won't need one — don't force it).

Newest entries at the bottom.

---

## 2026-07-23 — Stray scaffolding commit landed on the wrong branch, caught by a later session
Commit: uncommitted (this entry documents an incident, not a code change)
Tests: not applicable — process/doc incident, no code touched
Assumptions affected:
- `claude/steering-prompts/00-shared-research-standards.md` — "a local Claude Code CLI session... has no access to [the Claude] project" while "a Cowork session attached to that project... can't run git commands against this repo directly" — [Still accurate — this exact gap is what caused the incident below, not something the incident changed.]
Details: A memoryless Cowork session wrote CLAUDE.md and `claude/` (this convention itself) as untracked working-tree files, intentionally left out of PR #1 per handoff instructions. A separate, also-memoryless Claude Code CLI session later committed those files directly onto `implement-handoff-items` (commit `8bb2404`) without checking whether they were supposed to stay untracked, and that commit rode along when PR #1 merged to `main`. The next session caught it only by running `git status` and `gh pr view 1` directly rather than trusting the task description's assumption that the files were still untracked. Outcome: left as-is on `main` (functionally correct — the convention is live — just via the wrong branch/PR, a cosmetic history detail not worth rewriting merged history to fix).
Files touched: claude/session-log.md

---

## 2026-07-23 — Wire spring_drift_check.py into SKILL.md and README.md
Commit: e614e7c (also f969521 on the same branch)
Tests: 12/12 passing (`python3 scripts/test_spring_drift_check.py -v`) — an initial run surfaced a real Windows path-separator bug in `spring_drift_check.py`'s `tier1_scan()` (raw `os.path.relpath()` instead of normalizing to forward slashes like `spring_signal_scan.py` does everywhere else), fixed in this same PR along with a stale test assertion that predated the `references` bucket being cited as per-file evidence
Assumptions affected:
- `claude/steering-prompts/03-constraints-research-prompt.md` — "Integration gap, not a scope cut" item: `spring_drift_check.py` exists and works standalone but isn't wired into `SKILL.md`'s pipeline or documented in `README.md` — [Resolved — SKILL.md's Stage 0 now documents it as an optional pre-flight check, and README.md now has an "On drift detection" section; still standalone/not CI-triggered by design, which both files now say explicitly.]
- `claude/steering-prompts/04-analytics-logging-research-prompt.md` — re-scoped "what to scaffold" item 1, "add a SKILL.md-documented way to run spring_drift_check.py... and document it in README.md" — [Resolved — same SKILL.md/README.md additions as above; the run-manifest half of that prompt (item 2) remains open, out of scope for this commit.]
Files touched: skills/document-spring-repo/SKILL.md, README.md, claude/session-log.md
