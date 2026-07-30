# Facts ledger schema (Phase 1 dual-emit)

Companion to [`fact-store-phase1-decision-memo-2026-07-30.md`](fact-store-phase1-decision-memo-2026-07-30.md) §3.

**Artifact:** `facts.jsonl` — UTF-8 JSON Lines, one fact object per line, written beside `spring_signals.json` by `python -m doc_engine.tools.spring_signal_scan`.

**Not** a required certification gate in Phase 1. Existing `entity_table_map` / evidence bags remain the Path A contract.

## Record fields

| Field | Type | Notes |
|-------|------|--------|
| `predicate` | string | `rule_id` for evidence hits; `EVIDENCE` if no rule; `MAPS_TO` for entity→table |
| `subject` | string | Evidence: file path. Maps: simple class name |
| `object` | string or null | Evidence: match text. Maps: table name |
| `qualifiers` | object | May include `bucket`, `status`, `table_name_source` |
| `file` | string or null | Source path |
| `line` | int or null | 1-based when known |
| `rule_id` | string or null | Stage 0 rule id when known |
| `scanner` | string or null | Row scanner, else comma-joined `signals.scanners` |

All eight keys are always present.

## Emission rules

1. Each `evidence[*][]` hit → one fact (`predicate` = `rule_id` or `EVIDENCE`).
2. Each `entity_table_map` entry → `MAPS_TO`. If `status == "contested"` and `candidates` is non-empty → **one `MAPS_TO` per candidate** (derived stub).
3. Facts are sorted by `(predicate, subject, object, file, line)`.

Implementation: `doc_engine.scanning.facts` (`facts_from_signals`, `write_facts_jsonl`, `fact_emit_counts`).

## Observability

`python -m doc_engine.tools.spring_signal_scan` prints counters on stdout and a JSON line on stderr:

`{"event":"facts_emit","path":"...","facts_total":N,"facts_maps_to":N,"facts_maps_to_contested":N,"facts_evidence":N}`

These counters are for gap/error analysis across runs. They are **not** certification inputs.
