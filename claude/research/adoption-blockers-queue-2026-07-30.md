# Adoption blockers queue (post dual-emit) — 2026-07-30

Queued from the external principal review (`spring-boot-doc-agent-review.md`) after Phase 1 dual-emit. **Do not fold into the dual-emit PR.**

Theme (review §10): controls that are real but one layer away from where they bite.

North-star (design SoR): [`docs/design/ddia-north-star/`](../../docs/design/ddia-north-star/). Blindspot note: [`coverage-sor-derived-blindspot-2026-07-30.md`](coverage-sor-derived-blindspot-2026-07-30.md).

Every open L-item below carries a **DDIA card** (domain, ids, SoR vs derived, upstream check). Deviations live under [`docs/design/ddia-north-star/deviations/`](../../docs/design/ddia-north-star/deviations/).

## DDIA north-star thorough campaign (N-wave) — **honesty pass for this slice; campaign not complete**

| Wave | Status | Delivered |
|------|--------|-----------|
| Foundation | honesty pass | Depth gate + operational ratchet + prior-art; anti-Goodhart uniqueness/domain-ownership — not a proof of decision-readiness |
| A | honesty pass | Domain `07` + `ch07`; L2 **proxy** landed (capacity risk **not** closed) |
| B | honesty pass | Domain `09`; id-stable `batch-vs-stream`; `ch01`/`ch11`/`ch12` operational; `ch10` demoted bridge |
| C | honesty pass | Encoding/replication chapters deepened; domain `08` remains **partial** (hollow until local concept) |
| D | honesty pass | Domain `10` remains **partial** (hollow); `ch09`/`ch13`/`ch14` operational |
| E | honesty pass / campaign open | Slice honesty (UTF-8, STATUS/queue, demotions, depth gate) landed; thorough catalog campaign **not** complete while hollow domains/bridges remain |

Honest residual `partial`: domains `06`, `08`, `10`; `ch04`, `ch10`; lite concepts.

## Standing claim-pinning policy (B5 residual — not open work)

Prefer outcome-bound tests over substring-only `verify:` where the claim is behavioral. Closed vocabulary includes `called_by:` and `behavior:<key>` (pre-registered in `check_repo_claims.py`, like `DERIVATIONS`). Product wiring that needs runtime shape lives in [`tests/ci/test_control_wiring.py`](../../tests/ci/test_control_wiring.py). Attach live `verify:` / `behavior:` only when the underlying wiring is already true (same rule for L2+ and future claims). Weak substring `contains:` is a weak witness — cite `trust-but-verify-and-auditability` / `rel-gate-needs-witness`.

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
- Design note: [`certification-derived-view-2026-07-30.md`](certification-derived-view-2026-07-30.md). Deviation: `dev-certification-derived-view`.

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
- Residual policy: see **Standing claim-pinning policy** above (not an open todo).

## Later queue (numbered)

### L1 — Semgrep negative fixtures + FP ratchet — **done**

- Positive non-vacuity retained; hermetic negatives under `scripts/coverage/semgrep_rule_fixtures_negative/`.
- `check_fp_ratchet` (counts must not **rise**) vs `semgrep_rule_fp_baseline.json`; `--update-fp-baseline`.
- Cite `coverage-gates` / `trust-but-verify-and-auditability` / `dev-fp-ratchet-separate-from-recall`.
- Real-corpus semgrep **recall** baseline still absent (do not invent client names).

### L2 — Capacity Stage-4 load vs post–cross-group-edges reality — **open (proxy landed, risk not closed)**

**DDIA card**

