# ADR — Claim-symbol / entity identity (L3)

**Date:** 2026-07-30  
**Status:** Proposed (research only — **no code in this change**)  
**Queue:** L3 — Claim-symbol single-token entities  
**DDIA:** domain `02-encoding-and-evolution`; `schema-evolution-and-data-outlives-code`, `encoding-and-compatibility`, `rel-schema-outlives-writers`; SoR vs derived in domain `01`  
**Depends on:** Phase 1 dual-emit lock ([fact-store-phase1-decision-memo-2026-07-30.md](fact-store-phase1-decision-memo-2026-07-30.md)); L2b measurement on `main` (PR #74); L2b threshold **default retained at 80000** after calibration research ([l2b-stage4-threshold-calibration-2026-07-30.md](l2b-stage4-threshold-calibration-2026-07-30.md), PR #75/#77) — mid-size run still required to *change* 80k, not to author this ADR

**Decision (amended 2026-07-30):** canonical type-level identity is **FQCN (A)**. Dual-read (D) is **not** the architecture — at most a short compatibility note for stale on-disk `schema_version=1` files, not a standing dual-identity design.

---

## 1. Problem

Phase 1 ships a thin `facts.jsonl` ledger (`FACTS_LEDGER_SCHEMA_VERSION = 1`) beside `spring_signals.json`. Entity identity in that ledger is **not** collision-safe:

| Fact kind | Today’s `subject` | Failure mode |
|-----------|-------------------|--------------|
| Evidence | File path | Fine as a locator; not an addressable *type* / *member* entity |
| `MAPS_TO` | **Simple class name** | Two packages can share `User`; contested multi-edge does not fix the key |
| Qualifiers | Status / table_name_source | Carry provenance, not identity |

CONSTRAINTS already separates **resolved contested multi-`MAPS_TO`** from the **FQCN / fact-tuple backlog**. L3 is that backlog: how entities become **single-token, stable claim-symbols** in the facts SoR.

This is **not** unfinished Phase 1. Dual-emit is done. Walking `claude/10-architecture-maturation-plan.md` §0–1 or the JPA survey as an executable dump is forbidden by the Phase 1 memo.

**Important shape of the SoR:** `facts.jsonl` is a **scan-time projection** of `spring_signals.json`, rewritten on every `spring_signal_scan` run. It is not a durable append-only store whose old subject strings must be dual-read forever. That fact changes the migration story (see §5).

---

## 2. Non-goals

- No full JPA / Hibernate predicate vocabulary dump.
- No Glean / SCIP / Kythe wire protocol or in-process index service (borrowing *ideas* from SCIP symbol grammar is fine; shipping SCIP is not).
- No packaging mega-PR, product SPI, or HttpLLM executor vehicle.
- No fold into L2/L2b capacity, L5 `drift_report` schema, or L6 coverage hygiene.
- No inventing a mid-size capacity threshold as part of this ADR.
- No standing **dual-identity** design (two live keys for the same `MAPS_TO` fact) as the answer to L3 — that confuses migration with identity.
- No silently breaking Path A `entity_table_map` consumers in the first L3 code PR (Path A identity may stay simple-name until a *separate* Path A evolution).

---

## 3. Current SoR (witness)

| Axis | Location |
|------|----------|
| Writer | `doc_engine.tools.spring_signal_scan` → `facts_from_signals` / `write_facts_jsonl` |
| Module | [`src/doc_engine/scanning/facts.py`](../../src/doc_engine/scanning/facts.py) |
| Contract | `Fact` / `FACTS_LEDGER_SCHEMA_VERSION = 1` in [`src/doc_engine/pipeline/artifacts.py`](../../src/doc_engine/pipeline/artifacts.py); `scripts/schemas/facts.schema.json` |
| Path A SoR | `spring_signals.json` (`entity_table_map` + evidence); facts are dual-emit sidecar, not cert-required |
| Merge key today | `_merge_signals.py` — keyed by **simple class name alone** (documented collision) |
| Schema memo | [facts-ledger-schema-2026-07-30.md](facts-ledger-schema-2026-07-30.md) |
| Prior art | [fact-store-prior-art-corpus-2026-07-30.md](fact-store-prior-art-corpus-2026-07-30.md), [fact-store-approaches-collation-2026-07-30.md](fact-store-approaches-collation-2026-07-30.md) |

---

## 4. Research basis (why FQCN, not dual-read)

### 4.1 Java / JPA mental model

In Java, a type’s stable address is its **binary / fully-qualified name** (`com.acme.billing.User`), not the simple name. Contested multi-`MAPS_TO` already admits package-level collision; the backlog wording in CONSTRAINTS is FQCN for that reason. Optional persistence-unit (PU) qualification remains for multi-PU repos — as a **qualifier**, not a second subject namespace.

### 4.2 Index-symbol prior art (ideas only)

[SCIP](https://scip-code.org/docs.html) (and SemanticDB before it) centers identity on a **human-readable fully-qualified symbol string**, with a separate `display_name` for UI. Descriptors form a unique name across the package. That is the opposite of “keep the ambiguous key and dual-read a better one.”

L3 borrows that *principle* (canonical string = FQN; simple name = display / Path A convenience), **not** SCIP’s wire format, package-manager tuple, or indexer service. Option B (local SCIP-like grammar) stays available later if we need member-level facts without inventing a private dialect prematurely.

### 4.3 Why dual-read fails as the long-term answer

| Claim | Reality here |
|-------|----------------|
| Dual-read protects durable rows | Facts are **regenerated each scan** from signals |
| Dual-read is the identity model | It is a **temporary compatibility tactic** from DDIA `rel-schema-outlives-writers`, not a key design |
| Forever dual honors Path A | Path A coexistence means **open signals map can lag** closed facts — not that facts themselves keep two subjects |

Elevating D→A made migration the product. The product is **one collision-safe subject token**.

---

## 5. Options

### A — FQCN (+ optional PU qualifier) string tokens — **chosen**

`MAPS_TO.subject` becomes the fully-qualified type name. Optional PU lives in `qualifiers` when multi-PU identity matters. Simple name may appear as a **non-key** display qualifier if consumers need it.

- **Pros:** Matches Java; kills package collisions; readable in diffs and docs; aligns with SCIP/SemanticDB “FQN as symbol” without a wire dependency; matches CONSTRAINTS backlog wording.
- **Cons:** Inner classes / Kotlin mangling need an explicit rule in the code PR; not member-level; writers must obtain package context from the scan (today merge keys only the simple name).

### B — SCIP-inspired opaque single-token symbol grammar — **deferred**

Documented local grammar for type *and later* method/field symbols — still not a SCIP wire dependency.

- **Pros:** Extends to members without reshaping the eight-field contract.
- **Cons:** Heavier; dialect risk. Revisit only when member-level facts are a near-term requirement.

### C — Keep simple name + contested forever — **rejected**

Rejects the L3 problem statement.

### D — Hybrid dual-read migration — **rejected as architecture**

Emitting both simple-name and FQCN subjects (or parallel predicates) with “readers prefer symbol” as the standing design.

- Allowed only as a **short, dated compatibility window** for stale on-disk `schema_version=1` artifacts if a real external consumer requires it.
- **Not** the research direction, **not** the end-state, **not** an excuse for forever-dual without a sunset.
- Preferred cutover for this repo: bump `FACTS_LEDGER_SCHEMA_VERSION`, emit FQCN subjects on the next scan, update fixtures — because the ledger is regenerated.

---

## 6. Compatibility / versioning

1. **Bump** `FACTS_LEDGER_SCHEMA_VERSION` when `MAPS_TO.subject` meaning changes from simple name → FQCN (reinterpretation of the same field name counts as a breaking semantic change).
2. **Regenerate** unit fixtures and any committed sample `facts.jsonl` in the same code PR — do not “absorb” identity churn into drift baselines (`rel-schema-outlives-writers`).
3. **Path A:** leave `entity_table_map` simple-name-keyed until a separate Path A identity change; facts may become FQCN-keyed while Path A cert stays green (open/closed coexistence from the schema-contracts memo). Do not fold Path A FQCN into the first L3 facts PR unless exit criteria still hold.
4. **Stale files:** validators may reject or warn on `schema_version < N` rather than dual-reading two subject namespaces indefinitely.
5. Citation `claim_symbols()` single-token gap (principal review §2.5) is **related product pain**, not this ADR’s SoR decision — do not conflate regex widening with fact-subject identity.

---

## 7. Consumers to name in any later code PR

- `facts_from_signals` / merge path — must carry package (or equivalent) into `MAPS_TO.subject`.
- JPQL / lineage joins that key on class or table names.
- Drift tier-2 and any citation paths that quote fact subjects.
- Doc-writer / Stage-1 summaries that mention entity names (derived views — must not become a second SoR).
- `facts.jsonl` unit fixtures and schema export under `scripts/schemas/`.

---

## 8. Decision (this ADR)

| Question | Answer |
|----------|--------|
| Confirm maturation §1 as written? | **No** (Phase 1 memo REFINE stands) |
| Pivot away from facts SoR? | **No** |
| Canonical type-level identity? | **FQCN string tokens (A)** |
| Standing dual-read (D)? | **No** — rejected as architecture |
| SCIP-like grammar (B)? | **Deferred** until member-level facts are near-term |
| Simple name + contested only (C)? | **Rejected** |

**Direction:** Implement **A** as the long-term facts SoR identity for type-level `MAPS_TO` / entity subjects. Migration is a **versioned cutover** of a regenerated ledger (plus Path A lag), not a dual-identity landing pad.

**Exit criteria for a later code PR (not this change):**

1. Written subject rule: FQCN form; inner-class / missing-package behavior; optional PU qualifier policy.
2. Fixture with two same-simple-name types in different packages proving subjects differ.
3. `FACTS_LEDGER_SCHEMA_VERSION` bumped; fixtures/schema export updated; no forever-dual subject namespace.
4. Path A certification still green; facts validate-when-present unchanged in spirit.
5. No JPA vocabulary dump; no packaging/SPI fold; no fold into L5/L6.
6. STATUS/queue updated only after the code lands (or this ADR is superseded).

---

## 9. Sequencing

```text
L2b CLI measure (PR #74, main)
  → threshold default RETAIN 80000 (calibration research PR #75/#77)
  → L3 ADR (this file) — decision A (FQCN)
  → later: L3 code PR (FQCN subjects + schema bump) after exit criteria
  → L5 drift_report schema / L6 coverage hygiene (separate themes)
  → L4 branch protection (owner, deferred)
  → mid-size measured_stage4_inputs run (frontier; required only to change 80k)
```

Cite: `refactor-sequencing`, `claims-and-status-drift`, Phase 1 decision memo §3/§5.

---

## 10. See also

- [adoption-blockers-queue-2026-07-30.md](adoption-blockers-queue-2026-07-30.md) L3  
- [fact-store-phase1-decision-memo-2026-07-30.md](fact-store-phase1-decision-memo-2026-07-30.md)  
- [facts-ledger-schema-2026-07-30.md](facts-ledger-schema-2026-07-30.md)  
- CONSTRAINTS.md — contested resolved; FQCN backlog  
- SCIP protocol reference — FQN symbol + `display_name` (ideas only): https://scip-code.org/docs.html  
- `docs/design/ddia-north-star/domains/02-encoding-and-evolution/`
