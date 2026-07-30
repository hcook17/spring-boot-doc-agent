# Adoption blockers queue (post dual-emit) — 2026-07-30

Queued from the external principal review (`spring-boot-doc-agent-review.md`) after Phase 1 dual-emit. **Do not fold into the dual-emit PR.**

Theme (review §10): controls that are real but one layer away from where they bite.

North-star for build/review/refactor (moved under product design): [`docs/design/ddia-north-star/`](../../docs/design/ddia-north-star/). Blindspot note: [`coverage-sor-derived-blindspot-2026-07-30.md`](coverage-sor-derived-blindspot-2026-07-30.md).

## B1 — Client identifier purge + repo-wide denylist — **done**

- ~~Purge known client checkout dirname from tracked hits (baseline, tests, session-log fingerprint).~~
- ~~Extend `check_no_client_identifiers` beyond bytecode-oracle JSON to a **repo-wide** denylist pass.~~ `python3 scripts/ci/check_no_client_identifiers.py --tracked-tree`; tokens live only in `scripts/ci/client_identifier_denylist.txt`.
- ~~Regression: committed fixture that would fail CI if the string reappears in tracked paths.~~ Unit test plants a denylist token into a temp path set and asserts findings (token must not be committed outside the denylist file).

## B2 — Live certification chain — **done**

- ~~`doc-engine pipeline gates` must **write/merge** `certification.json` with `generative_executor: "live"` and the gates actually run.~~
- ~~`certification verify` rejects `none`/`mock` unless `--allow-mock`.~~
- ~~Regression: drop false docs into a deterministic_only cert run; verify must not stay OK after a live gates pass that should fail (and live path must update the certificate).~~ Covered by `tests/doc_engine/test_live_gates.py` (stale mock cert overwritten; failing live gates → `certified: false`).

## B2.5 — Certification as derived view (DDIA) — **done**

- ~~Treat `certification.json` as a recomputable fold over stage/gate facts (`StageRecord.executor`; schema_version stays 1 — bump only on breaking changes).~~
- ~~Live gates **derive** stages (keep deterministic, drop mock generative, append `generative_external`) — not LWW merge + stamp.~~
- ~~Fold rules: stage `fail` always fails; `skipped` fails only if required by profile; `mock_under_live` consistency.~~
- Design note: [`certification-derived-view-2026-07-30.md`](certification-derived-view-2026-07-30.md).

## B3 — Strict citations on the live gates path — **done**

- ~~Add `--compliance-profile` to the `gates` subcommand; derive strict citation checking like `local_runner`.~~
- ~~Regression: non-strict vs certified profile exit codes on a planted weak citation set.~~
- `citations_are_strict()` is the shared SoT used by `local_runner` and `live_gates`.

## B4 — Wire unused DDIA findings validator — **done (schema-contracts-research)**

- ~~Call `validate_architecture_testing_review_findings` from `run_stage5_gate`.~~
- ~~Regression: malformed `architecture_testing_review.json` fails the live gate (not only unit tests of the helper).~~ Covered by `Stage5ArchitectureTestingReviewGateTest` + Pydantic `ArchitectureTestingReviewArtifact` in `ARTIFACT_MODELS`.

## B5 — Stale current-state claims — **done (stale-claims-hygiene PR)**

- ~~README / drift docstring: tier-2 is full-repo filter, not per-file ast-grep subprocess.~~ Corrected: tier 1 hash → one fresh `scan()` → per-citation compare against filtered bag.
- ~~`CONSTRAINTS.md`: overlap-cascade / `carry_forward` / CI enumeration warnings that outlived the fixes.~~ Overlap `[Resolved]` (`carried_in_paths`); CI is `pytest tests/` / `testpaths`; STATUS `ENFORCE` prose aligned; Phase 1 memo §5 gate closed; content-stable claim keys stop ordinal baseline churn.
- Prefer outcome-bound tests over substring-only `verify:` where the claim is behavioral. Closed vocabulary includes `called_by:` and `behavior:<key>` (pre-registered in `check_repo_claims.py`, like `DERIVATIONS`); product wiring that needs runtime shape lives in `tests/test_control_wiring.py`. Attach live `verify:` for Phase B claims only when the underlying wiring is true.

## Later queue (numbered)

### L1 — Semgrep negative fixtures + FP ratchet — **done**

- Positive non-vacuity retained; hermetic negatives under `scripts/coverage/semgrep_rule_fixtures_negative/`.
- `check_fp_ratchet` (counts must not **rise**) vs `semgrep_rule_fp_baseline.json`; `--update-fp-baseline`.
- Cite north-star `coverage-gates` / `trust-but-verify-and-auditability`.
- Real-corpus semgrep **recall** baseline still absent (do not invent client names).

### L2 — Stage-4 fan-out in `capacity_preflight`

- After L1; capacity model still under-counts Stage-4 fan-out relative to post–cross-group-edges reality.

### L3 — Claim-symbol single-token entities

- Larger fact-store redesign; not a drive-by.

### L4 — Branch protection (human)

- `CONSTRAINTS.md` enterprise item 6 — `gh api` repo-admin; not agent.

### L5 — Thin drift/capacity schemas

- Schema memo slice 5 — lowest schema priority.

### L6 — Coverage SoR hygiene follow-ons

- `rule_coverage_baseline.json` schema_version 1→2 regenerate; optional `codeql_rule_count` derivation; any residual doc debt after this PR's CLAUDE/CONSTRAINTS/tool-quirks corrections.