| Axis | Value |
|------|--------|
| Domain | `07-partitioning-and-skew`, `01-data-flow-and-truth`, `05-maintainability-and-change` |
| Open | `rel-partition-bounds-fanout`, `partition-key-and-hotspots`, `rel-sor-feeds-views`, `claims-and-status-drift`, `ch07` |
| SoR | Pipeline dispatch graph (`VALID_DOC_FILES` / `manifest_fanout`, SKILL generative choreography) + group token estimates + Stage-0 edges for Stage-1 slices; Stage-4 real inputs = summaries + interview_answers + signals (`stages.py`) |
| Derived | `capacity_preflight_report.json` / CLI warnings (`stage4_metric_kind: partial_proxy_pre_stage4`; `stage4_omitted_not_estimated` includes interview; numeric `*_upper_bound_*` fields are warn thresholds only) |
| Upstream | After edges replaced Stage-1 broadcast, Stage-1 slice looks fine while Stage-4 still ships merged evidence — Stage-0 can only **proxy** future summary size from group `est_tokens` + optional signals. |
| Deviation | None for measuring a proxy; claiming Stage-4 risk closed while omissions are non-empty would need a deviation (do not) |

**Work landed (measurement):** Stage-4 fan-out from `VALID_DOC_FILES`; partial proxy fields + omissions; `--stage4-shared-tokens-warn-threshold`; signals + `signals_omitted`; polarity + pipeline SoR mirror tests; domain 07 + operational `ch07`.

**Still open for L2 (threshold calibration — not inventing numbers):**
- Keep `metric_kind: partial_proxy_pre_stage4` at Stage 0 forever for pre-run estimates.
- Recalibrate `--stage4-shared-tokens-warn-threshold` only with numbers from a real mid-size run (document the run). Default **80000** unchanged until then.
- Do **not** invent interview token guesses at Stage 0.
- Thin formal schema still L5 for `drift_report`.

### L2b — Post-Stage-1 Stage-4 input calibration — **CLI on main; default retained (research closed)**

