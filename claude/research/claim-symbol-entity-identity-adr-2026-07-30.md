# ADR — Claim-symbol / entity identity (L3)

**Date:** 2026-07-30  
**Status:** Accepted / implemented (L3 code — principal-complete B)  
**Queue:** L3 — Claim-symbol single-token entities  
**Normative grammar:** [`claim-symbol-grammar-2026-07-30.md`](claim-symbol-grammar-2026-07-30.md)  
**DDIA:** domain `02-encoding-and-evolution`; `schema-evolution-and-data-outlives-code`, `encoding-and-compatibility`, `rel-schema-outlives-writers`; SoR vs derived in domain `01`  
**Depends on:** Phase 1 dual-emit lock ([fact-store-phase1-decision-memo-2026-07-30.md](fact-store-phase1-decision-memo-2026-07-30.md)); L2b on `main` (PR #74); threshold **retain 80000** ([l2b-stage4-threshold-calibration-2026-07-30.md](l2b-stage4-threshold-calibration-2026-07-30.md), PR #75/#77)

**Decision:** **Principal-complete SCIP-inspired symbol architecture (B)** as the facts SoR identity. First code PR: complete grammar + `format`/`parse`/`display` module + type-level `MAPS_TO` emission. Prefer a slightly bolder first cut when incremental risk is small and it clearly advances the project (see §5). Dual-read (D) and forever-simple-name (C) rejected. Bare FQCN (A) is display/join aid, not the machine key.

---

## 1. Problem

Phase 1 `facts.jsonl` (`FACTS_LEDGER_SCHEMA_VERSION = 1`) keys `MAPS_TO` on **simple class name**. Contested multi-edge admits collisions; it does not fix the key. CONSTRAINTS already separates that partial fix from the **FQCN / fact-tuple / symbol backlog**. L3 is that backlog.

This is **not** unfinished Phase 1. Dual-emit is done. No maturation §0–1 / JPA survey dump.

**SoR shape:** facts are a **scan-time projection** of `spring_signals.json` — regenerated each run. Migration is a versioned cutover, not forever dual-read.

---

## 2. Non-goals

- No full JPA / Hibernate predicate vocabulary dump.
- No SCIP / Glean / Kythe **wire protocol** or index service (copy the symbol *model*; do not ship protobuf Stage 0).
- No packaging mega-PR, product SPI, or HttpLLM vehicle.
- No fold into L2/L2b, L5 `drift_report`, or L6 coverage hygiene.
- No standing dual-identity (simple name *and* symbol as live SoR keys).
- No silently breaking Path A `entity_table_map` in the first L3 PR (Path A may lag).
- No inventing mid-size capacity numbers here.

---

## 3. Current SoR (witness)

| Axis | Location |
|------|----------|
| Writer | `spring_signal_scan` → `facts_from_signals` / `write_facts_jsonl` |
| Module | [`src/doc_engine/scanning/facts.py`](../../src/doc_engine/scanning/facts.py) |
| Contract | `Fact` / `FACTS_LEDGER_SCHEMA_VERSION` in [`artifacts.py`](../../src/doc_engine/pipeline/artifacts.py); `scripts/schemas/facts.schema.json` |
| Path A | `entity_table_map` simple-name keys; facts sidecar, not cert-required |
| Merge | `_merge_signals.py` — simple name only (documented collision) |
| Prior art | [fact-store-prior-art-corpus-2026-07-30.md](fact-store-prior-art-corpus-2026-07-30.md) **P1 SCIP**; collation memo |

---

## 4. Research basis

**SCIP / SemanticDB principle:** one parseable symbol string; `display_name` for humans; descriptors grow type → field → method without changing the field that holds identity.

**Why not stop at bare FQCN (A):** solves today’s `User` collision; does not lock an extension point. Later member facts either half-invent a grammar inside FQCN strings or force a **second** identity migration.

**Why not “vague thin B”:** under-specified dialects become three spellings of the same type. Principal bar = **complete architecture**, narrow first *production emit*.

**Why not full SCIP wire:** fights portable source-text Stage 0; prior-art corpus says copy the model, not the deployment.

---

## 5. Posture: complete architecture, calculated forward risk

Ship like a principal engineer who is allowed to move:

| Must be complete in the first code PR | May be bold if risk is small | Do not boil the ocean |
|----------------------------------------|------------------------------|------------------------|
| Normative grammar: type, inner type, field, method forms; escaping; illegal tokens | Round-trip **tests** for field/method shapes even before any member row exists | SCIP protobuf / indexer service |
| Sole writer API: `format` / `parse` / `display` (no ad hoc concat in `facts.py`) | Optional `qualifiers.symbol_kind` (`type` now) | Emitting speculative member **facts** with no predicate/consumer |
| Type `MAPS_TO.subject` = symbol; required `display_name` + `fqcn` | Slightly richer Path A sidecar fields *only if* cert stays green and scope stays identity | JPA vocabulary dump / packaging fold |
| `FACTS_LEDGER_SCHEMA_VERSION` bump; collision fixture (two-package `User`) | Grammar `version` constant beside ledger version | Forever dual-read of simple name + symbol |
| Reject/warn stale schema rather than dual-read | Document Path A FQCN/symbol follow-on as next identity slice | Fake package-manager/version precision |

**Risk rule:** prefer the bolder option when (1) incremental engineering cost is modest vs type-only emit, (2) it prevents a foreseeable second migration, and (3) it does not invent SoR rows nobody reads. Round-trip tests for reserved descriptors clear that bar; inventing `MAPS_TO` for fields without a column predicate does not.

---

## 6. Options

### A — FQCN-only SoR key — **rejected as machine identity**

Keep as **required display/join aid** (`qualifiers.fqcn`).

### B — SCIP-inspired symbol architecture — **chosen**

Illustrative form (normative text: [`claim-symbol-grammar-2026-07-30.md`](claim-symbol-grammar-2026-07-30.md)):

```text
doc-engine spring . <namespace>/(<namespace>/)*<TypeName>#
doc-engine spring . <namespace>/(<namespace>/)*<TypeName>#<field>.
doc-engine spring . <namespace>/(<namespace>/)*<TypeName>#<method>().
```

| Entity | Symbol | Display |
|--------|--------|---------|
| `com.acme.billing.User` | `doc-engine spring . com/acme/billing/User#` | `User` |
| `com.acme.auth.User` | `doc-engine spring . com/acme/auth/User#` | `User` |
| Later field | `…/User#email.` | `User.email` |

Placeholders for manager/version (`.`) until real module coordinates exist — document as placeholders, do not pretend precision.

### C — Simple name + contested forever — **rejected**

### D — Hybrid dual-read — **rejected as architecture**

---

## 7. Impact over time

### Near term (first L3 code PR)

- **Workflow:** scan → package resolve → `symbol.format` → validate → write facts; CI holds grammar round-trips.
- **Content:** machine `subject` = symbol; humans see `display_name` / `fqcn` in qualifiers and derived views.
- **Data:** one ledger schema bump; collision-safe type keys; contested = mapping ambiguity, not identity ambiguity. Path A may still be simple-name-keyed.

### Medium term (first real member predicate)

- **Workflow:** same API, new descriptor kind in emitters that have a real consumer.
- **Content:** new fact kinds; **type symbols unchanged**.
- **Data:** additive rows; avoid subject rekeys for existing types.

### Long term

- **Workflow:** drift / lineage / machine citation ids join on symbols.
- **Content:** markdown stays prose; symbols stay in ledgers unless a citation path deliberately quotes them.
- **Data:** one identity namespace for the facts SoR lifetime — the payoff for designing B completely once.

---

## 8. Compatibility / versioning

1. Bump `FACTS_LEDGER_SCHEMA_VERSION` when `MAPS_TO.subject` meaning changes.
2. Regenerate fixtures in the same PR; do not absorb identity churn into drift baselines (`rel-schema-outlives-writers`).
3. Path A may lag until a separate identity slice.
4. Validators reject illegal symbols and stale schema versions rather than dual-reading two namespaces.
5. `claim_symbols()` single-token prose gap remains related product pain — not solved by picking B alone.

---

## 9. Consumers to name in the code PR

- New in-repo symbol module (format/parse/display + tests).
- `facts_from_signals` / merge — package → type symbol.
- JPQL / lineage / drift tier-2 / doc-writer derived views.
- Fixtures + `scripts/schemas/` export.

---

## 10. Decision

| Question | Answer |
|----------|--------|
| Maturation §1 as written? | **No** (Phase 1 REFINE) |
| Facts SoR? | **Yes** |
| Machine identity? | **Complete SCIP-inspired symbol architecture (B)** |
| FQCN (A)? | Display/`fqcn` qualifier only |
| Dual-read (D) / simple-forever (C)? | **Rejected** |
| First PR emit? | Type-level `MAPS_TO` + complete grammar/API/tests |
| Calculated risk? | **Allowed** when modest cost prevents second migration and does not invent unread SoR |

**Exit criteria (later code PR):**

1. Normative grammar (types, inner types, fields, methods, escaping, placeholders) + grammar/ledger versioning.
2. Sole `format`/`parse`/`display` module; round-trip tests including reserved member shapes.
3. Type `MAPS_TO` uses symbols; `display_name` + `fqcn` required; two-package collision fixture green.
4. Schema bump; fixtures/schema export updated; no forever-dual SoR keys; no SCIP wire.
5. Path A cert green; facts validate-when-present unchanged in spirit.
6. No JPA dump; no packaging/SPI; no L5/L6 fold.
7. STATUS/queue move only after code lands (or this ADR is superseded).

---

## 11. Sequencing

```text
L2b measure + retain 80000 (PR #74/#75/#77)
  → L3 ADR (this file) — principal-complete B
  → L3 code PR (grammar + symbol API + type MAPS_TO + schema bump)
  → member rows only when a real predicate/consumer exists
  → L5 / L6 separate; L4 owner-deferred
```

---

## 12. See also

- [claim-symbol-grammar-2026-07-30.md](claim-symbol-grammar-2026-07-30.md)  
- [adoption-blockers-queue-2026-07-30.md](adoption-blockers-queue-2026-07-30.md) L3  
- [fact-store-phase1-decision-memo-2026-07-30.md](fact-store-phase1-decision-memo-2026-07-30.md)  
- [facts-ledger-schema-2026-07-30.md](facts-ledger-schema-2026-07-30.md)  
- [fact-store-prior-art-corpus-2026-07-30.md](fact-store-prior-art-corpus-2026-07-30.md) P1  
- CONSTRAINTS.md — contested resolved; symbol/FQCN backlog  
- https://scip-code.org/docs.html (ideas only)  
- `docs/design/ddia-north-star/domains/02-encoding-and-evolution/`
