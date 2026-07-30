# INDEX — multi-axis router

Load [README.md](README.md) first. Prefer a **domain**, then one page. Cite its `id`. Check [deviations/](deviations/) when departing from Core claims.

## By level (start here if unsure)

| Level | Start |
|-------|--------|
| Product / direction | [README.md](README.md) + [meta/usage-levels.md](meta/usage-levels.md) |
| Domain | [domains/](domains/) (`01`…`10`) |
| Subdomain / concept | domain README → one `concepts/` page |
| Relationship | domain `relationships/` or playbook |
| Control / gate | [playbooks/](playbooks/) |
| Upstream diagnosis | [deviations/](deviations/) + `rel-conflict-vs-recompute` |

## Domains

| Domain | Open |
|--------|------|
| Data flow and truth | [domains/01-data-flow-and-truth/](domains/01-data-flow-and-truth/) |
| Encoding and evolution | [domains/02-encoding-and-evolution/](domains/02-encoding-and-evolution/) |
| Replication and conflicts | [domains/03-replication-and-conflicts/](domains/03-replication-and-conflicts/) |
| Integrity and verification | [domains/04-integrity-and-verification/](domains/04-integrity-and-verification/) |
| Maintainability and change | [domains/05-maintainability-and-change/](domains/05-maintainability-and-change/) |
| Consistency and coordination (partial) | [domains/06-consistency-and-coordination/](domains/06-consistency-and-coordination/) |
| Partitioning and skew | [domains/07-partitioning-and-skew/](domains/07-partitioning-and-skew/) |
| Transactions and concurrency (partial) | [domains/08-transactions-and-concurrency/](domains/08-transactions-and-concurrency/) |
| Derived data processing | [domains/09-derived-data-processing/](domains/09-derived-data-processing/) |
| Reliability / scalability goals (partial) | [domains/10-reliability-scalability-goals/](domains/10-reliability-scalability-goals/) |

## Build / implement

| If you are asking… | Open |
|--------------------|------|
| What is authoritative vs recomputable? | `sor-vs-derived` |
| Should this artifact be SoR or a view? | `choosing-sor-vs-view` + `rel-sor-feeds-views` |
| Positive vs negative vs recall coverage gates? | `coverage-gates` + `dev-fp-ratchet-separate-from-recall` |
| Multiple gates over one ruleset? | `materialized-views-and-caches` |
| Baseline / schema_version / additive fields? | `schema-evolution-and-data-outlives-code` + `rel-schema-outlives-writers` |
| Batch CI fixtures vs streaming freshness? | `batch-vs-stream-derived-state` + `rel-batch-feeds-serving` + domain `09` |
| Partition key / Stage-4 vs Stage-1 capacity? | `rel-partition-bounds-fanout` + `partition-key-and-hotspots` + `ch07` |
| Encoding / Pydantic / JSON Schema bite? | `encoding-and-compatibility` |
| How do we know a gate is not vacuous? | `trust-but-verify-and-auditability` + `rel-gate-needs-witness` |

## Review (code / architecture)

| Review concern | Open |
|----------------|------|
| SoR vs stale view in the diff | `sor-vs-derived` + `choosing-sor-vs-view` |
| LWW merge vs recompute | `replication-lag-and-lww` + `rel-conflict-vs-recompute` |
| Vacuous gate / missing witness | `trust-but-verify-and-auditability` + `coverage-gates` |
| STATUS/CONSTRAINTS/CI comment vs code | `claims-and-status-drift` |
| How to structure the review session | `architecture-decision-review` |
| Concurrent RMW / lost update language | `transactions-and-integrity-lite` (`partial`) |
| When derive-async is not enough | `consistency-and-consensus-lite` (`partial`) |
| Is this a silent DDIA deviation? | [deviations/](deviations/) |

## Refactor

| If you are asking… | Open |
|--------------------|------|
| Sequencing / blast radius / reversibility | `refactor-sequencing` |
| Operability / accidental complexity | `maintainability-operability-evolvability` |

## Chapters (5W1H)

| Need | Open |
|------|------|
| Who / what / when / where / why / how per chapter | [chapters/](chapters/) (`ch01`…`ch14`) |
| Epub package taxonomy | [meta/taxonomy.md](meta/taxonomy.md) |
| Completeness matrix | [COMPLETENESS.md](COMPLETENESS.md) |
| Machine index | [catalog.json](catalog.json) |

## Filed deviations

| id | Summary |
|----|---------|
| `dev-coverage-denominator-codeql` | Coverage SoR ≠ `rule_fixtures` / YAML count |
| `dev-certification-derived-view` | Certification is derived; no LWW with facts |
| `dev-fp-ratchet-separate-from-recall` | FP ratchet inverted & separate; no fake recall baseline |

## Tag → ids (quick)

- `sor`, `derived` → `sor-vs-derived`, `choosing-sor-vs-view`, `rel-sor-feeds-views`
- `ratchet`, `fixtures`, `semgrep` → `coverage-gates`, `dev-fp-ratchet-separate-from-recall`
- `lww`, `conflict` → `replication-lag-and-lww`, `rel-conflict-vs-recompute`
- `schema`, `baseline` → `schema-evolution-and-data-outlives-code`
- `audit`, `vacuous` → `trust-but-verify-and-auditability`, `rel-gate-needs-witness`
- `review`, `adr` → `architecture-decision-review`
- `partition`, `skew`, `fanout` → `partition-key-and-hotspots`, `rel-partition-bounds-fanout`, `ch07`
- `deviation` → [deviations/](deviations/)
- Prior art Took/Declined → [meta/prior-art.md](meta/prior-art.md)
