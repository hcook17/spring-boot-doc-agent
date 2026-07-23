---
pr: 7
title: Add CONTRIBUTING.md (write-then-verify rule) and STATUS.md
state: MERGED
branch: clarity-delivery-trust-scaffold -> main
merge_commit: bfcb324e50a167ed1262741c5c1698da9b4e6b92
---

# PR #7 — Add CONTRIBUTING.md (write-then-verify rule) and STATUS.md

## Summary

Resolves `claude/steering-prompts/05-clarity-delivery-trust-research-prompt.md`'s scaffold items 1 and 2: `CONTRIBUTING.md` states a write-then-verify rule (re-read any file after a device-bridge/remote-tool write; re-verify any prior session's/doc's claim about repo state directly), citing this repo's two prior trust-without-verify incidents as motivation and a `PostToolUse`-on-`Write|Edit` hook as a documented-but-unwired automation path. `STATUS.md` is a single in-place-edited current-state snapshot, cross-linked with `claude/session-log.md`, `CONSTRAINTS.md`, and `IMPLEMENTATION_HANDOFF.md`. Research found no on-point GitHub "write-then-verify" utility — a valid null result, per this project's own research standard — so item 3 was codified as a checklist rule rather than wiring in external tooling.

## Deterministic verification

Pinned to `bfcb324`:

1. **Claim: `CONTRIBUTING.md` states the write-then-verify rule and cites both prior incidents.**
   `git show bfcb324:CONTRIBUTING.md | grep -n "write-then-verify\|device-file-bridge\|Stray scaffolding"`
   Expect: matches for the rule heading and both incident references.

2. **Claim: `STATUS.md` is cross-linked with `claude/session-log.md`, `CONSTRAINTS.md`, and `IMPLEMENTATION_HANDOFF.md`.**
   `git show bfcb324:STATUS.md | grep -n "session-log.md\|CONSTRAINTS.md\|IMPLEMENTATION_HANDOFF.md"`
   Expect: at least one match for each of the three.

3. **Claim: the Claude Code docs research found no documented write-tool reliability guarantee, and named `PostToolUse` + `Write|Edit` as the supported automation mechanism.**
   `git show bfcb324:CONTRIBUTING.md | grep -n "PostToolUse"`
   Expect: one match, in a paragraph explicitly noting no such hook is wired into this repo as of that commit.

4. **Claim: the GitHub write-then-verify research is documented as a null result, not silently dropped.**
   `git show bfcb324:CONTRIBUTING.md | grep -n "teran/checksum\|nicjansma/checksum-verifier"`
   Expect: both named as the closest-but-not-on-point matches found.

5. **Claim: `05-clarity-delivery-trust-research-prompt.md`'s status frontmatter reflects resolution.**
   `git show bfcb324:claude/steering-prompts/05-clarity-delivery-trust-research-prompt.md | grep -n "^status:"`
   Expect: `status:` no longer reads "not started."
