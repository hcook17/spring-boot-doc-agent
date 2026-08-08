# SPEC — pr-94-query-surface

**schema_version:** 1
**input_kind:** review_remediation

## Goal

Remediate findings from docs/reviews/9bc7851_PR_94.md (31 items; 2 critical).

## Requirements

- C1: Arbitrary file read: containment opt-in; nothing opts in
- C2: `tokensUsed` under-reports; budget does not bound serialized output
- H1: Nested fan-out unbounded; `truncated` lies
- H2: `RedactionProvider` dead on production shape
- H3: Unknown filters → silent empty success
- H4: MCP fault isolation missing

## Data-source inventory

| ID | Data need | Origin |
|---|---|---|
| INV-C1 | Arbitrary file read: containment opt-in; nothing opts in | src/doc_engine/query/load.py |
| INV-C2 | `tokensUsed` under-reports; budget does not bound serialized output | claude/research/context-packet-schema-spike-2026-08-07.md |
| INV-H1 | Nested fan-out unbounded; `truncated` lies | new — to be built |
| INV-H2 | `RedactionProvider` dead on production shape | new — to be built |
| INV-H3 | Unknown filters → silent empty success | new — to be built |
| INV-H4 | MCP fault isolation missing | scripts/ratchets/mutate.py |
| INV-S3-1 | Spike (3d) | new — to be built |
| INV-S3-2 | Spike (2d) | new — to be built |
| INV-S3-3 | Spike (2d) | new — to be built |
| INV-S3-4 | Spike (2d) | new — to be built |
| INV-S3-5 | Spike (1d) | new — to be built |
| INV-S3-6 | Spike (2d) | new — to be built |

## Critical assumptions

- Severity: Critical (Information Disclosure / Confused Deputy)**
- Severity: Critical (Broken contract / DDIA backpressure failure)**

## Decisions

| Decision | Blocks | Resolution |
|---|---|---|
| Server-derived root mandatory for MCP | Q0-1 | locked — C1 Critical |
| Payload Option A (row_ref / honest serialized budget) | Q0-2 | locked |

## Out of scope

- Do not re-litigate verified non-findings from the review.

## Seeded findings

- `C1`
- `C2`
- `H1`
- `H2`
- `H3`
- `H4`
- `Q0-1`
- `Q0-2`
- `Q0-3`
- `Q0-4`
- `Q0-5`
- `Q1-1`
- `Q1-2`
- `Q1-3`
- `Q1-4`
- `Q1-5`
- `Q1-6`
- `Q2-1`
- `Q2-2`
- `Q2-3`
- `Q2-4`
- `Q2-5`
- `Q2-6`
- `S3-1`
- `S3-2`
- `S3-3`
- `S3-4`
- `S3-5`
- `S3-6`
- `Q4-1`
- `Q4-3`

**Source review:** `docs/reviews/9bc7851_PR_94.md`

