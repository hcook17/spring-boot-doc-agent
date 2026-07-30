# Facts ledger schema (Phase 1 dual-emit)

Companion to [`fact-store-phase1-decision-memo-2026-07-30.md`](fact-store-phase1-decision-memo-2026-07-30.md) §3.
Closed-contract formalization: [`schema-contracts-decision-memo-2026-07-30.md`](schema-contracts-decision-memo-2026-07-30.md) slice 1.

**Artifact:** `facts.jsonl` — UTF-8 JSON Lines, one fact object per line, written beside `spring_signals.json` by `python -m doc_engine.tools.spring_signal_scan`.

**Contract:** Pydantic `Fact` / `FactsArtifact` (`extra=forbid`) in `doc_engine.pipeline.artifacts`; JSON Schema export [`scripts/schemas/facts.schema.json`](../../scripts/schemas/facts.schema.json); validate via `python -m doc_engine.tools.validate_artifacts facts <path>` or `--all <dir>`. Ledger version constant `FACTS_LEDGER_SCHEMA_VERSION = 2` (export annotation `x-doc-engine-schema-version`; not a per-line wire field). **v2** reinterprets `MAPS_TO.subject` as a SCIP-inspired type claim-symbol ([`claim-symbol-grammar-2026-07-30.md`](claim-symbol-grammar-2026-07-30.md); ADR [`claim-symbol-entity-identity-adr-2026-07-30.md`](claim-symbol-entity-identity-adr-2026-07-30.md); `doc_engine.scanning.symbol`). Stale v1 simple-name subjects are obsolete on next scan — no dual-read.

**Not** a required certification gate replacing Path A. Existing `entity_table_map` / evidence bags remain the Path A contract; facts validate when present under `--all`.

## Record fields

| Field | Type | Notes |
|-------|------|--------|
| `predicate` | string | `rule_id` for evidence hits; `EVIDENCE` if no rule; `MAPS_TO` for entity→table |
| `subject` | string | Evidence: file path. Maps: type claim-symbol per [`claim-symbol-grammar-2026-07-30.md`](claim-symbol-grammar-2026-07-30.md) |
| `object` | string or null | Evidence: match text. Maps: table name |
| `qualifiers` | object | Evidence: may include `bucket`. Maps: required `display_name`, `fqcn`, `symbol_kind` (`type`); may include `status`, `table_name_source` |
| `file` | string or null | Source path |
| `line` | int or null | 1-based when known (`< 1` rejected) |
| `rule_id` | string or null | Stage 0 rule id when known |
| `scanner` | string or null | Row scanner, else comma-joined `signals.scanners` |

All eight keys are always present. Unknown keys are **rejected**.

## Emission rules

1. Each `evidence[*][]` hit → one fact (`predicate` = `rule_id` or `EVIDENCE`).
2. Each `entity_table_map` entry → `MAPS_TO` with a **type symbol** subject. If `status == "contested"` and `candidates` is non-empty → **one `MAPS_TO` per candidate**, each with its own package-qualified symbol (identity is not shared across colliding simple names). Path A map keys remain simple class names.
3. Facts are sorted by `(predicate, subject, object, file, line)`.
4. `write_facts_jsonl` validates each row through `Fact` before encode (write-time bite).

Implementation: `doc_engine.scanning.facts` (`facts_from_signals`, `write_facts_jsonl`, `fact_emit_counts`).

## Observability

`python -m doc_engine.tools.spring_signal_scan` prints counters on stdout and a JSON line on stderr:

`{"event":"facts_emit","path":"...","facts_total":N,"facts_maps_to":N,"facts_maps_to_contested":N,"facts_evidence":N}`

These counters are for gap/error analysis across runs. They are **not** certification inputs.
