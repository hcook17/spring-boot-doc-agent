# Contributing

## Write-then-verify: never trust a write tool's success response alone

**Rule:** after any file write made through a device bridge, remote tool, or subagent whose only view of the filesystem is a bridged connection, the very next action is re-reading that file's actual content directly. A "written" response, a byte count, or a reported mtime is not evidence the live file changed — only a direct re-read is.

**Why this rule exists, not just what it says:** this repo has two confirmed, independent incidents of the same failure shape — trusting a tool's or document's account of state instead of re-verifying it directly:

1. A cloud sandbox session driving this repo through a device-file-bridge tool had that bridge repeatedly report a file as "written" when the live copy on disk hadn't actually changed. Caught only by re-reading the file's actual bytes after a "success" response, and re-discovered more than once because each new session initially trusted the tool's own response instead of checking. See `IMPLEMENTATION_HANDOFF.md`'s opening section for the full account.
2. A later, unrelated incident: a memoryless session trusted a handoff document's stale claim about repo state (that certain files were still untracked) rather than checking actual repo state (`git status`, `gh pr view`) directly, and committed files onto the wrong branch as a result. Logged in `claude/session-log.md` (2026-07-23, "Stray scaffolding commit landed on the wrong branch").

Same root cause both times — trusting a tool's or a document's *report* of state instead of the state itself — different surface (file content vs. git/PR state). The rule below is written broadly enough to cover both.

**How to apply it:**

- Local filesystem calls made directly by a Claude Code CLI session against a repo checked out on that same machine (the normal case for this repo) are not the failure mode described above — there is no bridge in that path. The rule exists for the cases that *do* have an intermediary: a device bridge, a remote/cloud sandbox tool, or any handoff where one session's account of "this is done" is the only thing a later session has to go on.
- Before treating any prior session's, document's, or tool's claim about current repo state as fact — "this file was already fixed," "these files are untracked," "this test suite passes" — re-check it directly (`git status`, a direct file read, an actual test run) rather than building further work on top of an unverified claim. `IMPLEMENTATION_HANDOFF.md`'s own "Step 0 — Reconcile against the known-good baseline" is a worked example of this: it does not assume its own bundled baseline files are already live in the repo, it says to diff and confirm first.
- If you are automating verification (rather than doing it by hand) inside this repo's own Claude Code plugin tooling, the supported mechanism is a `PostToolUse` hook matched against `Write|Edit` (see `code.claude.com/docs/en/hooks` and `plugins-reference`'s hook-matcher documentation) — Claude Code's own docs don't document any built-in guarantee that a write tool's reported success reflects the live file, so a hook is the place to add that guarantee yourself if you need it enforced automatically rather than as a manual checklist step. No such hook exists in this repo as of this writing; this paragraph documents the mechanism, not a claim that it's wired in.

Research note (per `claude/steering-prompts/05-clarity-delivery-trust-research-prompt.md`): a GitHub search for small, well-maintained "write-then-verify" or checksum-confirm utilities turned up nothing genuinely on-point — the closest matches (`teran/checksum`, `nicjansma/checksum-verifier`, and similar) solve a different problem (verifying a *downloaded* file's integrity against a known-good checksum), not "did my own write tool's success response reflect what's actually on disk." Per the shared research standard, finding nothing better than "read the file back after writing it" is itself a valid result — that's the rule stated above, codified as an explicit checklist step rather than left as tribal knowledge.

## Current status and steering prompts

See `STATUS.md` for a current-state snapshot of this plugin (what's done, what's pending, next concrete action) and `claude/session-log.md` for the append-only history of commits that affect the assumptions in `claude/steering-prompts/`. `CLAUDE.md` explains when a commit needs a session-log entry.
