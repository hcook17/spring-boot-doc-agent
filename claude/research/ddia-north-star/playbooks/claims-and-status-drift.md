---
id: claims-and-status-drift
kind: playbook
completeness: operational
tags: [claims, status, drift, verify]
related: [sor-vs-derived, schema-evolution-and-data-outlives-code, maintainability-operability-evolvability]
last_refined: 2026-07-30
---

# Playbook: claims and STATUS drift

## Intent

Keep current-state docs as honest derived views of code SoR; mechanical `verify:` is necessary but not sufficient.

## Decision procedure

1. Identify SoR paths the claim names.
2. Read the runtime (script constants, CI steps) — not only the prose.
3. If prose ≠ runtime: fix prose/`verify:` in the same change as awareness (or queue explicitly).
4. Update STATUS “Next engineering” when the queue SoR moves.
5. Prefer derivations for counts; do not hand-stamp numbers that `DERIVATIONS` already own.

## Review procedure

1. For each touched claim in CLAUDE/CONSTRAINTS/STATUS/CI comments: does the path still exist **and** still mean what the sentence says?
2. `path_exists` alone is not truth — ask whether the gate reads that path.
3. Cite `claims-and-status-drift` + `sor-vs-derived`.

## Do not

- Rewrite historical `claude/llms/pr-*.md` to modern paths.
- Delete `rule_fixtures/` because coverage moved — metamorphic still owns it.
- Leave STATUS advertising finished blockers as “next”.

## Worked example (this repo)

- Coverage blindspot: docs said `rule_fixtures`; gate reads `spring_signals` + CodeQL ids.
- Adoption queue B1–B5 done while STATUS still listed them as next.

## See also

- `choosing-sor-vs-view`, `claude/research/coverage-sor-derived-blindspot-2026-07-30.md`
