---
id: coverage-gates
kind: playbook
completeness: operational
tags: [coverage, semgrep, ratchet, fixtures]
related: [materialized-views-and-caches, trust-but-verify-and-auditability, batch-vs-stream-derived-state]
last_refined: 2026-07-30
---

# Playbook: coverage gates (positive / negative / recall)

## Intent

Keep three measurements separate over one ruleset so CI stays hermetic and polarities cannot be confused.

## Decision procedure

1. **Positive non-vacuity** — every rule id fires ≥1 on committed positive fixtures (CI).
2. **Negative / FP** — hit counts on committed negative fixtures must not **rise** above FP baseline (CI).
3. **Recall backtest** — on a real corpus (dev): rule that used to fire must not drop to **zero** (baseline); do not invent client checkout names in git.
4. Never invert one helper for both (2) and (3).
5. Missing precision baseline after negatives exist → fail closed.

## Review procedure

1. Diff adds a rule? Require positive fixture trigger same commit.
2. Diff loosens a pattern? Check negative corpus / FP baseline.
3. Confirm CI invokes no-arg coverage (both 1+2 for semgrep after L1).
4. Cite `coverage-gates` + `trust-but-verify-and-auditability` in the review note.

## Do not

- Commit client dirname corpora.
- Overload recall baseline file for FP counts.
- Treat `rule_fixtures/` as `rule_coverage` SoR (it is metamorphic-owned).

## Worked example (this repo)

- Semgrep: `semgrep_rule_fixtures/` + `semgrep_rule_fixtures_negative/` + `semgrep_rule_fp_baseline.json`.
- Stage-0 vocabulary coverage: `rule_coverage.py` + `scripts/fixtures/spring_signals/` (CodeQL denominator).

## See also

- `materialized-views-and-caches`, `claims-and-status-drift`
