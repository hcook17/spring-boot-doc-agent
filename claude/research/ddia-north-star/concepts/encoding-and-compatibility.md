---
id: encoding-and-compatibility
kind: concept
completeness: operational
tags: [encoding, json, schema, rpc, compatibility]
epub_anchors:
  - { chapter: 5, title: "The Merits of Schemas" }
  - { chapter: 5, title: "Modes of Dataflow" }
related: [schema-evolution-and-data-outlives-code]
last_refined: 2026-07-30
---

# Encoding and compatibility

## In one sentence

Shared schemas make multi-writer/multi-reader evolution tractable; schemaless convenience shifts the cost to runtime failures and tribal knowledge.

## When to open

- Pydantic / JSON Schema for artifacts.
- Semgrep/check_id path prefixes and id conventions.
- RPC vs event vs DB dataflow boundaries.

## Core claims

- Schemas (even simple ones) beat ad-hoc JSON for evolution across languages and time.
- Dataflow mode matters: DB retains old values; RPC often assumes shorter-lived skew; events need compatible envelopes.
- Reader/writer version skew is normal — design for it.
- Validation without gate bite is debt (schema memo).

## Tradeoffs

- Heavy schema upfront vs open-world bags (`spring_signals` stays open; `facts.jsonl` closed).
- Exporting JSON Schema without Stage wiring → false confidence.

## Repo analogues

- `ARTIFACT_MODELS`, `scripts/schemas/`, facts closed contract.
- Semgrep `__` ids so `check_id.rsplit(".", 1)[-1]` is cwd-safe.
- Baseline JSON schemas for ratchets.

## Review checks

1. Is the artifact open-world or closed-world on purpose?
2. Does a schema change keep old readers/writers working?
3. Is validation invoked on the live path that matters?

## Refactor signals

- Free `dict` at a boundary that already has a model.
- Schema file with no caller.

## Anti-patterns seen

- Review helper existed while Stage 5 omitted it (B4 closed).

## See also

- `schema-evolution-and-data-outlives-code`
