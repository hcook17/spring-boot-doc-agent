---
id: schema-evolution-and-data-outlives-code
kind: concept
completeness: operational
tags: [schema, evolution, compatibility, baseline]
epub_anchors:
  - { chapter: 5, title: "Schema evolution rules" }
  - { chapter: 5, title: "Different values written at different times" }
related: [encoding-and-compatibility, claims-and-status-drift]
last_refined: 2026-07-30
path: domains/02-encoding-and-evolution/concepts/schema-evolution-and-data-outlives-code.md

---

# Schema evolution and data outlives code

## In one sentence

Deployed code turns over quickly; stored data and baselines persist in old shapes — evolution must stay backward/forward compatible or explicitly migrate.

## When to open

- Bumping `schema_version` on baselines or artifacts.
- Additive fields vs breaking renames.
- STATUS/CONSTRAINTS still describing a retired layout.

## Core claims

- Data outlives code: five-year-old rows remain until rewritten.
- Compatibility (Avro-style rule of thumb): add/remove only fields with defaults if readers/writers skew.
- Writer schema and reader schema can differ; plan for both directions.
- Silent schema mismatch fails at the worst time (first real backtest), not in unused paths.

## Tradeoffs

- Premature schema_version bumps train hollow version theater (see B2.5 cert policy).
- Never bumping → ambiguous meaning across commits.
- Inventing baselines to “have a file” → false precision.

## Repo analogues

- `rule_coverage_baseline.json` schema_version 1 vs code expecting 2 (backtest silent in CI).
- `CertificationReport.schema_version` stays 1 for additive `StageRecord.executor`.
- FP baseline (`semgrep_rule_fp_baseline.json`) is a new hermetic view — do not overload absent recall baseline.

## Review checks

- Fail if schema_version is bumped without stating which readers still must accept the prior version.
- Fail if a dual writer, silent LWW, or vacuous gate ships without a deviation or SoR fix.

1. Is the change additive-with-default or breaking?
2. Does CI exercise the schema path that would catch mismatch?
3. Are docs updated in the same change as the SoR move?
- Fail if the Core claims are ignored without a filed deviation.
## Refactor signals

- Code `SCHEMA_VERSION` != committed baseline without a queued `--update`.
- Prose still naming deleted paths while `verify:` still passes on a repurposed directory.

## Anti-patterns seen

- Coverage docs/`verify:` still pointing at `rule_fixtures` after SoR moved to `spring_signals`.

## See also

- `encoding-and-compatibility`, `claims-and-status-drift`
