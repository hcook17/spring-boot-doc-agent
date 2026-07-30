---
id: dev-coverage-denominator-codeql
kind: deviation
completeness: operational
tags: [deviation, coverage, codeql, sor]
related: [coverage-gates, sor-vs-derived, claims-and-status-drift, schema-evolution-and-data-outlives-code]
last_refined: 2026-07-30
path: deviations/dev-coverage-denominator-codeql.md

---

# Deviation: coverage denominator is CodeQL + spring_signals, not ast-grep YAML / rule_fixtures

## DDIA claim id(s)

- `sor-vs-derived` — SoR for “which rules must fire” must be one writer; derived docs must not invent a second denominator.
- `coverage-gates` — non-vacuity proves rules can fire; corpus must match the gate’s actual scan path.
- Textbook-shaped expectation some docs once implied: “ast-grep YAML rule count + `rule_fixtures/` = coverage SoR.”

## Local approach

`scripts/coverage/rule_coverage.py` enumerates **CodeQL pack `rule_id`s** and scans **`scripts/fixtures/spring_signals/`** via `spring_signal_scan`. `scripts/coverage/rule_fixtures/` remains the **metamorphic** corpus (`tests/ratchets/test_metamorphic.py`), not the coverage denominator. Semgrep has its own positive/negative fixture trees and FP ratchet under `scripts/coverage/`.

## Why correct here

- Runtime of `rule_coverage.py` is the SoR for what “coverage” means in CI; CLAUDE/CONSTRAINTS prose that still pointed at `rule_fixtures/` + YAML count were **stale derived views** (see `claude/research/coverage-sor-derived-blindspot-2026-07-30.md`).
- Metamorphic tests need a separate fixture tree with intentional mutations — merging that with coverage non-vacuity would couple two jobs and invite dual writers.
- Measured: docs claimed fixtures path that the gate did not read — classic SoR/view drift, fixed by aligning docs to code (not by inventing a second gate over the wrong corpus).

## Upstream check
- Fail if a dual writer, silent LWW, or vacuous gate ships without a deviation or SoR fix.

- Writers inspected: `rule_coverage.py`, `spring_signal_scan`, CodeQL pack rule ids, metamorphic tests, CLAUDE.md / CONSTRAINTS item 10, tool-quirks.
- SoR vs derived: **code + CI invocation** = SoR for coverage denominator; markdown counts = derived.
- Dual-writer ruled out by **not** inventing a parallel “ast-grep YAML coverage” gate and by correcting prose instead of LWW-merging “29 rules” with CodeQL ids.
- Upstream defect was **docs/runtime mismatch**, not “rules cannot fire”; fixed at the claim layer + blindspot memo, not by papering CI.

## Rejected band-aids

- Keep claiming `rule_fixtures/` in CLAUDE while scanning `spring_signals` — rejected (silent dual narrative).
- Force metamorphic fixtures to also satisfy coverage non-vacuity — rejected (wrong job; would hide metamorphic intent).
- Invent a client-named semgrep **recall** baseline without measurement — rejected (`dev-fp-ratchet-separate-from-recall`).

## Expiry / revisit

`standing` — owner: coverage / Stage-0 maintainers. Revisit if CodeQL ceases to be the Stage-0 signal pack SoR.

## See also

- `coverage-gates`, `sor-vs-derived`
- `claude/research/coverage-sor-derived-blindspot-2026-07-30.md`
- CONSTRAINTS item 10; CLAUDE.md coverage invariant wording
