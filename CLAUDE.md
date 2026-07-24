# Working conventions for this repo

## Steering prompts and the session log

`claude/steering-prompts/` contains thirteen numbered prompts, plus a canonical copy that also lives in this project's attached Claude project ("Plugin For Asynchronous Documentation Creation"). They fall into three groups:

- **`00`–`05` — research/scaffold prompts.** `00` shared standards, then one per improvement category: testability, pluggability, constraints, analytics-logging, clarity/delivery-trust.
- **`06`–`09` — implementation task prompts.** Wire drift-check, CI scaffold, dependency pinning, tool-quirks indexing. These carry a `status:` frontmatter field that is edited in place as the task lands; the body is left as historical record rather than rewritten.
- **`10`–`12` — the review layer.** Review persona and evidence tiers, the DFS/BFS context-traversal protocol, and the paste-able review-session launcher. Read these when the session is a review or a design-weighing pass rather than a build.

Each prompt states specific factual assumptions about the current state of this repo (e.g., "no test exists for the LLM stages," "the confidentiality rule only lives in a handoff doc"). Commits to this repo can make those assumptions stale.

**Before your final commit in any session that touches `scripts/`, `agents/`, or `skills/`:** read the prompt files, and check whether anything you just changed resolves, contradicts, or otherwise affects a stated assumption in any of them. In practice `00`–`09` are the ones that carry repo-state assumptions; `10`–`12` describe method and rarely go stale from a code change.

- If nothing you changed is plausibly relevant to any of the prompts, don't write a log entry — churn here is worse than silence. Most commits (a typo fix, a small test addition) won't touch anything a steering prompt assumed.
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

## Tool and environment quirks

`claude/tool-quirks.md` is a separate, append-only index from `claude/session-log.md` above — it's about odd behavior in the *ambient tools/environment* this repo is worked in (`gh`, `git`, MCP tools, Windows/Git-Bash-specific quirks), not this plugin's own document-generation logic. See `skills/tool-quirks/SKILL.md` for the full convention. Check it before deep-diving into something that looks like a tool bug; append an entry whenever you diagnose one (resolved, partially diagnosed, or still open) so the next session doesn't redo the investigation.
