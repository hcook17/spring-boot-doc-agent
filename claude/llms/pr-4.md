---
pr: 4
title: Add CONSTRAINTS.md
state: MERGED
branch: add-constraints-md -> main
merge_commit: 775132280f056bd3cccd514a38e46195e8b1c0ad
---

# PR #4 — Add CONSTRAINTS.md

## Summary

Adds `CONSTRAINTS.md` at the plugin root per `claude/steering-prompts/03-constraints-research-prompt.md`'s scaffold spec: one entry per real constraint, tagged by kind (Runtime prerequisite, Integration gap, Known precision tradeoff, Confidentiality/handling rule), plus a fifth category — Enterprise-readiness gap — added to hold findings (UNLICENSED license, no CI/CD, no RBAC, no audit trail, unpinned deps, an unmitigated secret-redaction gap) that didn't fit the original four cleanly. Cross-linked from `README.md` and `SKILL.md`.

## Deterministic verification

Pinned to `7751322`:

1. **Claim: `CONSTRAINTS.md` has exactly five top-level categories, the four specified plus one added.**
   `git show 7751322:CONSTRAINTS.md | grep -n "^## "`
   Expect: `Runtime prerequisites`, `Integration gaps, not scope cuts`, `Known precision tradeoffs`, `Confidentiality/handling rules`, `Enterprise-readiness gaps` — 5 headings.

2. **Claim: cross-linked from `README.md` and `SKILL.md`.**
   `git show 7751322:README.md | grep -n "CONSTRAINTS.md"`
   `git show 7751322:skills/document-spring-repo/SKILL.md | grep -n "CONSTRAINTS.md"`
   Expect: at least one match in each.

3. **Claim: names the specific unpinned dependencies (ast-grep, sqllineage, pathspec).**
   `git show 7751322:CONSTRAINTS.md | grep -n "ast-grep\|sqllineage\|pathspec"`
   Expect: all three named under "Runtime prerequisites."

4. **Claim: documents an open, unmitigated secret-redaction gap in `file-summarizer`.**
   `git show 7751322:CONSTRAINTS.md | grep -n "Secret/credential leakage"`
   Expect: one match, under "Confidentiality/handling rules," explicitly marked open/unmitigated in the surrounding text.

5. **Claim: documentation-only change, no test suite affected.**
   `git show --stat 7751322^1..7751322 -- scripts/`
   Expect: empty output (no files under `scripts/` touched).
