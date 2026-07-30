# Schema contracts decision memo (2026-07-30)

**Verdict: REFINE**

Not Confirm-as-written (“freeze facts only and stop”), not Pivot (“schematize everything / invent SPI before B1–B4”).

**Evidence:** [schema-coverage-corpus-2026-07-30.md](schema-coverage-corpus-2026-07-30.md), [schema-serde-approaches-collation-2026-07-30.md](schema-serde-approaches-collation-2026-07-30.md).  
**Aligns with:** [fact-store-phase1-decision-memo-2026-07-30.md](fact-store-phase1-decision-memo-2026-07-30.md), [adoption-blockers-queue-2026-07-30.md](adoption-blockers-queue-2026-07-30.md), DDIA SoR/views.

This memo **supersedes** [`../deterministic-boundary-schemas-spi-research-2026-07-29.md`](../deterministic-boundary-schemas-spi-research-2026-07-29.md) **for sequencing** of artifact schema work. That note’s write-vs-read / no-SPI conclusions remain valid and are adopted below.

---

## 1. What we confirm

1. **Uneven coverage is real and accurately described** — 4 of ~10 inter-stage artifacts have Pydantic + exported JSON Schema; the listed gaps (edges, review, gap_questions, capacity, drift, cert export) match the corpus.
2. **SoR vs derived vs view is the right taxonomy** — do not apply one openness policy to all.
3. **`spring_signals` stays open-world** — evolving bags; version lattice already exists.
4. **`facts.jsonl` should be closed-world** — eight-field ledger; `extra=forbid`; JSONL encoding; dual-emit already landed (PR #63).
5. **Schema without gate bite is debt** — especially `architecture_testing_review` (helper exists; `run_stage5_gate` omits it → B4).
6. **No product SPI** for artifact types; `ARTIFACT_MODELS` + `build_stage_specs()` remain registries.
7. **Do not block B1–B4** on a full schema catalog. Schema slices and product blockers interleave by risk.

---

## 2. What we refine (vs “finalize all schemas now”)

| Impulse | Refine to |
|---------|-----------|
| Finalize every artifact schema in one research outcome | Ranked implementation slices (below) |
| Freeze facts mid-flight without system map | Research first (this memo), then complete facts as **slice 1** |
| Dump JPA / full predicate vocabulary into JSON Schema | Out of scope — Phase 1 memo already refused |
| Treat cert `CertificationReport` as “unschematized” equally with free dicts | Typed today; **export** schema + register if desired — smaller than modeling edges |
| Schematize review without B4 | **Same change** as wiring `validate_architecture_testing_review_findings` into `run_stage5_gate` |

---

## 3. What we explicitly do not pivot to

- Neo4j / Glean-in-product as SoR
- Big-bang “Pydantic everywhere” PR
- Pausing client-ID purge / live cert / citations (B1–B3) until all schemas land
- Changing Stage 0 detection precision as part of schema work
- Mandatory RBAC / branch protection in-engine

---

## 4. Ranked implementation slices

| Slice | Work | Bite | Depends on |
|-------|------|------|------------|
| **1** | Complete `facts.jsonl` closed contract: `Fact`/`FactsArtifact`, JSONL loader, `scripts/schemas/facts.schema.json`, tests (RT + mutations), CI via existing deterministic_only `--all` once facts present | `validate_artifacts` rejects bad ledger; Stage 0 emit remains | Dual-emit on main |
| **2** | Export `certification.schema.json` from `CertificationReport` (optional register under validate if useful) | External/CI can check cert shape | Slice 1 not strictly required |
| **3** | Pydantic + schema for `cross_group_edges` and `gap_questions` (promote imperative → model; Stage 5 can call model or keep dual) | `--all` / Stage 5 | — |
| **4** | `architecture_testing_review` model **+ B4 gate wire** | Live Stage 5 fails on malformed review | Can parallel B1–B3 |
| **5** | Thin models for `drift_report` / `capacity_preflight_report` | Operator clarity | Lowest priority |

**Parallel product work (not schema-blocked):** B1 client-ID purge, B2 live cert chain, B3 strict citations — continue per adoption-blockers queue.

---

## 5. Policy locks (write / read / cert)

- **deterministic_only / scan_only:** require registered SoR/derived artifacts that the profile produces; do **not** require LLM view files.
- **certified / live gates:** when `gap_questions.json` or `architecture_testing_review.json` is present (or required by profile), Stage 5 must validate them (B4 for review).
- **facts:** validate when file present under `--all`; **not** a separate Path A replacement for `entity_table_map` (Phase 1).
- **Harness:** add `tests/test_artifact_serde_matrix.py` (or extend `test_artifact_schemas.py`) in slice 1 with registry rows; unschematized names skipped with reason.

---

## 6. Confirm / Refine / Pivot summary

| Claim | Tag |
|-------|-----|
| External §7 schema coverage list | **Confirmed** |
| Math of RT + mutation tests as acceptance for schema work | **Confirmed** |
| Implement all schemas before B1–B4 | **Refuted** |
| Closed facts as next schema engineering slice | **Confirmed** |
| Review schema alone without Stage 5 wire | **Refuted** |
| SPI for artifacts | **Refuted** |
| Open signals + closed facts coexistence | **Confirmed** |

**Overall: REFINE.**

---

## 7. Immediate next engineering

1. Research docs — **done**.
2. Slices 1–4 — **done in-tree** on `schema-contracts-research` (facts closed contract; cert/edges/gaps/review models + exported schemas; B4 Stage 5 wire).
3. Remaining product: B1–B3 adoption blockers; schema slice 5 (drift/capacity) last.
4. Land as reviewable PR(s); do not mix client-ID review dumps.

---

## 8. Review §7 siblings (recorded, not scheduled here)

Detection precision residuals, enterprise readiness, pyproject/shim/Python version claim — acknowledged as real; tracked outside this memo’s slices (CONSTRAINTS / admin / hygiene).
