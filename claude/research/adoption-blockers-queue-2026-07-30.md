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

## B4 — Wire unused DDIA findings validator — **done (schema-contracts-research)**

- ~~Call `validate_architecture_testing_review_findings` from `run_stage5_gate`.~~
- ~~Regression: malformed `architecture_testing_review.json` fails the live gate (not only unit tests of the helper).~~ Covered by `Stage5ArchitectureTestingReviewGateTest` + Pydantic `ArchitectureTestingReviewArtifact` in `ARTIFACT_MODELS`.

## B5 — Stale current-state claims — **done (stale-claims-hygiene PR)**

- ~~README / drift docstring: tier-2 is full-repo filter, not per-file ast-grep subprocess.~~ Corrected: tier 1 hash → one fresh `scan()` → per-citation compare against filtered bag.
- ~~`CONSTRAINTS.md`: overlap-cascade / `carry_forward` / CI enumeration warnings that outlived the fixes.~~ Overlap `[Resolved]` (`carried_in_paths`); CI is `pytest tests/` / `testpaths`; STATUS `ENFORCE` prose aligned; Phase 1 memo §5 gate closed; content-stable claim keys stop ordinal baseline churn.
- Prefer outcome-bound tests over substring-only `verify:` where the claim is behavioral. Closed vocabulary includes `called_by:` and `behavior:<key>` (pre-registered in `check_repo_claims.py`, like `DERIVATIONS`); product wiring that needs runtime shape lives in `tests/test_control_wiring.py`. Attach live `verify:` for Phase B claims only when the underlying wiring is true.

## Explicitly later (weeks — not this PR)

Claim-symbol single-token entities; semgrep negative fixtures + FP ratchet; Stage-4 fan-out in capacity_preflight; branch protection; thin drift/capacity schemas (memo slice 5). Review/edges/gap/cert schema work landed with B4 on `schema-contracts-research` — see [`schema-contracts-decision-memo-2026-07-30.md`](schema-contracts-decision-memo-2026-07-30.md).
