# Coverage SoR vs derived-view blindspot — 2026-07-30

**Verdict: REFINE** (docs/claims lagged runtime; fix in place + L1 precision gate)

Aligns with: [`docs/design/ddia-north-star/`](../../docs/design/ddia-north-star/) ids `sor-vs-derived`, `claims-and-status-drift`, `coverage-gates`, `schema-evolution-and-data-outlives-code`, deviation `dev-coverage-denominator-codeql`; adoption-blockers queue; B2.5 certification derived-view memo.

## 1. What drifted

| Claimed (derived view) | Runtime SoR |
|------------------------|-------------|
| `rule_coverage` reads `scripts/coverage/rule_fixtures/` | Reads `scripts/fixtures/spring_signals/` via `spring_signal_scan`; denominator = CodeQL `rule_id`s |
| `ast_grep_rule_count` (29) is what coverage enumerates | 29 = YAML scanner inventory; coverage denominator differs |
| STATUS “Next engineering” = B1–B4 themes | B1–B5 done on main (PRs #68–#72) |
| Semgrep CI = non-vacuity only; comment path `scripts/semgrep_rule_fixtures/` | Path is under `scripts/coverage/`; FP unmeasured until L1 |

`path_exists:scripts/coverage/rule_fixtures` stayed green because the directory still exists for **metamorphic** tests — mechanical verify ≠ semantic truth (`claims-and-status-drift`).

## 2. Upstream / downstream

- **Upstream:** CLAUDE.md, CONSTRAINTS item 10, tool-quirks, CI comments, STATUS.
- **Downstream:** agents adding fixtures to the wrong tree; humans reopening finished blockers; precision never gated for semgrep.

## 3. What this change does

1. DDIA north-star catalog for durable lookup (`docs/design/ddia-north-star/`).
2. Correct CLAUDE / CONSTRAINTS / tool-quirks / STATUS / CI comments; keep `rule_fixtures` as metamorphic-owned.
3. L1: `semgrep_rule_fixtures_negative/` + `check_fp_ratchet` + `semgrep_rule_fp_baseline.json` (hermetic; all-zero preferred).

## 4. Explicitly deferred (L6+) — discharged 2026-08-04 except standing ban

- ~~Regenerate `rule_coverage_baseline.json` to schema_version 2.~~ **Done** (L6).
- ~~Optional `codeql_rule_count` derivation key.~~ **Done** (L6).
- Do not invent semgrep **recall** baseline from a client checkout. **Standing ban** (unchanged).

## 5. Confirm / Refine / Pivot

| Claim | Tag |
|-------|-----|
| Coverage docs described wrong corpus | **Confirmed** |
| Fix is SoR/view hygiene + separate FP polarity | **Confirmed** (`coverage-gates`) |
| Big-bang rewrite of rule_coverage to ast-grep-only | **Refuted** |
| North-star replaces reading the epub for every decision | **Refuted** — catalog is paraphrase lookup; epub remains Tier A |

**Overall: REFINE.**
