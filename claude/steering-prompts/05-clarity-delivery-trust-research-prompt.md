---
category: Clarity / trust in delivery and handoff state
status: mostly resolved (2026-07-23) — CONTRIBUTING.md (write-then-verify rule) and STATUS.md (single living status doc) added; item 3's "helper" scaffolded as a documented checklist rule, not automated tooling — see STATUS.md's "Pending" section for the PostToolUse-hook follow-up if automation is wanted later
verify:
  - path_exists:CONTRIBUTING.md
  - path_exists:STATUS.md
---

# Research + scaffold prompt: write-then-verify discipline and a single living status doc

Read `claude/steering-prompts/00-shared-research-standards.md` in this repo first for the research bar and methodology every finding here must meet.

## The gap

This one is about how work on the plugin gets tracked and trusted across sessions, not the plugin's code. Past sessions using a device-bridge tool to push file changes to this repo repeatedly hit a failure mode: the write tool reported success while the actual file content on the target machine stayed unchanged — caught only via direct content re-reads, and re-discovered multiple times because each new session initially trusted the tool's own response. Separately, the project's own audit trail of what's fixed vs. pending is spread across many append-only prose documents, so a new session has to read a long history serially to reconstruct current state.

## Research

Check whether Claude Code's own docs (`code.claude.com/docs/en/sub-agents`, `code.claude.com/docs/en/plugins-reference`) say anything about tool-response reliability for file-write tools — cite directly if so, rather than treating this as a discovery unique to this project.

Search GitHub for small, well-maintained "write-then-verify"/checksum-confirm utility patterns (apply the star/push/DeepWiki methodology) — finding nothing better than "read the file back after writing it" is itself a valid, useful result.

Also check GitHub conventions for a `STATUS.md`/`PROGRESS.md` pattern edited in place, vs. an append-only changelog — note which fits a project with this session-handoff pattern better (the answer may be "keep both": one current-state snapshot, one append-only history, cross-linked).

## What to scaffold and implement

1. A documented rule (in this repo's own conventions, e.g. a `CONTRIBUTING.md` or this file's own follow-up): after any file write through a device bridge or remote tool, the very next action is re-reading that file's actual content directly — never trust a "written" response, byte count, or mtime alone.
2. A single `STATUS.md`, in-place-edited, stating current state: what's done vs. pending, what's confirmed delivered, what the next concrete action is — distinct from any append-only history doc, which should keep existing as the audit trail. Cross-link the two.
3. If research turns up a genuinely useful small write-verification helper, wire it in; otherwise codify "read-after-write" as an explicit checklist step rather than leaving it as tribal knowledge.
