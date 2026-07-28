---
name: tool-quirks
description: Look up and log operational quirks in the tools/environment used to work on this repo — a CLI or MCP tool silently defaulting to unexpected behavior, reporting success while the real state differs, an undocumented fallback, a Windows/Git-Bash-specific path or subprocess quirk, or any other oddity that cost real diagnostic time. Check claude/tool-quirks.md FIRST whenever you hit behavior that looks like a tool bug or environment quirk, before re-diagnosing something a prior session already root-caused. Log a new entry whenever you diagnose one (resolved, partially diagnosed, or still unresolved) so the next session doesn't redo the work. Distinct from claude/session-log.md (steering-prompt impact) and claude/llms/ (this repo's own PR-verification commands) — this index is about the ambient tools/environment themselves, not this plugin's own document-generation logic.
---

# Tool quirks and diagnostic playbooks

## Why this exists

This project already has two mechanisms for not re-deriving things from scratch: `claude/llms/pr-*.md` (re-runnable verification commands for this repo's own PR history) and `claude/session-log.md` (steering-prompt impact history). Neither covers a third real category: odd behavior in the *ambient tools* used to work on this repo at all — `gh`, `git`, MCP tools, the shell, Windows-specific path handling — that has nothing to do with this plugin's own document-generation logic, but still costs real diagnostic time every time it recurs and nobody wrote down what was found last time.

Concrete motivating case: `gh pr create --title ... --body ...` was run and returned "a pull request already exists," pointing at a PR whose stored title was truncated with an ellipsis and whose body was just the raw commit message — not the `--title`/`--body` content passed. A follow-up investigation (checked local and global git hooks, repo webhooks, installed GitHub Apps, `gh` CLI version, and the prior five merged PRs in this repo for the same pattern) found no configured automation that explains it, and no evidence it's a recurring problem in this environment specifically. That investigation — what was checked, what came back clean, and what remains genuinely unresolved — is exactly the kind of thing worth writing down once rather than re-running blind the next time something similar happens.

## Before deep-diving into an odd tool behavior

1. Search `claude/tool-quirks.md` for an entry matching the symptom or the tool/command involved.
2. If one matches, apply its documented workaround/resolution directly — don't re-diagnose from scratch. If the entry is tagged `[Unresolved — needs research]`, treat that as a real signal this may need deeper investigation (or a human's attention) rather than something to route around silently.
3. If nothing matches, investigate as you normally would, but keep the actual commands you run — they become the next entry's re-runnable diagnostic playbook, the same "keep it re-runnable, not just narrated" discipline `claude/llms/pr-*.md` already uses for PR-history verification.

## When to log a new entry

- A tool/command reported success while the real state differed — the general class of bug `CONTRIBUTING.md`'s write-then-verify rule already exists for; this file is where the *specific instances* of that pattern get recorded so they're searchable later.
- A tool silently fell back to different behavior than what was requested (a flag seemingly ignored, an unexpected default substituted) with no error surfaced.
- An environment-specific quirk (Windows path handling, Git Bash vs. native git subprocess behavior, a non-TTY CLI default, an MCP tool's undocumented edge case) that isn't obvious from the tool's own documentation.
- A useful diagnostic checklist worth keeping even when the underlying root cause stayed unresolved — e.g. "check local + global git hooks, repo webhooks, installed GitHub Apps, and `gh` CLI version" as a reusable first-pass playbook for "did something auto-create this."

**Don't log**: routine bugs in this project's own code (those belong in a commit message and, if relevant, `claude/session-log.md`) or one-off user preference (that's a `CLAUDE.md` concern, not this file's). This index is specifically about the ambient tools and environment this project happens to be worked in, not this plugin's own logic.

## Entry format

```
## <YYYY-MM-DD> — <short description>
Tools/commands involved: <e.g. gh CLI 2.96.0, git push, non-TTY Git Bash>
Status: [Resolved — <workaround>] / [Diagnosed — root cause found] / [Unresolved — needs research]
Symptom: <what happened, concretely>
Diagnostic steps taken (re-runnable):
    <the actual commands run, verbatim, so a future session can re-run them instead of re-deriving from scratch>
Resolution / workaround: <what fixed it, or what's still open and worth a deeper look>
```

Same three status words as this project's other logs use elsewhere (`[Resolved]`/`[Unresolved]`, mirroring `doc-taxonomy.md`'s `[Evidenced]`/`[Confirmed]`/`[Unknown]` tagging discipline) — don't invent new ones without a real reason.