**DDIA card:** same as L2; SoR = on-disk Stage-4 inputs after they exist. Measurement mode **merged** (PR #74). **Calibration research (2026-07-30):** [`l2b-stage4-threshold-calibration-2026-07-30.md`](l2b-stage4-threshold-calibration-2026-07-30.md) — two independent **spring/summer 2026** arXiv reviews (2604.01664 ContextBudget; **2607.24653 Kimi K3**), GitHub+DeepWiki (LiteLLM, LangGraph, Kimi-K3), prompt-11 BFS/DFS. **Decision: retain default 80000.** (Aug 2025 RCR-Router demoted.) Changing the default still requires a documented mid-size `measured_stage4_inputs` run (frontier). Returns still omitted.

### L3 — Claim-symbol single-token entities — **code landed (principal-complete B)**

**DDIA card:** domain `02-encoding-and-evolution`; open `schema-evolution-and-data-outlives-code`, `encoding-and-compatibility`, `rel-schema-outlives-writers`. SoR = facts / claim keys. **Normative grammar:** [`claim-symbol-grammar-2026-07-30.md`](claim-symbol-grammar-2026-07-30.md). **ADR:** [`claim-symbol-entity-identity-adr-2026-07-30.md`](claim-symbol-entity-identity-adr-2026-07-30.md) — Accepted/implemented. Type `MAPS_TO.subject` = claim-symbol (`FACTS_LEDGER_SCHEMA_VERSION = 2`); `display_name`/`fqcn` required; write-time `parse` bite; Path A simple-name residual; no SCIP wire / no member fact rows / no dual-read.

### L4 — Branch protection (human) — **deferred until later (owner)**

**DDIA card:** domain `05-maintainability-and-change`; open `maintainability-operability-evolvability`, `trust-but-verify-and-auditability`. `CONSTRAINTS.md` enterprise item 6 — `gh api` repo-admin; **not agent**. Confirmed unprotected (404, 2026-07-30). **Owner is not doing L4 now** — does not block L2b / L3 sequencing. Choosing never to require CI would need a written deviation.

### Gap probe + AET — Stage-0 residual measurement — **landed (schema v2)**

Tool: `python -m doc_engine.tools.gap_probe` (`GAP_PROBE_SCHEMA_VERSION = 2`). Rates memo: [`gap-probe-measurement-design-2026-07-30.md`](gap-probe-measurement-design-2026-07-30.md). **AET normative:** [`aet-measurement-2026-07-30.md`](aet-measurement-2026-07-30.md) — \(\hat{\mathcal{M}}\) with callable denoms, scoring-env \(\Delta\hat{\mathbf{r}}\), residuals, \(U_w\) comparison index, \(\Pi_B\)/\(L(B)\); axioms A1–A5. Opt-in ocs tests: [`tests/doc_engine/test_gap_probe_ocs_real_world.py`](../../tests/doc_engine/test_gap_probe_ocs_real_world.py) via `GAP_PROBE_OCS_ARTIFACTS_DIR` / `GAP_PROBE_OCS_REPO`+`GAP_PROBE_OCS_LIVE_SCAN`. **ocs 2026-07-30 (v1 baseline):** \(R_{\text{sym}}=1\), \(R_{\text{coll}}=0\), \(R_{\text{join}}=1\), \(\bar R_{\text{lin}}=0.49\), \(U=0.278\); dominant lineage failure = `dialect_or_syntax` (95).

**Re-rank from thresholds (not narrative):**

| Item | Decision |
|------|----------|
| Path A simple-name rekey | **Do not reopen** — \(R_{\text{coll}}=0\) and \(R_{\text{join}}=1\) on ocs |
| L5 / L6 | **L5 + slice-5 + L6 done** — AET does not displace product engineering; lineage residual after L6 |
| Lineage dialect investment | **Measured residual** after L5/L6 — dominant stratum fired |
| Capacity 80k | **Unchanged** — separate Stage-4 `measured_stage4_inputs` family |

### L5 — Thin drift / capacity schemas — **done (slice 5 closed)**

**DDIA card:** domain `02-encoding-and-evolution`; open `encoding-and-compatibility`, schema memo slice 5. Scope: primarily **`drift_report`** (residual capacity fields only if L2 did not touch them). Additive + `schema_version` per `rel-schema-outlives-writers`; do not invent fields without writers.

**Landed:** `DRIFT_REPORT_SCHEMA_VERSION = 1` on both `check_drift` return paths; `DriftReportArtifact` (+ nested thin models) registered in `ARTIFACT_MODELS` / `ARTIFACT_FILENAMES`; `scripts/schemas/drift_report.schema.json`; contract tests in `tests/doc_engine/test_drift_report_schema.py`; opt-in ocs witness in `tests/doc_engine/test_drift_report_ocs_real_world.py` (`DRIFT_OCS_ARTIFACTS_DIR` + `DRIFT_OCS_REPO`).

**Slice-5 residual (capacity) landed:** `CAPACITY_PREFLIGHT_REPORT_SCHEMA_VERSION = 1` on both `compute_preflight` and `compute_stage4_calibration`; `CapacityPreflightReportArtifact` (+ `CapacityWarningRow`, closed `Stage4MetricKind`) registered in `ARTIFACT_MODELS` / `ARTIFACT_FILENAMES`; `scripts/schemas/capacity_preflight_report.schema.json`; contract tests in `tests/doc_engine/test_capacity_preflight_schema.py`. Required keys = writer intersection (stage4 pool + warnings); mode-specific fan-out / calibration keys ride `extra="allow"`. Slice 5 closed.

### L6 — Coverage SoR hygiene follow-ons — **done**

**DDIA card:** domains `01` + `04`; cite `dev-coverage-denominator-codeql`, `coverage-gates`, `rel-gate-needs-witness`.

**Landed:** `rule_coverage_baseline.json` → `schema_version` 2; `check_ratchet` / `check_non_vacuity` fail-closed (missing baseline, corrupt JSON, missing/non-object `counts`, empty pack); hermetic committed-schema witness in `tests/coverage/test_rule_coverage.py`; `codeql_rule_count` derivation enumerates both `rule_id = "…"` and `"…" as rule_id` (so `raw_queries__query` stays pack-owned and measured); `write_baseline` filters to pack-owned keys. **Standing ban:** do **not** invent client-named semgrep recall baseline (`dev-fp-ratchet-separate-from-recall`).
