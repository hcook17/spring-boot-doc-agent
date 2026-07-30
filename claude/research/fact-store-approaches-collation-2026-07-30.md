# Fact-store approaches collation (2026-07-30)

Companion to [`fact-store-prior-art-corpus-2026-07-30.md`](fact-store-prior-art-corpus-2026-07-30.md). Semantic DFS/BFS against **primary** docs only (not DeepWiki prose). Protocol: [`../steering-prompts/11-context-traversal-protocol.md`](../steering-prompts/11-context-traversal-protocol.md).

> **Post–dual-emit (2026-07-30):** Thin `facts.jsonl` ledger shipped (PR #63). Matrix still useful for “don’t stand up Glean/Neo4j as product SoR”; Current Stage 0 row is partially superseded by dual-emit beside the evidence bag.

**Anchor nodes:** SCIP Relationship/SymbolInformation; Glean “facts + Angle”; Kythe graph overview; CodeWiki/RepoDoc paper abstracts; this product’s Stage 0 JSON (`evidence` bag + maps) and contested `entity_table_map` behavior.

---

## Matrix

| Approach | SoR unit | Edge / predicate model | Query / derive | Default needs compile? | Doc-pipeline use | Fit for *this* product (portable default) | Cost / ops |
|----------|----------|------------------------|----------------|------------------------|------------------|-------------------------------------------|------------|
| **Current Stage 0** (`doc_engine` signal scan + maps) | Flat evidence rows + unary maps | Mostly unary (`entity→table`); contested sentinel when conflict | Imperative Python validators / LLM reads JSON | **No** (ast-grep/fs default) | Feeds all 14 views directly | Baseline: works; **LWW/unary is the known ceiling** | Low |
| **SCIP** | Index / Document / Occurrence / Symbol | `Relationship` multi-flag (ref/impl/typedef/def) | External tools over protobuf index | Indexer-dependent (often build-aware for Java) | IDE nav; not Spring docs | **Schema inspiration** for exportable facts + multi-edge; don’t adopt SCIP wire as Stage 0 | Medium if we emit SCIP; low if we copy shape only |
| **Glean** | Typed immutable facts (schema) | Derived predicates (Angle/Datalog) | Angle; recursive limited in OSS | Language indexers (often compile-ish) | Meta: nav **+ docs** | **Conceptual twin** of maturation §1; ops too heavy to run Glean server in product | High |
| **Kythe** | Graph nodes + fact edges | Extensible schema | Graph query / tools | **Yes** (compilation units / kzip) | Cross-lang indexing | Opt-in high-fidelity path only | High |
| **CodeQL** | Extracted DB + QL predicates | Relational | QL | Often build; we already opt-in | Security / deep queries | Keep as **opt-in scanner**, not default SoR | Medium–high |
| **ArchUnit** | In-memory class model | Rule checks (not durable store) | Java DSL | **Yes** | Architecture tests | Precision augment; not fact export | Medium |
| **jQAssistant** | Neo4j property graph | Labels + Cypher concepts | Cypher | Typically Maven/build | Spring plugin = framework graph | Optional CI graph; not portable default | High (Neo4j) |
| **RepoDoc RepoKG** | Repo knowledge graph | Impact edges for regen | Graph impact → selective agents | Paper: static analysis + LLM | **Full doc lifecycle** | Strong *product* signal: facts/graph first; incremental regen | Research / reimplement |
| **CodeWiki** | Dependency graph (Tree-sitter) | `depends_on` | Hierarchical partition + agents | **No** (static) | Hierarchical wiki docs | Validates AST graphs + better partitioning than token-only | Research |

---

## DFS themes (collapsed)

### T1 — Unary maps lose to multi-edge / multi-def

- SCIP: one symbol can relate to many others with **orthogonal flags**; definition resolution is explicit override, not silent last-write.
- Glean: append facts; derive consistency in IDB rather than mutate EDB.
- **Our contested map** (partial): when two tables claim one entity, refuse LWW — aligns with T1 but is still a **map-shaped** mitigation, not a general fact store.

### T2 — EDB vs IDB (raw scan vs derived predicates)

- Glean / CodeQL / jQAssistant all separate extract from derive.
- Maturation §1 and JPA survey assume derived passes for `@JoinTable`, inheritance, etc.
- **Still valid thesis**; survey’s *predicate list* remains useful. Survey’s *sizing/timeline* and path layout are stale.

### T3 — Compile vs portable default

- Kythe / ArchUnit / typical CodeQL / jQAssistant: compile or heavy extract.
- CodeWiki + our Stage 0: source-text / Tree-sitter.
- Product already chose: **default portable; opt-in fidelity** (CONSTRAINTS / Stage 0 voice fix). Any Phase 1 fact store must respect that fork — maturation plan text that blurs CodeQL-as-default is obsolete.

### T4 — Docs as views / incremental materialization

- DDIA framing in maturation §0; RepoDoc incremental impact; Glean docs-at-Meta.
- Path B fan-out (~`2G+17`) is a **view-rebuild** tax, not a Stage 0 precision tax.
- Fact store alone does not delete fan-out; it enables (a) shared references without rebroadcast, (b) later selective regen (RepoDoc-style). Phase 1 should enable (a) first; (b) is Phase 2+ research.

### T5 — Don’t ship Neo4j/Glean as the product SoR

- Graph DBs and Glean servers win at *query UX* and *scale-at-Meta*.
- Our operator pilot needs a directory of JSON/Parquet/SQLite-class artifacts a PE can open without standing up RocksDB+Thrift.
- Collation verdict: **file-backed fact ledger + optional export**, not embedded Neo4j.

---

## What the in-repo plan still gets right vs wrong

| Claim (maturation / JPA survey) | Collation verdict |
|---------------------------------|-------------------|
| Facts SoR, docs materialized views | **Confirmed** by Glean/RepoDoc/DDIA usage pattern |
| `entity_table_map` unary is insufficient | **Confirmed**; contested is partial; SCIP/Glean show richer models |
| Derived predicates for JPA vocabulary | **Confirmed** as direction; survey vocab still useful |
| Phase 0.1 Elsevier PORTING / `_python-checks.yml` | **Obsolete** — do not execute |
| Path cites under `scripts/` for product tools | **Obsolete** — `src/doc_engine/` |
| “Mostly not started Phase 1” implying blank slate | **Partially wrong** — contested map, packaging, scanner defaults already moved |
| Bytecode/ArchUnit as near-term SoR | **Wrong for default**; right as opt-in (source-text research still holds) |

---

## Approaches we are *not* taking in Phase 1

- Stand up Glean or Kythe in-product.
- Replace Stage 0 with ArchUnit/CodeQL-only.
- Embed Neo4j for the default path.
- Fan-out topology mega-PR without a durable fact layer (addresses symptom, not SoR).
