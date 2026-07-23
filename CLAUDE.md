# Working conventions for this repo

## Steering prompts and the session log

`claude/steering-prompts/` contains five research/scaffold prompts (`00` shared standards, `01`–`05` one per improvement category: testability, pluggability, constraints, analytics-logging, clarity/delivery-trust) plus a canonical copy that also lives in this project's attached Claude project ("Plugin For Asynchronous Documentation Creation"). Each prompt states specific factual assumptions about the current state of this repo (e.g., "`references/` sits as a plugin-root-level sibling of `skills/`," "no test exists for the LLM stages," "the confidentiality rule only lives in a handoff doc"). Commits to this repo can make those assumptions stale.

**Before your final commit in any session that touches `scripts/`, `agents/`, `skills/`, or `references/`:** read the five prompt files, and check whether anything you just changed resolves, contradicts, or otherwise affects a stated assumption in any of them.

- If nothing you changed is plausibly relevant to any of the five prompts, don't write a log entry — churn here is worse than silence. Most commits (a typo fix, a small test addition) won't touch anything a steering prompt assumed.
- If something is relevant, append one entry to `claude/session-log.md` (create it from the template below if it doesn't exist yet) in the same commit. Keep it distilled, not a raw diff — the point is that a downstream reviewer (human or another Claude session) can read ten lines instead of parsing a diff.

### Entry format

```
## <YYYY-MM-DD> — <short description of the commit>
Commit: <short sha, or "uncommitted" if writing before commit>
Tests: <pass/fail summary if you ran the relevant suite, e.g. "18/18 passing", or "not run">
Assumptions affected:
- `<prompt file>` — "<short quote or paraphrase of the specific assumption>" — [Resolved — <what changed, in this commit>] / [Still accurate] / [New info — <what changed and why the prompt may need editing>]
Files touched: <comma-separated list>
```

Reuse the bracket-tag convention already established elsewhere in this project (`Evidenced` / `Confirmed` / `Unknown` in the doc-writer output) rather than inventing new status words — `[Resolved — ...]`, `[Still accurate]`, and `[New info — ...]` are the three states that matter here; don't add more without a real reason to.

Only tag an assumption `[Resolved]` if you're confident the prompt's stated problem no longer exists after your change — not just that you touched the same file. If you're not sure whether an assumption is now stale, say so explicitly (`[New info — unsure if this is still accurate, needs a look]`) rather than guessing either direction.

### Why this exists, not just what to do

A Claude Code CLI session (this one) has full repo and git access but no access to the Claude project where the canonical steering prompts live. A Cowork session attached to that project has the reverse — it can read/edit the prompts but can't run git commands against this repo directly. `claude/session-log.md` is the one file that crosses that gap: cheap for this session to write (it already has full context of its own change), and small enough for the other session to read directly once it has folder access, without needing the full diff or `.git` history relayed by hand.
