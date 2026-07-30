# Fact-store prior-art corpus (2026-07-30)

Bounded Pre–Phase 1 research spike. Method: [`../steering-prompts/00-shared-research-standards.md`](../steering-prompts/00-shared-research-standards.md) (arXiv mechanism fit; GitHub stars + push recency; DeepWiki as orientation only). Traversal protocol: [`../steering-prompts/11-context-traversal-protocol.md`](../steering-prompts/11-context-traversal-protocol.md).

> **Post–dual-emit (2026-07-30):** Phase 1 file-backed ledger shipped (`facts.jsonl`, PR #63). Rows below remain **mechanism cites** (Glean EDB/IDB, SCIP multi-edge, etc.) — do not re-measure stars/pushes for product decisions; copy the model, not the deployment.

**Outbound queries** used only generic terms (code intelligence, fact index, documentation knowledge graph). No customer-service identifiers.

**Trust bar (primary):** ≥2 of {adoption ≥~500 stars *or* clear org production use; push within ~18 months; domain fit; primary design docs}. Stars/pushes measured via `gh api` on 2026-07-30 unless noted.

---

## In-repo documents — staleness notice (read first)

These are **not** discarded, but they are **not current-state product docs**:

| Document | Still useful as | Known stale relative to 2026-07 packaging / portable kernel |
|----------|-----------------|---------------------------------------------------------------|
| [`../10-architecture-maturation-plan.md`](../10-architecture-maturation-plan.md) §0 thesis (facts as SoR, docs as views) | Architectural hypothesis under test | Phase 0.1 PORTING/`local_ci.sh` never landed; body still cites `scripts/spring_signal_scan.py`; scrap list items partially done (`verify_llms_docs` deleted; contested sentinel partial); “locked next = Phase 1 as written” predates dual-home deletion, suite SoT, default scanners `filesystem+ast-grep` |
| [`../jpa-hibernate-predicate-vocabulary-survey.md`](../jpa-hibernate-predicate-vocabulary-survey.md) | Predicate vocabulary / derived-pass obligations | Sized against pre-portable layout; still assumes Phase 1 timeline that needs re-estimate; does not know CodeQL is *opt-in* vs default |
| [`source-text-vs-bytecode-analysis.md`](source-text-vs-bytecode-analysis.md) | Source vs bytecode tradeoff | Path cites `scripts/spring_signal_scan.py`; product tools now under `src/doc_engine/` |
| Contested `entity_table_map` work (session-log 2026-07-27) | Partial H1 mitigation already shipped | Full n-ary key still open — survey/plan still talk as if map is untouched |

**Implication for this spike:** treat §0–1 and the JPA survey as **partially obsolete planning text carrying a still-plausible thesis**, not as executable specs. The decision memo must say what to keep vs rewrite before any Phase 1 code.

---

## Primary corpus (≥8)

### P1 — SCIP (`scip-code/scip`, Sourcegraph lineage)

| Heuristic | Value |
|-----------|--------|
| Stars / push | **708** / 2026-07-21 (primary: adoption + recency + domain + docs) |
| Primary docs | https://scip-code.org/docs.html ; `scip.proto` |
| Evidence tier | **Primary-confirmed** — Relationship + SymbolInformation opened |

**SoR shape:** Index → Documents → Occurrences + SymbolInformation; `Relationship { symbol, is_reference, is_implementation, is_type_definition, is_definition }` — multi-flag edges between symbols (n-ary-ish: subject symbol + object symbol + role flags). Explicitly designed so unary “one definition wins” is insufficient for languages with mixins/multiple definitions (`is_definition` override).

**Fit:** Strong template for *exportable* fact/relationship records without requiring Neo4j. Does not encode JPA table mappings; we would layer domain predicates on top.

### P2 — Glean (`facebookincubator/Glean`)

| Heuristic | Value |
|-----------|--------|
| Stars / push | **1375** / 2026-07-29 (Meta production + adoption + recency + docs) |
| Primary docs | https://glean.software/docs/introduction/ ; Meta eng blog 2024-12-19 |
| Evidence tier | **Primary-confirmed** — introduction + product pages |

**SoR shape:** Typed immutable **facts** in user schemas; DAG; RocksDB; **Angle** derives facts (Datalog-like; OSS Angle currently non-recursive). Explicit EDB/IDB split: raw indexer facts vs derived predicates; language-specific schemas + derived language-neutral layers (`codemarkup`). Used at Meta for navigation **and documentation generation**.

**Fit:** Closest industry twin to maturation §1 (facts + derivation). **Ops cost high** (server, Thrift, RocksDB) — copy the *model*, not the deployment, under our no-compile portable constraint.

### P3 — Kythe (`kythe/kythe`)

| Heuristic | Value |
|-----------|--------|
| Stars / push | **2143** / 2026-07-16 (Google + adoption + recency + schema docs) |
| Primary docs | https://kythe.io/docs/kythe-overview.html |
| Evidence tier | **Primary-confirmed** |

**SoR shape:** Language-agnostic **graph** of nodes/edges (VName + facts); extractors consume **compilation units** (`.kzip`); indexers emit entry streams. Liberal extensible schema.

**Fit:** Confirms graph SoR + schema extensibility. **Requires compile/extract pipeline** — conflicts with default no-build Stage 0 unless opt-in (same fork as ArchUnit / CodeQL-with-build).

### P4 — CodeQL (`github/codeql` + CLI binaries)

| Heuristic | Value |
|-----------|--------|
| Stars / push | **9886** (libraries) / active 2026-07-29; CLI binaries **993** stars |
| Primary docs | CodeQL docs / QL language |
| Evidence tier | **Primary-confirmed** for product use in this repo (opt-in scanner already exists) |

**SoR shape:** Relational/Datalog evaluation over extracted DB; predicates as queries; databases built from builds or language extractors.

**Fit:** Already an **opt-in** Stage 0 backend here (`--scanners filesystem,codeql`). Not the default (`filesystem,ast-grep`). Teaches: rich predicates want a real store; default path must stay source-text portable.

### P5 — ArchUnit (`TNG/ArchUnit`)

| Heuristic | Value |
|-----------|--------|
| Stars / push | **3786** / 2026-07-29 |
| Primary docs | ArchUnit user guide; in-repo note [`source-text-vs-bytecode-analysis.md`](source-text-vs-bytecode-analysis.md) |
| Evidence tier | **Primary-confirmed** (docs + prior in-repo research) |

**SoR shape:** In-memory `JavaClass` model from bytecode; rules as checks, not durable fact export.

**Fit:** Precision upgrade path; **compile required**. Reinforces dual-backend strategy (default source-text facts; optional bytecode enrichment) rather than replacing Stage 0 wholesale.

### P6 — jQAssistant (`jQAssistant/jqassistant` + Spring plugin)

| Heuristic | Value |
|-----------|--------|
| Stars / push | **284** stars (below 500) but **org product** + push 2026-07-16 + Spring plugin + Neo4j docs → primary on org-use + domain + docs |
| Primary docs | https://jqassistant.github.io/jqassistant/current/ |
| Evidence tier | **Primary-confirmed** (manual + prior research table) |

**SoR shape:** Property graph (Neo4j); concepts/constraints as Cypher; Spring plugin encodes framework structure as labeled graph.

**Fit:** Spring-aware graph constraints are on-point for `authorization.md` / component rules. **Neo4j + typically Maven/build integration** — optional CI-gated path, not portable default.

### P7 — RepoDoc (arXiv:2604.26523 + `SYSUSELab/RepoDoc`)

| Heuristic | Value |
|-----------|--------|
| Paper | https://arxiv.org/abs/2604.26523 — **mechanism confirmed** (RepoKG → cluster → agent docs; bidirectional impact for incremental regen) |
| GitHub | **14** stars / push 2026-04-02 — **secondary as repo**, **primary as paper** |
| Evidence tier | Paper **primary-confirmed** via abs/html; repo low adoption |

**SoR shape:** Repository knowledge graph as semantic foundation for *entire* doc lifecycle; selective regeneration via graph impact — directly attacks our Path B fan-out / full regen cost.

**Fit:** Strong evidence that **graph/facts first, LLM second** is current SOTA framing for doc systems—not flat chunk RAG.

### P8 — CodeWiki (arXiv:2510.24428)

| Heuristic | Value |
|-----------|--------|
| Paper | https://arxiv.org/abs/2510.24428 — static dependency graph via Tree-sitter; hierarchical module tree; bottom-up agent docs |
| Evidence tier | **Primary-confirmed** (abs/html) |

**SoR shape:** Unified `depends_on` over calls/inheritance/imports; recursive partitioning by interdependency (not only token budgets).

**Fit:** Validates AST/source-text graphs without compile; suggests our `partition_repo` token slicing is weaker than dependency-aware clustering for doc quality (research signal, not immediate rewrite mandate).

### P9 — FActScore (arXiv:2305.14251) — already adopted by this project

| Heuristic | Value |
|-----------|--------|
| Cited in `00-shared-research-standards.md` for claim-tagging | Primary for **provenance of atomic claims**, not code SoR |
| Evidence tier | **Primary-confirmed** (project prior verification bar) |

**Fit:** Supports evidenced/confirmed/unknown as first-class; contested is a natural fourth value (maturation plan) — aligns with Glean “don’t overwrite conflicting facts.”

---

## Secondary corpus (cite lightly)

| Candidate | Why secondary |
|-----------|----------------|
| `code-graph-builder` (PyPI/Kuzu + embeddings) | Domain fit; not org-scale trust bar verified in this pass |
| `codebase-cortex` | Diff-driven doc agents + FAISS; useful incremental idea; adoption unverified here |
| LSIF (Microsoft LSP ecosystem) | Superseded directionally by SCIP for many tools; historical |
| RepoDoc GitHub (14★) | Paper primary; repo not trusted by star heuristic |

---

## Coverage vs research questions

| Question | Covered by |
|----------|------------|
| SoR shapes | P1–P6, P7 paper |
| Indexing / retrieval | P1–P4, P7–P8 |
| Traversal / fan-out reduction | P7 incremental impact; P8 dependency partition; P2 derivation |
| Unary / LWW failure modes | P1 `is_definition` / multi-def; P2 append+derive; our contested map work |
| Consequence | → decision memo |

**Saturation note:** Eight+ primary rows reached. Stopping per spike hard-stop (no extra lap).
