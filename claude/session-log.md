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
