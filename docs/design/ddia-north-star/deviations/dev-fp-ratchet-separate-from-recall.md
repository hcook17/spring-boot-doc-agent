---
id: dev-fp-ratchet-separate-from-recall
kind: deviation
completeness: operational
tags: [deviation, semgrep, ratchet, fp]
related: [coverage-gates, trust-but-verify-and-auditability, schema-evolution-and-data-outlives-code]
last_refined: 2026-07-30
path: deviations/dev-fp-ratchet-separate-from-recall.md

---

# Deviation: FP ratchet is separate and inverted from recall — no invented recall baseline

## DDIA claim id(s)

- `coverage-gates` — positive non-vacuity ≠ negative FP control ≠ recall ratchet; each needs its own witness.
- `trust-but-verify-and-auditability` — a gate without the right corpus is vacuous.
- Tempting textbook collapse: one “coverage number” that mixes hit rate, false positives, and recall.

## Local approach

Semgrep:

- **Positive / non-vacuity** — rules must fire on committed positive fixtures.
- **FP ratchet** — `check_fp_ratchet` against `semgrep_rule_fixtures_negative/` + `semgrep_rule_fp_baseline.json`; fails if FP **count rises** (`--update-fp-baseline` only when intentional).
- **Recall ratchet API** may exist, but this repo does **not** invent or commit a client-named recall baseline without measured evidence.

## Why correct here

- FP and recall move in opposite “bad” directions; one shared baseline would be a schema lie (`schema-evolution-and-data-outlives-code`).
- Negative fixtures were chosen so measured FP is all-zero after fixing FQN `assertThrows` shapes — hermetic, reviewable.
- Inventing a recall baseline to “complete the story” would create a derived artifact with no SoR measurement (band-aid).

## Upstream check

- Writers inspected: `semgrep_rule_coverage.py`, positive fixtures, new negative fixtures, CI no-arg path, adoption queue L1.
- SoR for FP = negative corpus + committed FP baseline; SoR for non-vacuity = positive fixtures; recall baseline **absent until measured**.
- Dual-writer ruled out: docs must not claim a recall baseline exists; FP update is an explicit flag, not silent CI rewrite.
- Upstream gap was **missing FP control**, not “recall looked bad” — fixed by adding the missing gate, not by loosening positives.

## Rejected band-aids

- Single ratchet JSON with both “must not drop” and “must not rise” without separate semantics — rejected (confusing failure mode).
- Commit an empty/fake recall baseline for symmetry — rejected (vacuous SoR).
- Disable FP gate when negatives are hard — rejected (returns to blind spot).

## Expiry / revisit

`standing` for FP separation. Recall baseline: revisit when a **measured** client corpus is ratified (adoption L6 hygiene may touch schemas; does not invent numbers).

## See also

- `coverage-gates`, playbook worked example
- `scripts/coverage/semgrep_rule_coverage.py`, `semgrep_rule_fp_baseline.json`
- adoption-blockers queue L1
