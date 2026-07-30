# ADR — Claim-symbol / entity identity (L3)

**Date:** 2026-07-30  
**Status:** Proposed (research only — **no code in this change**)  
**Queue:** L3 — Claim-symbol single-token entities  
**DDIA:** domain `02-encoding-and-evolution`; `schema-evolution-and-data-outlives-code`, `encoding-and-compatibility`, `rel-schema-outlives-writers`; SoR vs derived in domain `01`  
**Depends on:** Phase 1 dual-emit lock ([fact-store-phase1-decision-memo-2026-07-30.md](fact-store-phase1-decision-memo-2026-07-30.md)); L2b measurement on `main` (PR #74); L2b threshold **default retained at 80000** after calibration research ([l2b-stage4-threshold-calibration-2026-07-30.md](l2b-stage4-threshold-calibration-2026-07-30.md), PR #75) — mid-size run still required to *change* 80k, not to author this ADR

---

## 1. Problem

Phase 1 ships a thin `facts.jsonl` ledger (`FACTS_LEDGER_SCHEMA_VERSION = 1`) beside `spring_signals.json`. Entity identity in that ledger is **not** collision-safe:

| Fact kind | Today’s `subject` | Failure mode |
|-----------|-------------------|--------------|
| Evidence | File path | Fine as a locator; not an addressable *type* / *member* entity |
| `MAPS_TO` | **Simple class name** | Two packages can share `User`; contested multi-edge does not fix the key |
| Qualifiers | Status / table_name_source | Carry provenance, not identity |

CONSTRAINTS already separates **resolved contested multi-`MAPS_TO`** from the **FQCN / fact-tuple backlog**. L3 is that backlog: how entities become **single-token, stable claim-symbols** in the facts SoR (and what, if anything, migrates off simple-name maps).

This is **not** unfinished Phase 1. Dual-emit is done. Walking `claude/10-architecture-maturation-plan.md` §0–1 or the JPA survey as an executable dump is forbidden by the Phase 1 memo.

---

## 2. Non-goals

- No full JPA / Hibernate predicate vocabulary dump.
- No Glean / SCIP / Kythe wire protocol or in-process index service.
- No packaging mega-PR, product SPI, or HttpLLM executor vehicle.
- No fold into L2/L2b capacity, L5 `drift_report` schema, or L6 coverage hygiene.
- No silent `schema_version` bump theater without a dual-read / migration story (`rel-schema-outlives-writers`).
- No inventing a mid-size capacity threshold as part of this ADR.

---

## 3. Current SoR (witness)

| Axis | Location |
|------|----------|
| Writer | `doc_engine.tools.spring_signal_scan` → `facts_from_signals` / `write_facts_jsonl` |
| Module | [`src/doc_engine/scanning/facts.py`](../../src/doc_engine/scanning/facts.py) |
| Contract | `Fact` / `FACTS_LEDGER_SCHEMA_VERSION = 1` in [`src/doc_engine/pipeline/artifacts.py`](../../src/doc_engine/pipeline/artifacts.py); `scripts/schemas/facts.schema.json` |
| Path A SoR | `spring_signals.json` (`entity_table_map` + evidence); facts are dual-emit sidecar, not cert-required |
| Schema memo | [facts-ledger-schema-2026-07-30.md](facts-ledger-schema-2026-07-30.md) |
| Prior art | [fact-store-prior-art-corpus-2026-07-30.md](fact-store-prior-art-corpus-2026-07-30.md), [fact-store-approaches-collation-2026-07-30.md](fact-store-approaches-collation-2026-07-30.md) |

---

## 4. Options

### A — FQCN (+ optional persistence unit) string tokens

`subject` / `object` become fully-qualified type names (and optional PU qualifier where multi-PU repos exist). Closest to maturation §1.1 backlog wording.

- **Pros:** Human-readable; matches Java mental model; enough to kill most simple-name collisions.
- **Cons:** Inner classes, Kotlin name mangling, and multi-module duplicates still need a rule; not a member-level symbol.

### B — SCIP-inspired opaque single-token symbol grammar

One string token per entity (type, and later method/field) with a documented local grammar inspired by SCIP/Glean — **not** a SCIP wire dependency.

- **Pros:** Extends to members without changing field shape; aligns with prior-art corpus.
- **Cons:** Heavier design; risk of inventing a private dialect nobody can debug; needs dual-read longer.

### C — Keep simple name + contested forever

Treat collisions as permanent multi-edge / contested status only.

- **Pros:** Zero migration cost.
- **Cons:** Rejects the L3 problem statement; docs and drift stay ambiguous on colliding names.

### D — Hybrid dual-read migration

Keep emitting simple-name `MAPS_TO` (and Path A map) while **also** emitting a new identity field or parallel predicate (e.g. `subject_symbol` qualifier, or additive `MAPS_TO` rows keyed by FQCN/symbol). Readers prefer symbol when present.

- **Pros:** Honors `rel-schema-outlives-writers`; Path A certification survives; matches Phase 1 “sidecar, don’t replace” discipline.
- **Cons:** Temporary dual identity; must define an end state and refuse forever-dual without a sunset note.

---

## 5. Compatibility / versioning

- Prefer **additive** identity (new qualifier or parallel facts) over in-place rewrite of `subject` for existing `MAPS_TO` rows.
- Any change to the closed eight-field contract that removes or reinterprets `subject` requires an explicit `FACTS_LEDGER_SCHEMA_VERSION` bump **and** a dual-read window — not a same-day cutover.
- Do not regenerate drift baselines to “absorb” identity churn (`rel-schema-outlives-writers`).
- Open `spring_signals` / closed facts coexistence (schema-contracts memo) remains: Path A map consumers must not silently break.

---

## 6. Consumers to name in any later code PR

- JPQL / lineage joins that key on class or table names.
- Drift tier-2 and any citation paths that quote fact subjects.
- Doc-writer / Stage-1 summaries that mention entity names (derived views — must not become a second SoR).
- `facts.jsonl` unit fixtures and schema export under `scripts/schemas/`.

---

## 7. Decision (this ADR)

| Question | Answer |
|----------|--------|
| Confirm maturation §1 as written? | **No** (Phase 1 memo REFINE stands) |
| Pivot away from facts SoR? | **No** |
| Proceed toward collision-safe symbols? | **Yes — research direction D then A** |

**Direction:** Plan a **hybrid dual-read (D)** landing pad whose *end-state identity* is **FQCN string tokens (A)** for type-level `MAPS_TO` / entity subjects. Revisit SCIP-like opaque grammar (B) only if member-level facts become a near-term requirement; do not invent B in the first code PR.

**C is rejected** as a standing answer to L3.

**Exit criteria for a later code PR (not this change):**

1. Written dual-read rules (what writers emit; what readers prefer; sunset condition).
2. Fixture with two same-simple-name types proving the new token distinguishes them.
3. Path A certification still green; facts validate-when-present unchanged in spirit.
4. No JPA vocabulary dump; no packaging/SPI fold.
5. STATUS/queue updated only after the code lands (or this ADR is superseded).

---

## 8. Sequencing

```text
L2b CLI measure (PR #74, main)
  → threshold default RETAIN 80000 (calibration research PR #75)
  → L3 ADR (this file)
  → later: L3 code PR (D→A) after exit criteria
  → L5 drift_report schema / L6 coverage hygiene (separate themes)
  → L4 branch protection (owner, deferred)
  → mid-size measured_stage4_inputs run (frontier; required only to change 80k)
```

Cite: `refactor-sequencing`, `claims-and-status-drift`, Phase 1 decision memo §3/§5.

---

## 9. See also

- [adoption-blockers-queue-2026-07-30.md](adoption-blockers-queue-2026-07-30.md) L3  
- [fact-store-phase1-decision-memo-2026-07-30.md](fact-store-phase1-decision-memo-2026-07-30.md)  
- [facts-ledger-schema-2026-07-30.md](facts-ledger-schema-2026-07-30.md)  
- CONSTRAINTS.md — contested resolved; FQCN backlog  
- `docs/design/ddia-north-star/domains/02-encoding-and-evolution/`
