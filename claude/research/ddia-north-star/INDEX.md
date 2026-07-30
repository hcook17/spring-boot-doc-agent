# INDEX — question / tag / review router

Load [README.md](README.md) first. Open **one** target page. Cite its `id`.

## Build / implement

| If you are asking… | Open |
|--------------------|------|
| What is authoritative vs recomputable? | [concepts/system-of-record-vs-derived.md](concepts/system-of-record-vs-derived.md) (`sor-vs-derived`) |
| Should this artifact be SoR or a view? | [playbooks/choosing-sor-vs-view.md](playbooks/choosing-sor-vs-view.md) |
| Positive vs negative vs recall coverage gates? | [playbooks/coverage-gates.md](playbooks/coverage-gates.md) |
| Multiple gates over one ruleset? | [concepts/materialized-views-and-caches.md](concepts/materialized-views-and-caches.md) |
| Baseline / schema_version / additive fields? | [concepts/schema-evolution-and-data-outlives-code.md](concepts/schema-evolution-and-data-outlives-code.md) |
| Batch CI fixtures vs streaming freshness? | [concepts/batch-vs-stream-derived-state.md](concepts/batch-vs-stream-derived-state.md) |
| Encoding / Pydantic / JSON Schema bite? | [concepts/encoding-and-compatibility.md](concepts/encoding-and-compatibility.md) |
| How do we know a gate is not vacuous? | [concepts/trust-but-verify-and-auditability.md](concepts/trust-but-verify-and-auditability.md) |

## Review (code / architecture)

| Review concern | Open |
|----------------|------|
| SoR vs stale view in the diff | `sor-vs-derived` + `choosing-sor-vs-view` |
| LWW merge vs recompute | [concepts/replication-lag-and-lww.md](concepts/replication-lag-and-lww.md) |
| Vacuous gate / missing witness | `trust-but-verify-and-auditability` + `coverage-gates` |
| STATUS/CONSTRAINTS/CI comment vs code | [playbooks/claims-and-status-drift.md](playbooks/claims-and-status-drift.md) |
| How to structure the review session | [playbooks/architecture-decision-review.md](playbooks/architecture-decision-review.md) |
| Concurrent RMW / lost update language | [concepts/transactions-and-integrity-lite.md](concepts/transactions-and-integrity-lite.md) (`partial`) |
| When derive-async is not enough | [concepts/consistency-and-consensus-lite.md](concepts/consistency-and-consensus-lite.md) (`partial`) |

## Refactor

| If you are asking… | Open |
|--------------------|------|
| Sequencing / blast radius / reversibility | [playbooks/refactor-sequencing.md](playbooks/refactor-sequencing.md) |
| Operability / accidental complexity | [concepts/maintainability-operability-evolvability.md](concepts/maintainability-operability-evolvability.md) |

## Structure / completeness

| Need | Open |
|------|------|
| Epub package / sect / leaf taxonomy | [taxonomy.md](taxonomy.md) |
| What is operational vs outline | [COMPLETENESS.md](COMPLETENESS.md) |
| Chapter atlas | [chapters/](chapters/) (`ch01`…`ch14`) |
| Machine index | [catalog.json](catalog.json) |

## Tag → ids (quick)

- `sor`, `derived` → `sor-vs-derived`, `choosing-sor-vs-view`
- `ratchet`, `fixtures`, `semgrep` → `coverage-gates`
- `lww`, `conflict` → `replication-lag-and-lww`
- `schema`, `baseline` → `schema-evolution-and-data-outlives-code`
- `audit`, `vacuous` → `trust-but-verify-and-auditability`
- `review`, `adr` → `architecture-decision-review`
