---
id: rel-gate-needs-witness
kind: relationship
completeness: operational
tags: [relationship, gate, audit]
related: [trust-but-verify-and-auditability, coverage-gates, dev-fp-ratchet-separate-from-recall]
last_refined: 2026-07-30
path: domains/04-integrity-and-verification/relationships/gate-needs-witness.md

---

# Relationship: gate needs witness

## In one sentence

A trust or coverage claim is only as strong as its **witness corpus** and failure direction; gates without witnesses are vacuous.

## Who

Gate author, CI maintainer, reviewer who asks “what would make this fail?”

## What

Edge: `Claim --proven_by--> Witness` (positive fixtures, negative fixtures, ratchet baseline, audit log).

## When

Adding or changing any CI gate, ratchet, or “we verified X” prose.

## Where

`rule_coverage`, `semgrep_rule_coverage`, `check_repo_claims`, live_gates, certification verify.

## Why

Without a witness, green CI means “script ran,” not “property holds.”

## How

1. Name the property.
2. Name the witness path and the bad direction (drop vs rise).
3. Separate witnesses when properties invert (`dev-fp-ratchet-separate-from-recall`).
4. Refuse gates that can only pass.

## See also

`coverage-gates`, `trust-but-verify-and-auditability`
