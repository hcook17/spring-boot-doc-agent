---
id: trust-but-verify-and-auditability
kind: concept
completeness: operational
tags: [audit, integrity, end-to-end, verification]
epub_anchors:
  - { chapter: 13, title: "Trust, but Verify" }
  - { chapter: 13, title: "Designing for auditability" }
  - { chapter: 13, title: "The End-to-End Argument for Databases" }
related: [sor-vs-derived, coverage-gates, transactions-and-integrity-lite]
last_refined: 2026-07-30
path: domains/04-integrity-and-verification/concepts/trust-but-verify-and-auditability.md

---

# Trust, but verify (and auditability)

## In one sentence

Assume components usually keep their promises, but design so integrity can be checked end-to-end — because local ACID or a green CI step does not stop application-level corruption or vacuous gates.

## When to open

- A gate that can pass by checking nothing.
- Certification / coverage claims without witnesses.
- “The database is serializable so we are safe.”

## Core claims

- System models state what may fail; verify rather than trusting marketing.
- End-to-end argument: strong storage properties do not fix buggy writers.
- Event/log style improves auditability when derivation is deterministic and replayable.
- Immutable append-only inputs limit blast radius of bad code vs overwrite-in-place.

## Tradeoffs

- Verification has cost (fixtures, ratchets, oracle compares).
- Over-verification without witnesses → theater.
- Under-verification → confidently wrong docs (this repo’s stated principal risk).

## Repo analogues

- Non-vacuity + invented-rule tests; FP ratchet; `check_repo_claims` mechanical half.
- Live cert fail-closed; strict citations on compliance profiles.
- Prompt 10 evidence tiers A/B/C.

## Review checks

1. What would a vacuous pass look like for this control — is it tested?
2. Is there a witness (fixture, counterexample, failing case)?
3. Can a later session re-run the check without tribal knowledge?

## Refactor signals

- Soft-pass on missing baseline for a gate that claims to enforce precision.
- Skipping binary-dependent tests without `skipTest` (false green).

## Anti-patterns seen

- Positive-only semgrep coverage: rules can fire, FPs unmeasured until L1.

## See also

- `coverage-gates`, `architecture-decision-review`
