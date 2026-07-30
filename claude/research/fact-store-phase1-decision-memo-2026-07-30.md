# Fact-store Phase 1 decision memo (2026-07-30)

> **Gate status (2026-07-30):** §3 dual-emit **landed** (PR #63 — `facts.jsonl` beside `spring_signals.json`). §5 research gate below is **closed**. Next engineering is the adoption-blockers queue (B1–B4 product; B5 stale-claims hygiene). Sections 1–4 remain the historical REFINE rationale.

**Verdict: REFINE** (not Confirm-as-written, not Pivot-away-from-facts).

DDIA 2e framing (Ch1 systems of record / derived data; Ch4/Ch13 materialized views) still applies. External prior art ([corpus](fact-store-prior-art-corpus-2026-07-30.md), [collation](fact-store-approaches-collation-2026-07-30.md)) **confirms** the thesis: durable facts + derivation beat flat evidence bags and unary maps. It does **not** confirm that [`../10-architecture-maturation-plan.md`](../10-architecture-maturation-plan.md) §0–1 or the JPA survey are executable specs for 2026-07 product state.

---

## 1. Staleness audit (principal concern)

### Maturation plan §0–1

| Piece | Keep? | Why |
|-------|-------|-----|
| §0 reframe: docs = views over fact SoR | **Yes — as hypothesis now externally reinforced** | Glean (facts→docs), RepoDoc (RepoKG), CodeWiki (graph→hierarchy), SCIP (multi-edge symbols) |
| §0 “no fact store today” | **Refine wording** | Still no *general* fact ledger; contested `entity_table_map` + Stage 0 JSON + cross-group edges are partial structure |
| Phase 0.1 PORTING / `local_ci.sh` / `_python-checks.yml` | **Discard as work** | Banner already says so; body still reads as deliverables |
| Path cites `scripts/spring_signal_scan.py` etc. | **Stale** | Product SoT is `src/doc_engine/tools/` |
| Scrap list / “mostly not started” | **Partially obsolete** | Packaging pause complete; scanners default `filesystem+ast-grep`; CodeQL opt-in; llms verifier deleted |
| Phase 1 sizing / “twenty findings → three classes” | **Keep classes; re-estimate size** | Contested map already ate some H1; dual-emit slice should be thin |

### JPA / Hibernate predicate vocabulary survey

| Piece | Keep? | Why |
|-------|-------|-----|
| Effect categories + row-visibility predicates | **Yes** | Still the right vocabulary when we mint predicates |
| EDB vs IDB / `not-a-base-table` / contested | **Yes** | Aligns with Glean/CodeQL and our contested sentinel |
| Integration-cost / Phase 1 sizing hooks into maturation plan | **Re-open** | Sized against pre-kernel tree and full vocabulary dump; do **not** implement the whole catalog in Phase 1 |
| Implicit “CodeQL-class derive everywhere” | **Refine** | Default path stays source-text; CodeQL remains opt-in enrichment |

**Rule for engineers:** Do not implement Phase 1 by walking the maturation plan top-to-bottom. Implement against **this memo’s slice**, then rewrite maturation §1 to match.

---

## 2. What prior art locks in

1. **Multi-edge / append facts beat unary LWW** — SCIP `Relationship`; Glean immutable facts; our contested map is the right *direction*, wrong *scope* if it stays the only arity fix.
2. **EDB (scan) vs IDB (derive)** — Glean/CodeQL/jQAssistant; survey’s base vs derived split stays.
3. **Portable default vs compile-opt-in** — Kythe/ArchUnit/jQAssistant are fidelity forks, not replacements for Stage 0 default.
4. **File-backed ledger, not Neo4j/Glean-in-process** — operator pilot and PE adoption need openable artifacts.
5. **Fan-out is a view problem** — RepoDoc incremental impact is Phase 2+; Phase 1 enables shared facts so later stages stop re-deriving from bags.

---

## 3. Phase 1 slice (after this memo — still gated on explicit “build” ask)

**Goal:** Thin dual-emit fact ledger beside existing Stage 0 JSON, without breaking Path A certification.

| Deliver | Do not deliver yet |
|---------|-------------------|
| `facts.jsonl` (or equivalent) of typed records: `{predicate, subject, object?, qualifiers?, file, line, rule_id, scanner}` | Full JPA survey catalog |
| Emit existing evidence rows + `entity_table_map` / contested outcomes as facts | Replace all maps in one PR |
| One derived pass stub (e.g. `not-a-base-table` or contested→`MAPS_TO` multi) with tests | Angle/Datalog engine |
| Schema doc + golden fixture under `tests/` | SCIP/Glean wire format |
| Update maturation §1 banner to “Phase 1 = dual-emit per memo” | Fan-out rewrite; Neo4j; ArchUnit default |

**Success criteria:** Path A on a known fixture still certifies; new facts file round-trips in a unit test; contested entity produces ≥2 `MAPS_TO` (or equivalent) facts rather than silent overwrite.

---

## 4. Confirm / Refine / Pivot summary

| Option | Chosen? | Meaning |
|--------|---------|---------|
| **Confirm** | No | Would mean “execute maturation §1 as written” — **rejected** because §0–1 planning text is outdated |
| **Refine** | **Yes** | Keep DDIA/fact-store thesis; rewrite Phase 1 as thin dual-emit; treat survey as vocab backlog; refresh maturation banners/paths |
| **Pivot** | No | Would mean abandon fact SoR (e.g. fan-out-only or RAG-only) — **rejected**; prior art strengthens facts-first |

---

## 5. Gate

**Closed (2026-07-30).** §3 dual-emit shipped in PR #63 (`facts.jsonl`, contested multi-`MAPS_TO`, emit counters). This memo is no longer a start gate for emitter work.

**Next engineering:** [`adoption-blockers-queue-2026-07-30.md`](adoption-blockers-queue-2026-07-30.md) — B1–B4 product wiring; B5 current-state claim hygiene (do not mix with dual-emit history).

Parallel non-code: branch protection (`CONSTRAINTS.md` enterprise item 6) remains allowed anytime.

---

## Sources (primary)

- SCIP docs / Relationship: https://scip-code.org/docs.html  
- Glean introduction: https://glean.software/docs/introduction/  
- Kythe overview: https://kythe.io/docs/kythe-overview.html  
- RepoDoc: https://arxiv.org/abs/2604.26523  
- CodeWiki: https://arxiv.org/abs/2510.24428  
- In-repo: contested map work (session-log 2026-07-27); product architecture / Stage 0 scanner defaults  
