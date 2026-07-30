---
id: rel-schema-outlives-writers
kind: relationship
completeness: operational
tags: [relationship, schema, evolution]
related: [schema-evolution-and-data-outlives-code, encoding-and-compatibility]
last_refined: 2026-07-30
path: domains/02-encoding-and-evolution/relationships/schema-outlives-writers.md

---

# Relationship: schema outlives writers

## In one sentence

Schemas and on-disk artifacts persist across code deploys; writers and readers must stay compatible across skew.

## Who

Schema owners, writers (producers), readers (consumers / gates), migration owners.

## What

Edge: `Schema --constrains--> Writer/Reader` across versions; additive evolution preferred under skew.

## When

Any baseline, JSON schema, ratchet file, or fixture format change.

## Where

`*.schema.json`, coverage baselines, certification shapes, Pydantic models, `<!-- derived: -->` keys.

## Why

Data (and baselines) outlive the PR that wrote them; breaking readers without a migration is a production incident in slow motion.

## How

1. Prefer additive fields with defaults.
2. Bump `schema_version` when semantics change.
3. Provide a migration or dual-read window — do not “fix CI” by inventing fake SoR numbers.

## See also

`schema-evolution-and-data-outlives-code`, `dev-fp-ratchet-separate-from-recall`
