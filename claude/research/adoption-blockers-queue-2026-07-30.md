# Adoption blockers queue (post dual-emit) — 2026-07-30

Queued from the external principal review (`spring-boot-doc-agent-review.md`) after Phase 1 dual-emit. **Do not fold into the dual-emit PR.** Next engineering PR after `facts.jsonl` lands on `main`.

Theme (review §10): controls that are real but one layer away from where they bite.

## B1 — Client identifier purge + repo-wide denylist

- Purge `ocs-api-service-develop` from tracked hits (baseline, tests, session-log fingerprint).
- Extend `check_no_client_identifiers` (or CI gate) beyond bytecode-oracle JSON to a **repo-wide** denylist pass.
- Regression: committed fixture that would fail CI if the string reappears in tracked paths.

## B2 — Live certification chain

- `doc-engine pipeline gates` must **write/merge** `certification.json` with `generative_executor: "live"` and the gates actually run.
- `certification verify` rejects `none`/`mock` unless `--allow-mock`.
- Regression: drop false docs into a deterministic_only cert run; verify must not stay OK after a live gates pass that should fail (and live path must update the certificate).

## B3 — Strict citations on the live gates path

- Add `--compliance-profile` to the `gates` subcommand; derive strict citation checking like `local_runner`.
- Regression: non-strict vs certified profile exit codes on a planted weak citation set.

## B4 — Wire unused DDIA findings validator

- Call `validate_architecture_testing_review_findings` from `run_stage5_gate`.
- Regression: malformed `architecture_testing_review.json` fails the live gate (not only unit tests of the helper).

## B5 — Stale current-state claims

- README / drift docstring: tier-2 is full-repo filter, not per-file ast-grep subprocess.
- `CONSTRAINTS.md`: overlap-cascade / `carry_forward` / CI enumeration warnings that outlived the fixes.
- Prefer outcome-bound tests over substring-only `verify:` where the claim is behavioral.

## Explicitly later (weeks — not this PR)

Claim-symbol single-token entities; semgrep negative fixtures + FP ratchet; schemas for review/edges artifacts; Stage-4 fan-out in capacity_preflight; branch protection.
