# Deterministic boundary schemas + SPI (research note)

Date: 2026-07-29  
Status: **research only — do not implement in the Suite SoT / hygiene PR**  
Aligns with: `STATUS.md` sequencing lock; `claude/10-architecture-maturation-plan.md` fact-store Phase 1  
Supersedes: nothing; scopes work deferred from “Pydantic everywhere / entry points” discussion

> **Sequencing supersession (2026-07-30):** For *which artifacts get schemas in what order*, use [`research/schema-contracts-decision-memo-2026-07-30.md`](research/schema-contracts-decision-memo-2026-07-30.md) (corpus + collation siblings). This note’s answers on write-vs-read validation, ephemeral JSON vs fact SoR, **no SPI**, and package boundary remain in force and are adopted by that memo.

## Why this note exists

Suite-layout hygiene closes a **packaging/layout** dual-home (`tests/` via `pyproject.toml` `testpaths`, no `scripts/` pytest forwarders). Broader deterministic-tool **data-interface** hardening (typed I/O, optional SPI) is a different failure mode and must not share that PR.

STATUS already records Pydantic stage artifacts, JSON Schema exports, `validate_artifacts`, and CI schema-gating of the spring fixture. The residual is uneven `Dict[str, Any]` at scanner/tool edges — a maturation pass, not a blocker for deleting test wrappers.

## Inventory (evidence, not a rewrite plan)

| Surface | Today | Notes |
|---------|--------|-------|
| Stage artifacts | Pydantic in `src/doc_engine/pipeline/` + `validate_artifacts` | Keep as SoT for inter-stage JSON |
| `doc_engine.tools.*` CLIs | Mix of typed validation and dict JSON | Certification-critical paths should fail closed on read/write |
| Scanning SDK | Still heavy `Dict[str, Any]` in merge/orchestrator | Natural fact-store Phase 1 input shape |
| Meta `scripts/` | Untyped by design | Do not pull into the product wheel |

Product tools under `src/doc_engine/tools/` (as of this note): `spring_signal_scan`, `spring_drift_check`, `run_manifest`, `capacity_preflight`, `partition_repo`, `pipeline_validators`, `citation_coverage`, `check_pipeline_output`, `check_no_secrets_leaked`, `build_docs_site`, `build_cross_group_edges`, `semantic_eval_helpers`, `doc_tag_utils`, `validate_artifacts`, `certification`, plus bootstrap.

## Questions a principal design must answer before code

1. **Write-time vs read-time validation** — which artifacts must be schema-valid when produced vs only when certified?
2. **Ephemeral stage JSON vs fact-store tables** — which models become durable facts / materialized views (`claude/10-architecture-maturation-plan.md` Class A) vs stay pipeline-local?
3. **SPI** — default bias: **keep `build_stage_specs()` as the only registry**. Entry points only if a real third-party scanner/adapter story appears; do not invent plugins for one in-tree Claude adapter.
4. **Package boundary** — schemas that certification depends on live in `doc_engine`; meta ratchets stay in `scripts/`.

## Non-goals

- No web framework, DI container, or workflow engine for deterministic tools.
- No folding this work into suite-layout hygiene or shim-deletion PRs.
- No second markdown “schema inventory” that drifts from code — when implementation starts, models and JSON Schema exports remain the SoT.

## Recommended sequence

1. Land Suite SoT hygiene (layout only).
2. Fact-store Phase 1 design (STATUS-locked product investment).
3. Use that design to decide which remaining dict edges get Pydantic (and whether any entry-point SPI is justified).
